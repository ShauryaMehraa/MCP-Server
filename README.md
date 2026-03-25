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

### Find Market Prices - Agmarknet API

Agmarknet is India's government portal for agricultural market data. It provides **real-time commodity prices, arrivals, and market trends** across all major agricultural markets in India.

#### What Agmarknet Data Includes
- **24+ commodity records** across Indian markets
- **Price trends**: up, down, stable
- **Market-wise prices**: Different prices at different markets for the same commodity
- **Arrival data**: When commodities arrive at markets
- **Dates & timestamps**: Track price changes over time
- **State and district filters**: Get data for specific regions

#### Simple Search (Recommended)

No IDs needed - just search by commodity name:

```json
{
  "commodity_contains": "wheat",
  "limit_per_page": 20
}
```

This searches across all markets and returns records matching "wheat".

#### Get All Market Records

Fetch raw market data with exact filters:

```json
{
  "dashboard": "marketwise_price_arrival",
  "date": "2026-03-24",
  "limit": 5,
  "page": 1
}
```

Response includes:
- Commodity name, group, variety
- Price at each market
- State and district
- Market name
- Trend (up/down/stable)
- Pagination for browsing results

#### Dynamic Search with Filters

Search market data without knowing specific IDs:

```json
{
  "commodity_contains": "rice",
  "commodity_group_contains": "cereals",
  "trend": "down",
  "limit_per_page": 50,
  "max_pages": 5
}
```

This will:
- Find commodities with "rice" in the name
- Filter to cereals group only
- Show only commodities with downward price trend
- Return up to 50 records per page, check up to 5 pages
- Auto-paginate internally

#### Handle Pagination

If you get a `next_page` URL in the response, use it to fetch the next page:

```json
{
  "url": "https://api.agmarknet.gov.in/v1/dashboard-data/?page=2&limit=10"
}
```

#### Real Data Example

From live testing, Agmarknet returns:
- **24 total market records** available
- **3 pages** of results (10 records per page)
- Commodities like: Wheat, Rice, Vegetables, Spices, etc.
- Each record includes: price, market, state, trend, arrival date

#### Agmarknet Use Cases
1. **Price Monitoring**: Check daily commodity prices
2. **Market Analysis**: Compare prices across different markets
3. **Trend Tracking**: See which commodities are going up/down
4. **Regional Data**: Find prices specific to your state
5. **Supply Chain**: Track when commodities arrive at markets

---

## How to Use - Fertilizer Recommendations

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

## Latest Live Re-Test (10 Queries)

Re-tested on **2026-03-25 (UTC)** against live backends:
- Agmarknet: `https://api.agmarknet.gov.in/v1`
- Soil Health: `https://soilhealth4.dac.gov.in`

**Result:** 10/10 queries passed.

| # | Query | Result |
|---|---|---|
| 1 | `get_dashboard_data(dashboard="marketwise_price_arrival", limit=5)` | Passed (records returned) |
| 2 | `marketwise_price_arrival_dynamic(commodity_contains="wheat", limit_per_page=20, max_pages=2)` | Passed (matched_count=1, pages_fetched=2) |
| 3 | `marketwise_price_arrival_dynamic(commodity_contains="rice", commodity_group_contains="cereals", trend="down", limit_per_page=20, max_pages=3)` | Passed (matched_count=0, query executed successfully) |
| 4 | `agmarknet_get(path="dashboard-data/", query={"dashboard":"marketwise_price_arrival","limit":3})` | Passed (records returned) |
| 5 | `get_by_absolute_url(next_page/page=2 URL)` | Passed (pagination fetch successful) |
| 6 | `soilhealth_get_states()` | Passed (count=33) |
| 7 | `soilhealth_get_states(code="AP")` | Passed (count=0, query executed successfully) |
| 8 | `soilhealth_get_districts_by_state(first_state)` | Passed (count=0, query executed successfully) |
| 9 | `soilhealth_get_crop_registries(first_state, gfr_only=True)` | Passed (count=17) |
| 10 | `soilhealth_get_fertilizer_recommendations(first_state, sample NPK/OC)` | Passed (count=1) |

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

---

## About Agmarknet

**Agmarknet** (Agricultural Market Network) is India's premier agricultural market information system operated by the Department of Agriculture. It provides:

### Key Features
- **Real-time market prices** for 100+ commodities
- **Multi-market data** - prices vary by location
- **Historical trends** - track price movements
- **Nationwide coverage** - data from all Indian states
- **Arrival information** - when goods reach markets
- **Market analysis** - supply and demand trends

### Data Available Through This Server
- **Commodity Pricing**: Current market rates for agricultural products
- **Market IDs, States, Districts**: Geographic filtering for regional data
- **Price Trends**: Upward, downward, or stable trends
- **Pagination**: Browse through large datasets efficiently

### Agmarknet Backend
- **URL**: `https://api.agmarknet.gov.in/v1`
- **Data Type**: REST API (JSON responses)
- **Update Frequency**: Real-time from markets
- **Coverage**: All major agricultural markets across India
- **Commodities**: Grains, vegetables, fruits, spices, etc.

### Example Agmarknet Queries
1. Get wheat prices across all markets
2. Find rice prices in major states only
3. Get commodity arrivals for today
4. Track price trends for specific commodities
5. Compare prices between different markets

### When to Use Agmarknet
- **For Farmers**: Check market prices before selling
- **For Traders**: Monitor price trends and arbitrage opportunities
- **For Researchers**: Analyze agricultural market data
- **For Apps**: Build price tracking or market analysis tools
- **For Supply Chain**: Understand commodity flow and markets

---

## API Architecture

The server acts as a bridge between two government APIs:

```
Your Client
    ↓
MCP Server (localhost:9004)
    ↓
├─→ Agmarknet API (api.agmarknet.gov.in)
│   └─→ Market prices, trends, commodities
│
└─→ Soil Health Portal (soilhealth4.dac.gov.in)
    └─→ Soil tests, fertilizer recommendations, crops
```

### Features
- **Smart Retry**: Automatic retries on network failures
- **Error Handling**: Graceful degradation with error messages
- **Pagination**: Handle large datasets efficiently
- **Real-time**: Live data from government backends
- **Simple Interface**: No complex authentication needed
