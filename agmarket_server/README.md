# Agmarket MCP Server

## Run with Poetry

```powershell
py -m poetry install
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
py -m poetry run python server_agmarket.py
```

## Test command

```powershell
py -m poetry run python test_agmarket.py --state Punjab --district "All Districts" --market "All Markets" --commodity-group "All Commodities" --commodity "All Commodities" --variety "All Varieties" --grade FAQ --date 2026-03-23 --limit 2000
```

## Names-only search (no IDs)

Use MCP tool `marketwise_price_arrival` with names only:

- `state_name` (example: Gujarat)
- `district_name` (example: Ahmedabad)
- `market_name` (example: Ahmedabad APMC)
- `commodity_group_name` (example: Vegetables)
- `commodity_name` (example: Tomato)
- `variety_name` (example: All Varieties)
- `grade_name` (example: FAQ)

The server resolves all IDs internally from live `dashboard-filters` metadata.
