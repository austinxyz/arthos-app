# LLM Insights

On the stock details page, add a tab called "Insights". This tab should be the left-most tab (before Covered Calls).
The Insights tab displays AI-generated analysis for the stock using OpenRouter (model configured via admin debug page).

## User Experience

### Tab Placement & Default Selection
- Add "Insights" as the first tab on the stock detail page
- When the user lands on the stock details page, the Insights tab should be selected by default

### Display Format
Single card layout displaying a comprehensive investment analysis:
- **Card header**: "Investment Analysis" - blue-themed header with lightbulb icon
- **Card body**: Renders the 6-section analysis as formatted markdown

The analysis includes:
1. The Strategic Narrative & Pivot
2. Fundamental "Health Check" (The Numbers)
3. The Debt & Cash Flow Stress Test
4. Anatomy of Recent Price Action
5. Future Pathways & Watchlist
6. The Investment Verdict

### Loading & Error States
- Show a loading spinner while fetching insights
- If insights are unavailable, show a friendly message: "Insights are being generated. Please check back shortly."
- If API fails, show: "Unable to load insights at this time."

## Technical Implementation

### OpenRouter Setup
1. Go to [OpenRouter](https://openrouter.ai/)
2. Create an API key
3. Add to environment variables: `OPENROUTER_API_KEY`
4. Configure active model via `/debug/llm-models` admin page

### Model & Prompt
**Model**: Configured via database (admin debug page). Default: `google/gemini-2.5-flash-preview-05-20` (free tier)

**Prompt**:
```
Role: Act as a Senior Equity Research Analyst with a focus on deep fundamental valuation and strategic capital allocation.

Task: Conduct a comprehensive, multi-layered investment analysis of [TICKER]. The goal is to determine if the current stock price represents a fundamental opportunity or a "value trap."

Please structure the analysis into the following 6 distinct sections:

1. The Strategic Narrative & Pivot

What is the core story management is selling right now? (e.g., Transition to AI, shifting from license to SaaS, etc.).

Requirement: Include specific quotes or stated goals from recent earnings calls or analyst days (CEO/CTO) that validate this strategy.

Are they a "First Mover" or a "Late Mover" playing catch-up?

2. Fundamental "Health Check" (The Numbers)

Revenue Mix: Break down the quality of revenue (Recurring vs. One-time). Is the "growth" segment actually moving the needle?

DuPont Analysis: Break down their ROE (Return on Equity). Is it driven by high margins, asset efficiency, or just massive leverage (Debt)?

Capital Intensity: Calculate the "Capex/Revenue" ratio. Are they burning cash to buy growth? How does this compare to their historical average?

3. The Debt & Cash Flow Stress Test

Leverage: What is their Debt-to-EBITDA ratio? Is it dangerously high (>3x)?

Maturity Profile: Do they have a "wall of debt" coming due in the next 2-3 years?

Cash Flow Dynamics: Analyze the trend of Free Cash Flow over the last 4 quarters. Are they funding operations from cash flow or by issuing new debt/equity?

4. Anatomy of Recent Price Action

The stock has moved significantly recently. Dissect why beyond the headlines.

Was the move driven by a "valuation reset" (multiple compression), a fundamental broken promise (earnings miss), or macro factors?

Identify key technical support/resistance levels that matter right now.

5. Future Pathways & Watchlist

Bull Case: What must go right for the stock to double?

Bear Case: What is the specific "failure mode"? (e.g., AI adoption slows, margins compress).

Leading Indicators: Give me 2-3 specific metrics to watch in the next earnings report (e.g., RPO conversion, Gross Margin stability) that will signal which scenario is playing out.

6. The Investment Verdict

Synthesize the above into a clear stance: Buy, Sell, or Wait?

Provide a "Buy Zone" price level where the risk/reward becomes favorable.

```

### Database Changes
Add two fields to `StockAttributes` model (`app/models/stock_price.py`):
```python
insights_json: Optional[str] = Field(default=None)  # JSON string with 'analysis' key containing markdown
insights_updated_at: Optional[datetime] = Field(default=None)  # Last fetch timestamp
```

### API Changes
**New Endpoint**: `GET /api/v1/stock/{ticker}/insights`

Response:
```json
{
  "ticker": "AAPL",
  "insights": {
    "analysis": "## 1. The Strategic Narrative & Pivot\n\n..."
  },
  "updated_at": "2026-02-03T10:30:00Z",
  "is_stale": false,
  "status": "available"
}
```

### Service Layer
Create `app/services/insights_service.py`:
- `get_insights(ticker: str) -> dict` - Returns cached insights or fetches fresh
- `fetch_insights_from_llm(ticker: str) -> dict` - Calls Google AI API
- `is_insights_stale(updated_at: datetime) -> bool` - Returns True if > 24 hours old

### Fetch Strategy: On-demand + Scheduled

**On-demand** (when user visits stock page):
1. Check if `insights_json` exists and `insights_updated_at` is within 24 hours
2. If fresh, return cached insights
3. If stale or missing, fetch from LLM asynchronously and return immediately with loading state
4. Store new insights in database

**Scheduled Job** (runs daily):
1. Get all unique tickers from all watchlists (all users)
2. For each ticker with insights older than 24 hours, refresh from LLM
3. Add to existing scheduler in `app/services/scheduler_service.py`
4. Run at off-peak hours (e.g., 5 AM EST)

### Rate Limiting & Error Handling
- Implement exponential backoff for API failures
- Cache failures for 1 hour to avoid hammering API
- Log all API calls and errors
- Set reasonable timeout (30 seconds)

## Files to Create/Modify

### New Files
- `app/services/insights_service.py` - LLM integration and caching logic

### Modified Files
- `app/models/stock_price.py` - Add insights fields to StockAttributes
- `app/main.py` - Add `/api/v1/stock/{ticker}/insights` endpoint
- `app/services/scheduler_service.py` - Add daily insights refresh job
- `app/templates/stock_detail.html` - Add Insights tab (first position, default selected)

## Environment Variables
- `OPENROUTER_API_KEY` - Required for OpenRouter API access

## Testing
1. Test LLM prompt returns valid JSON
2. Test caching logic (fresh vs stale)
3. Test scheduled job picks up all watchlist tickers
4. Test UI displays insights correctly
5. Test error states (API failure, timeout, invalid response)
