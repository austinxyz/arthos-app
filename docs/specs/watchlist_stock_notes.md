# Watchlist Stock Notes

A feature to add qualitative notes to stocks within watchlists, helping users track research, investment thesis, and decision-making rationale.

## Overview

Users can add plain text notes to any stock in their watchlists. Notes are **per-watchlist**, meaning the same stock in different watchlists can have different notes. This allows users to track different perspectives (e.g., "Growth Portfolio" vs "Dividend Portfolio" notes for the same stock).

## Core Requirements

### Data Model

- Notes are tied to the **watchlist + stock** combination (not global per stock)
- Each note stores:
  - `note_text`: Plain text content (max 500 characters)
  - `updated_at`: Timestamp of last modification
  - `created_at`: Timestamp of initial creation
- Notes belong to the watchlist owner (account_id)

### User Interface

#### Location
- **Stock Detail Page** (`/stock/{ticker}`) - A dedicated "Notes" tab alongside existing tabs (Covered Calls, RRR)

#### Notes Tab Behavior
- If the stock exists in **multiple watchlists**, display all notes labeled by watchlist name
- Each note card shows:
  - Watchlist name (header)
  - Note text
  - "Last updated: {date}" timestamp
  - Edit button
- If no notes exist, show empty state with "Add Note" prompt for each watchlist containing this stock
- If stock is not in any watchlist, show message: "Add this stock to a watchlist to create notes"

#### Edit Experience
- Click "Edit" to enter edit mode for that specific watchlist's note
- Simple textarea (500 character limit)
- Character counter showing remaining characters
- Save / Cancel buttons
- Auto-save is NOT required (explicit save only)

### Character Limit
- Maximum 500 characters per note
- Display character counter during editing: "123 / 500"

## Data Schema

```sql
-- New table: watchlist_stock_notes
CREATE TABLE watchlist_stock_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id UUID NOT NULL REFERENCES watchlist(watchlist_id) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL,
    note_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Composite unique constraint
    UNIQUE(watchlist_id, ticker)
);
```

## API Endpoints

### Get Notes for Stock
```
GET /api/stock/{ticker}/notes
```
Returns all notes for this ticker across user's watchlists.

Response:
```json
{
  "ticker": "AAPL",
  "notes": [
    {
      "watchlist_id": "uuid",
      "watchlist_name": "Growth Portfolio",
      "note_text": "Strong iPhone sales expected...",
      "updated_at": "2026-01-29T10:30:00Z"
    }
  ]
}
```

### Create/Update Note
```
POST /api/watchlist/{watchlist_id}/stock/{ticker}/note
```
Body:
```json
{
  "note_text": "My research notes..."
}
```

### Delete Note
```
DELETE /api/watchlist/{watchlist_id}/stock/{ticker}/note
```

## UI Mockup

```
┌─────────────────────────────────────────────────────────┐
│ AAPL - Stock Details                              [⟳]  │
├─────────────────────────────────────────────────────────┤
│ [Covered Calls] [RRR] [Notes]                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Growth Portfolio                        [Edit]  │   │
│  ├─────────────────────────────────────────────────┤   │
│  │ Strong Q4 expected. Watch for services         │   │
│  │ revenue growth. Consider adding on dips        │   │
│  │ below $250.                                    │   │
│  │                                                 │   │
│  │ Last updated: Jan 29, 2026                     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Dividend Portfolio                      [Edit]  │   │
│  ├─────────────────────────────────────────────────┤   │
│  │ No notes yet                      [Add Note]   │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Implementation Notes

1. **Authentication Required**: All note operations require user authentication
2. **Ownership Validation**: Users can only view/edit notes for their own watchlists
3. **Cascade Delete**: When a watchlist is deleted, all associated notes are deleted
4. **Cascade Delete (Stock)**: When a stock is removed from a watchlist, its note is deleted
5. **No Version History**: Only current note is stored (with timestamp)

## Out of Scope (Future Enhancements)

- Rich text / Markdown formatting
- Full version history
- Note search across all stocks
- Note templates
- Sharing notes between users
- Price targets or structured fields
- Notes visible in watchlist table view
