# LLM Insights

On the stock details page, add a tab called "Insights". This tab should be the left-most tab (before Covered Calls).
The Insights tab displays AI-generated analysis for the stock using Google AI Studio (Gemini 2.0 Flash).

## User Experience

### Tab Placement & Default Selection
- Add "Insights" as the first tab on the stock detail page
- When the user lands on the stock details page, the Insights tab should be selected by default

### Display Format
Two-column layout with side-by-side cards:
- **Left card**: "What's Going Right" - green-themed header, lists top 5 positive factors
- **Right card**: "What's Going Wrong" - red-themed header, lists top 5 negative factors

Each item should display:
- A brief title/headline
- A short explanation (1-2 sentences)

### Loading & Error States
- Show a loading spinner while fetching insights
- If insights are unavailable, show a friendly message: "Insights are being generated. Please check back shortly."
- If API fails, show: "Unable to load insights at this time."

## Technical Implementation

### Google AI Studio Setup
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Create a new API key
3. Add to environment variables: `GOOGLE_AI_API_KEY`
4. Add to Railway: `railway variables set GOOGLE_AI_API_KEY=<your-key>`

### Model & Prompt
**Model**: Gemini 2.0 Flash (`gemini-2.0-flash`)

**Prompt**:
```
You are an experienced stock market analyst. Analyze the stock {ticker} ({company_name}) and provide insights.

Return a JSON object with exactly this structure:
{
  "going_right": [
    {"title": "Brief headline", "description": "1-2 sentence explanation"},
    ... (exactly 5 items)
  ],
  "going_wrong": [
    {"title": "Brief headline", "description": "1-2 sentence explanation"},
    ... (exactly 5 items)
  ]
}

Consider these factors:
- Fundamentals (revenue, earnings, margins, debt)
- Technical indicators (price trends, moving averages, volume)
- Market conditions and sector performance
- Business developments (products, partnerships, management)
- Competitive positioning
- Macroeconomic factors

Be specific and actionable. Use recent data and developments.
Return ONLY the JSON object, no additional text.
```

### Database Changes
Add two fields to `StockAttributes` model (`app/models/stock_price.py`):
```python
insights_json: Optional[str] = Field(default=None)  # JSON string with going_right/going_wrong
insights_updated_at: Optional[datetime] = Field(default=None)  # Last fetch timestamp
```

### API Changes
**New Endpoint**: `GET /api/v1/stock/{ticker}/insights`

Response:
```json
{
  "ticker": "AAPL",
  "insights": {
    "going_right": [...],
    "going_wrong": [...]
  },
  "updated_at": "2026-02-03T10:30:00Z",
  "is_stale": false
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
- `GOOGLE_AI_API_KEY` - Required for Google AI Studio API access

## Testing
1. Test LLM prompt returns valid JSON
2. Test caching logic (fresh vs stale)
3. Test scheduled job picks up all watchlist tickers
4. Test UI displays insights correctly
5. Test error states (API failure, timeout, invalid response)
