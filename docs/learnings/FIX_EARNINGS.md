# Fix for Earnings Data Not Showing

## Problem
Earnings dates show "N/A" even though the code is working correctly.

## Root Cause
The server is either:
1. Using a different database file (different working directory)
2. Has the database file locked and hasn't seen the cleared data
3. Needs to be restarted to pick up changes

## Solution

### Step 1: Stop the Server
```bash
# Find and kill the server process
pkill -f "python.*run.py"
# Or find the PID:
ps aux | grep "python.*run.py"
# Then kill it:
kill <PID>
```

### Step 2: Clear the Database
```bash
python3 clear_database.py
```

### Step 3: Verify Database is Empty
```bash
python3 debug_database.py
```

### Step 4: Restart the Server
```bash
python run.py
```

### Step 5: Test in Fresh Browser
1. Open browser in **incognito/private mode** (to avoid cache)
2. Go to `http://localhost:8000`
3. Create a new watchlist
4. Add "JPM" as a stock
5. Check if earnings date appears: **Jan 13, 2026**

## If Still Not Working

Run this to see what the server actually sees:
```bash
python3 debug_database.py
```

This will show:
- Which database file is being used
- What watchlists exist
- What earnings data exists for each stock

## Expected Result

After adding JPM, you should see:
- **Next Earnings column**: "Jan 13, 2026"
- **Stock detail page**: "Next Earnings: Jan 13, 2026"

The code is working correctly - the issue is the server needs to see the cleared database.
