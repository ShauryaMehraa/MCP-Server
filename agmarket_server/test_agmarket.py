from __future__ import annotations

import argparse
import asyncio
import json
import logging

import server_agmarket


# Keep script output focused on diagnostics instead of HTTP transport logs.
logging.getLogger("httpx").setLevel(logging.WARNING)


async def check_agmarknet(
    state_name: str,
    district_name: str,
    market_name: str,
    commodity_group: str,
    commodity_name: str,
    variety_name: str,
    grade_name: str,
    date_freeze: str,
    limit: int,
) -> None:
    try:
        print("\n==============================================")
        print(" Checking Agmarknet with live name->ID resolution")
        print(f" State: {state_name} | District: {district_name} | Market: {market_name}")
        print(f" Commodity Group: {commodity_group} | Commodity: {commodity_name}")
        print(f" Variety: {variety_name} | Grade: {grade_name}")
        print(f" Date Freeze: {date_freeze}")
        print("==============================================")

        response = await server_agmarket.marketwise_price_arrival(
            state_name=state_name,
            district_name=district_name,
            market_name=market_name,
            commodity_group_name=commodity_group,
            commodity_name=commodity_name,
            variety_name=variety_name,
            grade_name=grade_name,
            date=date_freeze,
            limit=limit,
            page=1,
            include_resolved_ids=True,
        )

        if response.get("success") is False:
            print("[-] Query failed:")
            print(json.dumps(response, indent=2))
            return

        result = response.get("result") or {}
        records = ((result.get("data") or {}).get("records") or [])
        print("[+] Resolved IDs:")
        print(json.dumps(response.get("resolved_filters") or {}, indent=2))
        print(f"[+] Matched records: {len(records)}")
        if records:
            print(json.dumps(records[:2], indent=2))
        else:
            print("[-] No records found for the resolved filter set.")
    except Exception as exc:
        print(f"[-] Unexpected error while checking Agmarknet: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agmarknet checker with aggregate/location modes.")
    parser.add_argument("--state", default="Punjab")
    parser.add_argument("--district", default="All Districts")
    parser.add_argument("--market", default="All Markets")
    parser.add_argument("--commodity-group", default="All Commodity Groups")
    parser.add_argument("--commodity", default="All Commodities")
    parser.add_argument("--variety", default="All Varieties")
    parser.add_argument("--grade", default="FAQ")
    parser.add_argument("--date", default="2026-03-23")
    parser.add_argument("--limit", type=int, default=2000)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(
        check_agmarknet(
            state_name=args.state,
            district_name=args.district,
            market_name=args.market,
            commodity_group=args.commodity_group,
            commodity_name=args.commodity,
            variety_name=args.variety,
            grade_name=args.grade,
            date_freeze=args.date,
            limit=args.limit,
        )
    )
