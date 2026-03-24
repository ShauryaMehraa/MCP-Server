from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date as date_type
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

# Configure logging similar to admin reference implementation.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("AGMARKNET_BASE_URL", "https://api.agmarknet.gov.in/v1").rstrip("/")
SOILHEALTH_GRAPHQL_URL = os.getenv("SOILHEALTH_GRAPHQL_URL", "https://soilhealth4.dac.gov.in").rstrip("/")
TIMEOUT_SECONDS = float(os.getenv("AGMARKNET_TIMEOUT_SECONDS", "30"))
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http").strip().lower()
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0").strip()
MCP_PORT = int(os.getenv("MCP_PORT", "9004"))
MCP_MOUNT_PATH = os.getenv("MCP_MOUNT_PATH", "/").strip() or "/"
MAX_RETRIES = int(os.getenv("AGMARKNET_MAX_RETRIES", "3"))
INITIAL_BACKOFF = float(os.getenv("AGMARKNET_INITIAL_BACKOFF", "0.5"))

SOILHEALTH_GET_STATE_QUERY = """
query GetState($getStateId: String, $code: String) {
	getState(id: $getStateId, code: $code)
}
"""

SOILHEALTH_GET_DISTRICTS_QUERY = """
query GetdistrictAndSubdistrictBystate(
	$getdistrictAndSubdistrictBystateId: String,
	$name: String,
	$state: ID,
	$subdistrict: Boolean,
	$code: String,
	$aspirationaldistrict: Boolean
) {
	getdistrictAndSubdistrictBystate(
		id: $getdistrictAndSubdistrictBystateId,
		name: $name,
		state: $state,
		subdistrict: $subdistrict,
		code: $code,
		aspirationaldistrict: $aspirationaldistrict
	)
}
"""

SOILHEALTH_GET_CROP_REGISTRIES_QUERY = """
query GetCropRegistries($state: String) {
	getCropRegistries(state: $state) {
		GFRavailable
		id
		combinedName
	}
}
"""

SOILHEALTH_GET_TEST_CENTERS_QUERY = """
query GetTestCenters($state: String, $district: String) {
	getTestCenters(state: $state, district: $district) {
		state
	}
}
"""

SOILHEALTH_GET_RECOMMENDATIONS_QUERY = """
query GetRecommendations($state: ID!, $results: JSON!, $district: ID, $crops: [ID!], $naturalFarming: Boolean) {
	getRecommendations(
		state: $state
		results: $results
		district: $district
		crops: $crops
		naturalFarming: $naturalFarming
	)
}
"""

mcp = FastMCP(
	"agmarknet-fastmcp",
	host=MCP_HOST,
	port=MCP_PORT,
	mount_path=MCP_MOUNT_PATH,
)


def _encode_list(values: list[int] | None) -> str | None:
	if values is None:
		return None
	return json.dumps(values)


def _normalize_query_value(value: Any) -> Any:
	if isinstance(value, list):
		return json.dumps(value)
	return value


def _clean_params(params: dict[str, Any] | None = None) -> dict[str, Any]:
	if not params:
		return {}
	return {k: _normalize_query_value(v) for k, v in params.items() if v is not None}


async def _retry_with_backoff(func, *args, max_retries: int = MAX_RETRIES, **kwargs):
	last_exception: Exception | None = None

	for attempt in range(max_retries):
		try:
			return await func(*args, **kwargs)
		except httpx.HTTPStatusError as exc:
			status = exc.response.status_code if exc.response is not None else None

			if status == 429 or (status is not None and 500 <= status < 600):
				last_exception = exc
				if attempt < max_retries - 1:
					backoff = INITIAL_BACKOFF * (2**attempt)
					logger.warning("HTTP %s retry %s/%s after %.2fs", status, attempt + 1, max_retries, backoff)
					await asyncio.sleep(backoff)
					continue
				break

			raise
		except (
			httpx.ConnectError,
			httpx.ReadTimeout,
			httpx.WriteTimeout,
			httpx.TimeoutException,
			httpx.RemoteProtocolError,
			httpx.RequestError,
		) as exc:
			last_exception = exc
			if attempt < max_retries - 1:
				backoff = INITIAL_BACKOFF * (2**attempt)
				logger.warning("Network retry %s/%s after %.2fs: %s", attempt + 1, max_retries, backoff, exc)
				await asyncio.sleep(backoff)
				continue
			break
		except Exception:
			raise

	if last_exception:
		raise last_exception

	raise RuntimeError("retry_with_backoff exhausted without captured exception")


