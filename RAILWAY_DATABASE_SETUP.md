# Connecting PostgreSQL Database to Your Railway App

## ✅ Good News: It's Already Configured!

Your app is already set up to automatically use Railway's PostgreSQL database! Here's how it works:

## How Railway Database Connection Works

### 1. Railway Automatically Provides DATABASE_URL

When you add a PostgreSQL service to your Railway project:
- Railway **automatically creates** a `DATABASE_URL` environment variable
- This variable contains the connection string to your PostgreSQL database
- Your app automatically uses it (no manual configuration needed!)

### 2. Your App is Already Configured

Your `app/database.py` is already set up to:
- ✅ Read `DATABASE_URL` from environment variables
- ✅ Convert `postgres://` to `postgresql://` (if needed)
- ✅ Use PostgreSQL when `DATABASE_URL` is set
- ✅ Fall back to SQLite for local development

## Verify the Connection

### Step 1: Check Environment Variables in Railway

1. **Go to Railway Dashboard**
   - Navigate to your `arthos-app` project

2. **Check Your Web Service**
   - Click on your web service (FastAPI app)
   - Go to **Settings** → **Variables**
   - You should see `DATABASE_URL` automatically set
   - It will look like: `postgresql://user:password@host:port/database`

3. **Check PostgreSQL Service**
   - Click on your PostgreSQL service
   - Go to **Settings** → **Variables**
   - You'll see the connection details there

### Step 2: Verify Database Connection in App

1. **Check Application Logs**
   - Railway Dashboard → Your Service → **Deployments**
   - Click on latest deployment → **Logs**
   - Look for database connection messages
   - Should see successful connection

2. **Test the App**
   - Visit your app URL
   - Try creating a watchlist or adding stocks
   - If it works, the database is connected!

### Step 3: Verify Database Tables Are Created

Your app automatically creates tables on startup. Check logs for:
```
Added cache_version column to stockcache table
```

Or check the database directly (if you have access).

## How It Works

### Database Configuration Flow

1. **Railway provides `DATABASE_URL`**
   ```
   DATABASE_URL=postgresql://user:pass@host:port/dbname
   ```

2. **Your app reads it** (in `app/database.py`):
   ```python
   DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///arthos.db")
   ```

3. **App connects automatically**
   - On startup, `create_db_and_tables()` runs
   - Tables are created in PostgreSQL
   - App uses PostgreSQL for all operations

## Troubleshooting

### Database Not Connected?

1. **Check if PostgreSQL Service is Running**
   - Railway Dashboard → PostgreSQL service
   - Ensure it's "Active" or "Running"

2. **Check if DATABASE_URL is Set**
   - Web Service → Settings → Variables
   - Look for `DATABASE_URL`
   - If missing, Railway should auto-create it when services are linked

3. **Check Application Logs**
   - Look for database connection errors
   - Common issues:
     - Connection timeout
     - Authentication failure
     - Network issues

### Database Connection Errors?

1. **Check Logs**
   - Railway Dashboard → Deployments → Latest → Logs
   - Look for SQLAlchemy or database errors

2. **Verify Service Linking**
   - Railway automatically links services in the same project
   - `DATABASE_URL` should be automatically available

3. **Restart the Service**
   - Sometimes a restart helps
   - Railway Dashboard → Your Service → Settings → Restart

## Manual Verification (Optional)

If you want to verify the connection manually:

1. **Check Railway Logs**
   - Look for successful database connection messages
   - Should see table creation messages

2. **Test Database Operations**
   - Create a watchlist in your app
   - Add stocks to watchlist
   - If these work, database is connected!

3. **Check Database Directly** (if you have Railway CLI)
   ```bash
   railway connect postgres
   # Then run SQL queries to check tables
   ```

## What Happens on Deployment

1. **Railway starts your app**
2. **App reads `DATABASE_URL`** from environment
3. **App connects to PostgreSQL**
4. **Tables are created automatically** (if they don't exist)
5. **App is ready to use!**

## Summary

✅ **Your app is already configured** to use PostgreSQL  
✅ **Railway automatically provides** `DATABASE_URL`  
✅ **No manual configuration needed**  
✅ **Just verify it's working** by using your app!

Your database should be connected automatically. Just test your app to confirm!

