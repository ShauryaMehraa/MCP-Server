# Agricultural Data MCP Server

A simple HTTP server that gives you access to live Indian agricultural data: market prices from Agmarknet and fertilizer recommendations from Soil Health Portal.

## What It Does

Get real-time data about:
- **Agricultural commodity prices** (wheat, rice, vegetables, etc.)
- **Fertilizer recommendations** based on soil test results (N, P, K, Organic Carbon)
- **Available crops** for soil testing in different states
- **Market trends** and price movements

## Getting Started

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
python server.py
```

That's it. The server starts on `http://localhost:9004`.

To change the port, copy `.env.example` to `.env` and edit it.

## The Tools

**Market Price Tools** (4)
- Search prices by commodity name (wheat, rice, etc.)
- Get all market records with filters
- Browse through paginated results

**Soil & Fertilizer Tools** (5)
- List all Indian states (33 total)
- Find districts in a state
- See which crops have soil testing available
- **Get fertilizer recommendations** - the main feature
- Filter crops with official fertilizer recommendations

## How to Use

### Find Market Prices

Search for a commodity (no IDs needed):
```json
{
  "commodity_contains": "wheat",
  "limit_per_page": 20
}
```

### Get Fertilizer Recommendation

Three simple steps:

1. **Get the list of states**
   - Returns: 33 states with their IDs

2. **Pick a state and get crops**
   - Pick any state ID from step 1
   - Returns: ~17 crops available for that state

3. **Get the recommendation**
   ```json
   {
     "state": "63f9ce47519359b7438e76fa",
     "crops": ["6625fcb2c986db5da828c206"],
     "n": 180,
     "p": 70,
     "k": 120,
     "oc": 0.8
   }
   ```
   Where:
   - N = Nitrogen (ppm)
   - P = Phosphorus (ppm)
   - K = Potassium (ppm)
   - OC = Organic Carbon (%)

   Returns: Recommended fertilizer dosages (both organic and chemical options)

## Performance

- **Live data**: Everything is real, from government APIs
- **24 market records** available per query
- **100% uptime** in testing (10/10 successful calls)
- **Automatic retries** if the backend is slow

## Configuration

Edit `.env` to change:
- `MCP_PORT` - Server port (default: 9004)
- `MCP_HOST` - Listen address (default: 0.0.0.0)

All other settings use government API defaults and work out of the box.

## Troubleshooting

**Server won't start**
- Port 9004 is in use → change `MCP_PORT` in `.env`
- Python 3.10+ required

**No market data**
- Try different date or commodity name
- Use the dynamic search tool

**Fertilizer data empty**
- Double-check state and crop IDs (get from state/crop tools)
- OC must be 0–5%

---

Built with Python FastMCP | Connects to Agmarknet & Soil Health portals