async def _request(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
	url = f"{BASE_URL}/{path.lstrip('/')}"
	cleaned_params = _clean_params(params)

	async def make_request():
		async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
			response = await client.get(url, params=cleaned_params)
			response.raise_for_status()
			return response

	response = await _retry_with_backoff(make_request)
	return response.json()


async def _soilhealth_graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
	body = {
		"query": query,
		"variables": variables,
	}

	async def make_request():
		async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
			response = await client.post(SOILHEALTH_GRAPHQL_URL, json=body)
			response.raise_for_status()
			return response

	response = await _retry_with_backoff(make_request)
	data = response.json()

	if isinstance(data, dict) and data.get("errors"):
		return {
			"success": False,
			"error": "graphql_error",
			"errors": data.get("errors"),
			"data": data.get("data"),
		}

	return {
		"success": True,
		"data": data.get("data") if isinstance(data, dict) else data,
	}


@mcp.tool()
async def get_dashboard_data(
	dashboard: str,
	date: str | None = None,
	group: list[int] | None = None,
	commodity: list[int] | None = None,
	variety: int | None = None,
	state: int | None = None,
	district: list[int] | None = None,
	market: list[int] | None = None,
	grades: list[int] | None = None,
	limit: int = 10,
	page: int | None = None,
	format: str = "json",
) -> dict[str, Any]:
	"""Fetch Agmarknet dashboard data with filters and pagination.

	Example dashboard value: marketwise_price_arrival
	"""
	if limit < 1:
		raise ValueError("limit must be >= 1")

	if date is None:
		date = date_type.today().isoformat()

	params = {
		"dashboard": dashboard,
		"date": date,
		"group": _encode_list(group),
		"commodity": _encode_list(commodity),
		"variety": variety,
		"state": state,
		"district": _encode_list(district),
		"market": _encode_list(market),
		"grades": _encode_list(grades),
		"limit": limit,
		"page": page,
		"format": format,
	}

	try:
		return await _request("dashboard-data/", params=params)
	except httpx.HTTPStatusError as exc:
		status = exc.response.status_code if exc.response is not None else None
		message = ""
		if exc.response is not None:
			try:
				message = exc.response.text[:300]
			except Exception:
				message = str(exc)
		logger.warning("Agmarknet get_dashboard_data failed: %s", status)
		return {
			"success": False,
			"error": "api_error",
			"status_code": status,
			"message": message,
		}
	except Exception as exc:
		logger.error("Agmarknet get_dashboard_data request failed: %s", exc)
		return {
			"success": False,
			"error": "request_failed",
			"detail": str(exc),
		}


@mcp.tool()
async def get_by_absolute_url(url: str) -> dict[str, Any]:
	"""Follow Agmarknet pagination links such as pagination.next_page."""
	async def make_request():
		async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
			response = await client.get(url)
			response.raise_for_status()
			return response

	try:
		response = await _retry_with_backoff(make_request)
		return response.json()
	except httpx.HTTPStatusError as exc:
		status = exc.response.status_code if exc.response is not None else None
		message = exc.response.text[:300] if exc.response is not None else str(exc)
		return {
			"success": False,
			"error": "api_error",
			"status_code": status,
			"message": message,
		}
	except Exception as exc:
		return {
			"success": False,
			"error": "request_failed",
			"detail": str(exc),
		}


@mcp.tool()
async def agmarknet_get(path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
	"""Generic Agmarknet GET request for dynamic endpoints.

	- path example: dashboard-data/
	- list values in query are encoded as JSON-style arrays
	"""
	params = _clean_params(query)

	try:
		return await _request(path=path, params=params)
	except httpx.HTTPStatusError as exc:
		status = exc.response.status_code if exc.response is not None else None
		message = exc.response.text[:300] if exc.response is not None else str(exc)
		return {
			"success": False,
			"error": "api_error",
			"status_code": status,
			"message": message,
		}
	except Exception as exc:
		return {
			"success": False,
			"error": "request_failed",
			"detail": str(exc),
		}


@mcp.tool()
async def marketwise_price_arrival(
	group: list[int],
	commodity: list[int],
	district: list[int],
	market: list[int],
	variety: int,
	state: int,
	grades: list[int] | None = None,
	date: str | None = None,
	limit: int = 10,
	page: int | None = None,
) -> dict[str, Any]:
	"""Convenience wrapper for the marketwise_price_arrival dashboard."""
	return await get_dashboard_data(
		dashboard="marketwise_price_arrival",
		date=date,
		group=group,
		commodity=commodity,
		variety=variety,
		state=state,
		district=district,
		market=market,
		grades=grades,
		limit=limit,
		page=page,
		format="json",
	)


@mcp.tool()
async def marketwise_price_arrival_dynamic(
	date: str | None = None,
	commodity_contains: str | None = None,
	commodity_group_contains: str | None = None,
	trend: str | None = None,
	limit_per_page: int = 50,
	max_pages: int = 10,
) -> dict[str, Any]:
	"""Fetch marketwise data dynamically without requiring hardcoded ID filters.

	This tool auto-pages results and applies client-side text filters.
	"""
	if date is None:
		date = date_type.today().isoformat()

	commodity_q = commodity_contains.lower().strip() if commodity_contains else None
	group_q = commodity_group_contains.lower().strip() if commodity_group_contains else None
	trend_q = trend.lower().strip() if trend else None

	records: list[dict[str, Any]] = []
	pages_fetched = 0
	total_count: int | None = None

	for page_no in range(1, max_pages + 1):
		response = await get_dashboard_data(
			dashboard="marketwise_price_arrival",
			date=date,
			limit=limit_per_page,
			page=page_no,
			format="json",
		)

		if response.get("success") is False:
			return response

		pages_fetched += 1
		pagination = response.get("pagination", {})
		if total_count is None:
			try:
				total_count = int(pagination.get("total_count"))
			except (TypeError, ValueError):
				total_count = None

		page_records = response.get("data", {}).get("records", []) or []
		if not page_records:
			break

		for record in page_records:
			cmdt_name = str(record.get("cmdt_name", "")).lower()
			cmdt_group = str(record.get("cmdt_grp_name", "")).lower()
			record_trend = str(record.get("trend", "")).lower()

			if commodity_q and commodity_q not in cmdt_name:
				continue
			if group_q and group_q not in cmdt_group:
				continue
			if trend_q and trend_q != record_trend:
				continue

			records.append(record)

		if not pagination.get("next_page"):
			break

	unique_groups = sorted({str(r.get("cmdt_grp_name", "")).strip() for r in records if r.get("cmdt_grp_name")})
	unique_commodities = sorted({str(r.get("cmdt_name", "")).strip() for r in records if r.get("cmdt_name")})

	return {
		"status": "success",
		"query": {
			"date": date,
			"commodity_contains": commodity_contains,
			"commodity_group_contains": commodity_group_contains,
			"trend": trend,
			"limit_per_page": limit_per_page,
			"max_pages": max_pages,
		},
		"meta": {
			"pages_fetched": pages_fetched,
			"reported_total_count": total_count,
			"matched_count": len(records),
			"unique_groups": unique_groups,
			"unique_commodities": unique_commodities,
		},
		"records": records,
	}


@mcp.tool()
async def soilhealth_get_states(
	state_id: str | None = None,
	code: str | None = None,
) -> dict[str, Any]:
	"""Fetch Soil Health states from live portal GraphQL backend."""
	variables = {
		"getStateId": state_id,
		"code": code,
	}

	try:
		result = await _soilhealth_graphql(SOILHEALTH_GET_STATE_QUERY, variables)
		if result.get("success") is False:
			return result

		states = result.get("data", {}).get("getState", [])
		if isinstance(states, list) and states:
			return {
				"success": True,
				"source": "soilhealth4.dac.gov.in",
				"count": len(states),
				"states": states,
			}

		# Fallback for public listing: derive unique states from test center records.
		if not state_id and not code:
			fallback = await _soilhealth_graphql(
				SOILHEALTH_GET_TEST_CENTERS_QUERY,
				{"state": None, "district": None},
			)
			if fallback.get("success") is False:
				return fallback

			rows = fallback.get("data", {}).get("getTestCenters", [])
			unique: dict[str, dict[str, Any]] = {}
			for row in rows if isinstance(rows, list) else []:
				state_obj = row.get("state") if isinstance(row, dict) else None
				if not isinstance(state_obj, dict):
					continue
				state_key = str(state_obj.get("_id") or state_obj.get("id") or "").strip()
				if not state_key:
					continue
				unique[state_key] = state_obj

			derived_states = sorted(unique.values(), key=lambda x: str(x.get("name", "")))
			return {
				"success": True,
				"source": "soilhealth4.dac.gov.in",
				"count": len(derived_states),
				"states": derived_states,
				"note": "Derived from getTestCenters fallback because getState returned empty for unfiltered query.",
			}

		return {
			"success": True,
			"source": "soilhealth4.dac.gov.in",
			"count": 0,
			"states": [],
		}
	except Exception as exc:
		return {
			"success": False,
			"error": "request_failed",
			"detail": str(exc),
		}


@mcp.tool()
async def soilhealth_get_districts_by_state(
	state: str,
	name: str | None = None,
	subdistrict: bool = False,
	code: str | None = None,
	aspirationaldistrict: bool = False,
) -> dict[str, Any]:
	"""Fetch Soil Health districts for a given state ID."""
	variables = {
		"getdistrictAndSubdistrictBystateId": None,
		"name": name,
		"state": state,
		"subdistrict": subdistrict,
		"code": code,
		"aspirationaldistrict": aspirationaldistrict,
	}

	try:
		result = await _soilhealth_graphql(SOILHEALTH_GET_DISTRICTS_QUERY, variables)
		if result.get("success") is False:
			return result
		districts = result.get("data", {}).get("getdistrictAndSubdistrictBystate", [])
		return {
			"success": True,
			"source": "soilhealth4.dac.gov.in",
			"count": len(districts) if isinstance(districts, list) else 0,
			"districts": districts,
		}
	except Exception as exc:
		return {
			"success": False,
			"error": "request_failed",
			"detail": str(exc),
		}


@mcp.tool()
async def soilhealth_get_crop_registries(
	state: str,
	gfr_only: bool = True,
) -> dict[str, Any]:
	"""Fetch crop registries used by Soil Health fertilizer recommendation screen."""
	variables = {
		"state": state,
	}

	try:
		result = await _soilhealth_graphql(SOILHEALTH_GET_CROP_REGISTRIES_QUERY, variables)
		if result.get("success") is False:
			return result

		crops = result.get("data", {}).get("getCropRegistries", [])
		if gfr_only and isinstance(crops, list):
			crops = [crop for crop in crops if str(crop.get("GFRavailable", "")).lower() == "yes"]

		return {
			"success": True,
			"source": "soilhealth4.dac.gov.in",
			"count": len(crops) if isinstance(crops, list) else 0,
			"crops": crops,
		}
	except Exception as exc:
		return {
			"success": False,
			"error": "request_failed",
			"detail": str(exc),
		}


@mcp.tool()
async def soilhealth_get_fertilizer_recommendations(
	state: str,
	n: float,
	p: float,
	k: float,
	oc: float,
	district: str | None = None,
	crops: list[str] | None = None,
	natural_farming: bool = False,
) -> dict[str, Any]:
	"""Fetch crop-specific fertilizer dosage recommendations from Soil Health portal."""
	variables = {
		"state": state,
		"district": district,
		"crops": crops,
		"naturalFarming": natural_farming,
		"results": {
			"n": n,
			"p": p,
			"k": k,
			"OC": oc,
		},
	}

	try:
		result = await _soilhealth_graphql(SOILHEALTH_GET_RECOMMENDATIONS_QUERY, variables)
		if result.get("success") is False:
			return result
		recommendations = result.get("data", {}).get("getRecommendations", [])
		return {
			"success": True,
			"source": "soilhealth4.dac.gov.in",
			"count": len(recommendations) if isinstance(recommendations, list) else 0,
			"recommendations": recommendations,
		}
	except Exception as exc:
		return {
			"success": False,
			"error": "request_failed",
			"detail": str(exc),
		}


if __name__ == "__main__":
	# Default transport follows admin reference style: streamable-http on port 9004.
	mcp.run(transport=MCP_TRANSPORT)
