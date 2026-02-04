# Capability to add notes to a stock per account 

This feature allows addition of notes for future reference for a stock from various entry points.
- When it is added to a watch list.
- stock details page.


## Model changes
Create a new model called watchlist_stock_note with the following fields:
- watchlist_stock_id (foreign key to watchlist_stock)
- account_id (foreign key to account)
- note (text)
- date_added (timestamp)

When a note is added from the two entry points, create a new watchlist_stock_note record.
Create the indexes to support the faster retrieval of notes for a stock.

## API Changes
Create a new endpoint for CRUD operations on watchlist_stock_note.

## Display
The notes are stored per account per stock and add a tab in the stock details page left of Covered Calls as "Notes".
On clicking this tab, provide a bullet list of the notes for the stock as bullet list.
The bullet point should start with a grayed out date of the timestamp of the watchlist_stock_note in yyyy-MM-dd format, followed by a column and the note.

## UI changes
- Add a text box when adding a stock to the watchlist and stock details page to capture notes and save it in the watchlist_stock_note table.
- Add a text box when seeing the notes tab to add a new note and save it in the watchlist_stock_note table. Refresh the notes upon saving the new note from this page.

## Testing
- Test adding a note from the watchlist and stock details page.
- Test adding a note from the notes tab.
- Test deleting a note from the notes tab.
- Update existing test cases to handle this change.
- Testing should include both backend testing, API testing and UI testing.

