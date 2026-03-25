# Soil Health MCP Server

## Run with Poetry

```powershell
py -m poetry install
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
py -m poetry run python server_soilhealth.py
```

## Quick check

```powershell
py -m poetry run python -c "import asyncio, server_soilhealth; print(asyncio.run(server_soilhealth.soilhealth_get_states()).get('count'))"
```
