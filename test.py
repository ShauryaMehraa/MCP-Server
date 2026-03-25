from __future__ import annotations

import asyncio
import json
from datetime import datetime, UTC

import server_agmarknet
import server_soilhealth


def is_pass(response: dict) -> bool:
    return isinstance(response, dict) and response.get("success") is not False and not response.get("error")


def summarize_response(response: dict) -> str:
    if not isinstance(response, dict):
        return "invalid_response"

    if response.get("status") == "success":
        meta = response.get("meta", {})
        return f"matched={meta.get('matched_count')} pages={meta.get('pages_fetched')}"

    if isinstance(response.get("pagination"), dict):
        pagination = response.get("pagination", {})
        return f"page={pagination.get('current_page')} total={pagination.get('total_count')}"

    if "count" in response:
        return f"count={response.get('count')}"

    if response.get("error"):
        return f"error={response.get('error')}"

    return "ok"


async def run_tests() -> dict:
    # Prepare dynamic IDs for Soil Health queries.
    states_seed = await server_soilhealth.soilhealth_get_states()
    state_id = None
    if isinstance(states_seed, dict) and isinstance(states_seed.get("states"), list) and states_seed.get("states"):
        first_state = states_seed["states"][0]
        if isinstance(first_state, dict):
            state_id = first_state.get("_id") or first_state.get("id")

    crop_id = None
    if state_id:
        crops_seed = await server_soilhealth.soilhealth_get_crop_registries(state=state_id, gfr_only=True)
        if isinstance(crops_seed, dict) and isinstance(crops_seed.get("crops"), list) and crops_seed.get("crops"):
            first_crop = crops_seed["crops"][0]
            if isinstance(first_crop, dict):
                crop_id = first_crop.get("id") or first_crop.get("_id")

    tests = [
        ("agmarknet.get_dashboard_data(limit=3)", lambda: server_agmarknet.get_dashboard_data(dashboard="marketwise_price_arrival", limit=3)),
        ("agmarknet.marketwise_price_arrival_dynamic(wheat)", lambda: server_agmarknet.marketwise_price_arrival_dynamic(commodity_contains="wheat", limit_per_page=20, max_pages=2)),
        ("agmarknet.agmarknet_get(limit=2)", lambda: server_agmarknet.agmarknet_get(path="dashboard-data/", query={"dashboard": "marketwise_price_arrival", "limit": 2})),
        ("agmarknet.get_by_absolute_url(page=2)", lambda: server_agmarknet.get_by_absolute_url(f"{server_agmarknet.BASE_URL}/dashboard-data/?dashboard=marketwise_price_arrival&limit=5&page=2")),
        ("agmarknet.marketwise_price_arrival_dynamic(cereals)", lambda: server_agmarknet.marketwise_price_arrival_dynamic(commodity_group_contains="cereals", limit_per_page=20, max_pages=2)),
        ("soilhealth.soilhealth_get_states()", lambda: server_soilhealth.soilhealth_get_states()),
        ("soilhealth.soilhealth_get_states(code=AP)", lambda: server_soilhealth.soilhealth_get_states(code="AP")),
        ("soilhealth.soilhealth_get_districts_by_state(first_state)", lambda: server_soilhealth.soilhealth_get_districts_by_state(state=state_id) if state_id else asyncio.sleep(0, result={"success": False, "error": "missing_state_id"})),
        ("soilhealth.soilhealth_get_crop_registries(first_state)", lambda: server_soilhealth.soilhealth_get_crop_registries(state=state_id, gfr_only=True) if state_id else asyncio.sleep(0, result={"success": False, "error": "missing_state_id"})),
        ("soilhealth.soilhealth_get_fertilizer_recommendations(first_state)", lambda: server_soilhealth.soilhealth_get_fertilizer_recommendations(state=state_id, crops=[crop_id] if crop_id else None, n=180, p=70, k=120, oc=0.8) if state_id else asyncio.sleep(0, result={"success": False, "error": "missing_state_id"})),
    ]

    query_results: list[dict] = []
    for index, (name, func) in enumerate(tests, start=1):
        response = await func()
        query_results.append(
            {
                "query_no": index,
                "name": name,
                "passed": is_pass(response),
                "summary": summarize_response(response),
            }
        )

    pass_count = sum(1 for item in query_results if item["passed"])

    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "total_queries": 10,
        "pass_count": pass_count,
        "fail_count": 10 - pass_count,
        "queries": query_results,
    }


if __name__ == "__main__":
    result = asyncio.run(run_tests())
    print(json.dumps(result, indent=2))
