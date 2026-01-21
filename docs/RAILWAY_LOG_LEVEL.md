# Railway LOG_LEVEL Configuration Guide

## Quick Reference

**Enable DEBUG logging in Railway:**
1. Go to your Railway project
2. Navigate to Variables tab
3. Add variable: `LOG_LEVEL` = `DEBUG`
4. Railway will auto-restart with DEBUG logs enabled

**Disable DEBUG logging:**
1. Remove the `LOG_LEVEL` variable (or set to `INFO`)
2. Railway will auto-restart back to INFO level

## How It Works

The application now reads the `LOG_LEVEL` environment variable on startup:
- **Default**: `INFO` (normal production logging)
- **DEBUG**: Detailed logs including all scheduler debug statements
- **WARNING**: Only warnings and errors
- **ERROR**: Only errors

## Example: Debugging Scheduler in Railway

### Step 1: Enable DEBUG Logs
1. Open Railway dashboard
2. Select your Arthos project
3. Go to **Variables** tab
4. Click **+ New Variable**
5. Set:
   - Variable: `LOG_LEVEL`
   - Value: `DEBUG`
6. Click **Add**
7. Railway will automatically restart the service

### Step 2: View Scheduler Logs
1. Go to **Deployments** tab
2. Click on the latest deployment
3. View logs - you'll now see detailed scheduler debug logs:
   ```
   INFO:     app.main - Logging configured at DEBUG level
   DEBUG:    app.services.scheduler_service - Creating scheduler_log entry in database...
   DEBUG:    app.services.scheduler_service - Market hours check:
   DEBUG:    app.services.scheduler_service -   Current ET time: 2026-01-20 10:30:15 EST
   DEBUG:    app.services.scheduler_service -   Querying database for watchlist tickers...
   ```

### Step 3: Disable DEBUG Logs (After Debugging)
1. Go back to **Variables** tab
2. Find `LOG_LEVEL` variable
3. Click the **X** to remove it (or change value to `INFO`)
4. Railway will restart with INFO level logging

## What You'll See at Each Level

### INFO Level (Default)
- Scheduler initialization
- Job triggers
- Database operations (inserts/updates)
- Completion summaries
- Errors and warnings

### DEBUG Level (On-Demand)
All of the above PLUS:
- Database query details
- Market hours calculations
- Individual ticker processing steps
- Detailed skip reasons
- Stack traces for all exceptions

## Local Development

For local development, you can also use the environment variable:

```bash
# Enable DEBUG logs locally
LOG_LEVEL=DEBUG python run.py

# Or add to .env file
echo "LOG_LEVEL=DEBUG" >> .env
python run.py
```

## Verification

After setting `LOG_LEVEL=DEBUG` in Railway, you should see this on startup:
```
INFO:     app.main - Logging configured at DEBUG level
```

This confirms the environment variable is being read correctly.
