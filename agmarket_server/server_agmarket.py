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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("AGMARKNET_BASE_URL", "https://api.agmarknet.gov.in/v1").rstrip("/")
TIMEOUT_SECONDS = float(os.getenv("AGMARKNET_TIMEOUT_SECONDS", "30"))
MAX_RETRIES = int(os.getenv("AGMARKNET_MAX_RETRIES", "3"))
INITIAL_BACKOFF = float(os.getenv("AGMARKNET_INITIAL_BACKOFF", "0.5"))

MCP_TRANSPORT = os.getenv("AGMARKNET_MCP_TRANSPORT", os.getenv("MCP_TRANSPORT", "streamable-http")).strip().lower()
MCP_HOST = os.getenv("AGMARKNET_MCP_HOST", os.getenv("MCP_HOST", "0.0.0.0")).strip()
MCP_PORT = int(os.getenv("AGMARKNET_MCP_PORT", "9004"))
MCP_MOUNT_PATH = os.getenv("AGMARKNET_MCP_MOUNT_PATH", os.getenv("MCP_MOUNT_PATH", "/")).strip() or "/"

mcp = FastMCP(
    "agmarknet-mcp",
    host=MCP_HOST,
    port=MCP_PORT,
    mount_path=MCP_MOUNT_PATH,
)


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_all_value(value: str | None, all_label: str) -> bool:
    return _norm_text(value) in {"", _norm_text(all_label)}


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
    """Fetch Agmarknet dashboard data with explicit filters and pagination."""
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
        message = exc.response.text[:300] if exc.response is not None else str(exc)
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
    """Generic Agmarknet GET request for dynamic endpoints."""
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
async def get_dashboard_filters(dashboard_name: str = "marketwise_price_arrival") -> dict[str, Any]:
    """Fetch live filter metadata (states, districts, markets, commodity mappings) for a dashboard."""
    return await agmarknet_get("dashboard-filters/", {"dashboard_name": dashboard_name})


