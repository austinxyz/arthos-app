#!/bin/bash
# Production verification script
# Runs automated checks after deployment

set -e

echo "=================================================="
echo "🔍 PRODUCTION VERIFICATION"
echo "=================================================="
echo ""

# Check 1: Production site is accessible
echo "✓ Check 1: Site accessibility..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://my.arthos.app/)
if [ "$STATUS" -eq 200 ]; then
    echo "  ✅ Site is UP (Status: $STATUS)"
else
    echo "  ❌ Site returned status: $STATUS"
    exit 1
fi

# Check 2: Railway logs for errors
echo ""
echo "✓ Check 2: Checking Railway logs for errors..."
ERRORS=$(/opt/homebrew/bin/railway logs --json 2>&1 | tail -100 | grep -c "ERROR\|Exception\|Traceback\|500 Internal" || true)
if [ "$ERRORS" -eq 0 ]; then
    echo "  ✅ No errors found in recent logs"
else
    echo "  ⚠️  Found $ERRORS potential error lines in logs"
    echo "  Run: railway logs --json | tail -100 | grep -E 'ERROR|Exception'"
fi

# Check 3: Critical endpoints
echo ""
echo "✓ Check 3: Verifying critical endpoints..."

# Home page
if curl -s https://my.arthos.app/ | grep -q "Arthos"; then
    echo "  ✅ Home page loads"
else
    echo "  ❌ Home page issue"
fi

# Watchlists page (redirects to login for unauthenticated)
WATCHLIST_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://my.arthos.app/watchlists)
if [ "$WATCHLIST_STATUS" -eq 307 ] || [ "$WATCHLIST_STATUS" -eq 200 ]; then
    echo "  ✅ Watchlists endpoint responding (Status: $WATCHLIST_STATUS)"
else
    echo "  ❌ Watchlists endpoint status: $WATCHLIST_STATUS"
fi

# API health check (if you have one)
# HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://my.arthos.app/health)

echo ""
echo "=================================================="
echo "✅ PRODUCTION VERIFICATION COMPLETE"
echo "=================================================="
echo ""
echo "Next: Manual verification of changed functionality"
echo "      Login at: https://my.arthos.app"
echo "      Test account: arthos.test@gmail.com"
