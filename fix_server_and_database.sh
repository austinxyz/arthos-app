#!/bin/bash
# Script to stop server, clear database, and provide instructions

echo "=========================================="
echo "FIXING EARNINGS DATA ISSUE"
echo "=========================================="
echo ""

# Step 1: Find and stop server
echo "Step 1: Stopping server..."
SERVER_PIDS=$(ps aux | grep -E "python.*run.py|uvicorn.*main:app" | grep -v grep | awk '{print $2}')
if [ -z "$SERVER_PIDS" ]; then
    echo "  ✓ No server process found"
else
    echo "  Found server PIDs: $SERVER_PIDS"
    for pid in $SERVER_PIDS; do
        kill $pid 2>/dev/null && echo "  ✓ Killed process $pid" || echo "  ⚠️  Could not kill process $pid"
    done
    sleep 2
fi

# Step 2: Check for locked database
echo ""
echo "Step 2: Checking database lock..."
DB_LOCKS=$(lsof arthos.db 2>/dev/null | grep -v COMMAND | wc -l | tr -d ' ')
if [ "$DB_LOCKS" -gt 0 ]; then
    echo "  ⚠️  Database file is locked by $DB_LOCKS process(es)"
    echo "  Run: lsof arthos.db"
    echo "  Then kill those processes"
else
    echo "  ✓ Database file is not locked"
fi

# Step 3: Clear database
echo ""
echo "Step 3: Clearing database..."
python3 clear_database.py

# Step 4: Verify
echo ""
echo "Step 4: Verifying database is empty..."
python3 debug_database.py | tail -10

echo ""
echo "=========================================="
echo "NEXT STEPS:"
echo "=========================================="
echo "1. Start the server: python run.py"
echo "2. Open browser in INCOGNITO/PRIVATE mode"
echo "3. Create a new watchlist"
echo "4. Add 'JPM' as a stock"
echo "5. Check if earnings date appears: Jan 13, 2026"
echo ""
echo "If you still see old data, the server might be"
echo "using a different database. Check the server logs"
echo "for the DATABASE_URL it's using."