@mcp.tool()
async def marketwise_price_arrival_by_names(
    state_name: str = "All States",
    district_name: str = "All Districts",
    market_name: str = "All Markets",
    commodity_group_name: str = "All Commodity Groups",
    commodity_name: str = "All Commodities",
    variety_name: str = "All Varieties",
    grade_name: str = "FAQ",
    date: str | None = None,
    limit: int = 50,
    page: int | None = 1,
    include_resolved_ids: bool = False,
) -> dict[str, Any]:
    """Resolve filter names to IDs using dashboard-filters and fetch marketwise_price_arrival rows."""
    if date is None:
        date = date_type.today().isoformat()

    filters_response = await get_dashboard_filters("marketwise_price_arrival")
    if filters_response.get("success") is False or filters_response.get("error"):
        return {
            "success": False,
            "error": "filters_fetch_failed",
            "filters_response": filters_response,
        }

    meta = filters_response.get("data") or {}
    states = meta.get("state_data") or []
    districts = meta.get("district_data") or []
    markets = meta.get("market_data") or []
    groups = meta.get("cmdt_group_data") or []
    commodities = meta.get("cmdt_data") or []
    varieties = meta.get("variety_data") or []
    grades = meta.get("grade_data") or []

    resolved_state = None
    if not _is_all_value(state_name, "All States"):
        resolved_state = next((s for s in states if _norm_text(s.get("state_name")) == _norm_text(state_name)), None)
        if not resolved_state:
            return {
                "success": False,
                "error": "state_not_found",
                "state_name": state_name,
            }

    resolved_district = None
    if not _is_all_value(district_name, "All Districts"):
        state_id = resolved_state.get("state_id") if resolved_state else None
        resolved_district = next(
            (
                d
                for d in districts
                if _norm_text(d.get("district_name")) == _norm_text(district_name)
                and (state_id is None or d.get("state_id") == state_id)
            ),
            None,
        )
        if not resolved_district:
            return {
                "success": False,
                "error": "district_not_found",
                "district_name": district_name,
                "state_name": state_name,
            }

    resolved_market = None
    if not _is_all_value(market_name, "All Markets"):
        district_id = resolved_district.get("id") if resolved_district else None
        resolved_market = next(
            (
                m
                for m in markets
                if _norm_text(m.get("mkt_name")) == _norm_text(market_name)
                and (district_id is None or m.get("district_id") == district_id)
            ),
            None,
        )
        if not resolved_market:
            return {
                "success": False,
                "error": "market_not_found",
                "market_name": market_name,
                "district_name": district_name,
            }

    resolved_group = None
    if not _is_all_value(commodity_group_name, "All Commodity Groups"):
        resolved_group = next(
            (g for g in groups if _norm_text(g.get("cmdt_grp_name")) == _norm_text(commodity_group_name)),
            None,
        )
        if not resolved_group:
            return {
                "success": False,
                "error": "commodity_group_not_found",
                "commodity_group_name": commodity_group_name,
            }

    resolved_commodity = None
    if not _is_all_value(commodity_name, "All Commodities"):
        group_id = resolved_group.get("id") if resolved_group else None
        resolved_commodity = next(
            (
                c
                for c in commodities
                if _norm_text(c.get("cmdt_name")) == _norm_text(commodity_name)
                and (group_id is None or c.get("cmdt_group_id") == group_id)
            ),
            None,
        )
        if not resolved_commodity:
            return {
                "success": False,
                "error": "commodity_not_found",
                "commodity_name": commodity_name,
                "commodity_group_name": commodity_group_name,
            }

    resolved_variety = next(
        (v for v in varieties if _norm_text(v.get("variety_name")) == _norm_text(variety_name)),
        None,
    )
    if not resolved_variety:
        return {
            "success": False,
            "error": "variety_not_found",
            "variety_name": variety_name,
        }

    resolved_grade = next(
        (g for g in grades if _norm_text(g.get("grade_name")) == _norm_text(grade_name)),
        None,
    )
    if not resolved_grade:
        return {
            "success": False,
            "error": "grade_not_found",
            "grade_name": grade_name,
        }

    response = await get_dashboard_data(
        dashboard="marketwise_price_arrival",
        date=date,
        group=[resolved_group.get("id")] if resolved_group else None,
        commodity=[resolved_commodity.get("cmdt_id")] if resolved_commodity else None,
        variety=resolved_variety.get("id"),
        state=resolved_state.get("state_id") if resolved_state else None,
        district=[resolved_district.get("id")] if resolved_district else None,
        market=[resolved_market.get("id")] if resolved_market else None,
        grades=[resolved_grade.get("id")],
        limit=limit,
        page=page,
        format="json",
    )

    result: dict[str, Any] = {
        "success": response.get("success", True),
        "query": {
            "dashboard": "marketwise_price_arrival",
            "date": date,
            "state_name": state_name,
            "district_name": district_name,
            "market_name": market_name,
            "commodity_group_name": commodity_group_name,
            "commodity_name": commodity_name,
            "variety_name": variety_name,
            "grade_name": grade_name,
            "limit": limit,
            "page": page,
        },
        "result": response,
    }

    if include_resolved_ids:
        result["resolved_filters"] = {
            "state": resolved_state,
            "district": resolved_district,
            "market": resolved_market,
            "commodity_group": resolved_group,
            "commodity": resolved_commodity,
            "variety": resolved_variety,
            "grade": resolved_grade,
        }

    return result


@mcp.tool()
async def marketwise_price_arrival(
    state_name: str = "All States",
    district_name: str = "All Districts",
    market_name: str = "All Markets",
    commodity_group_name: str = "All Commodity Groups",
    commodity_name: str = "All Commodities",
    variety_name: str = "All Varieties",
    grade_name: str = "FAQ",
    date: str | None = None,
    limit: int = 50,
    page: int | None = 1,
    include_resolved_ids: bool = False,
) -> dict[str, Any]:
    """Name-based marketwise query wrapper. No ID inputs required."""
    return await marketwise_price_arrival_by_names(
        state_name=state_name,
        district_name=district_name,
        market_name=market_name,
        commodity_group_name=commodity_group_name,
        commodity_name=commodity_name,
        variety_name=variety_name,
        grade_name=grade_name,
        date=date,
        limit=limit,
        page=page,
        include_resolved_ids=include_resolved_ids,
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
    """Fetch marketwise data dynamically without requiring hardcoded ID filters."""
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


if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
