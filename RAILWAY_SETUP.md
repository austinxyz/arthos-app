# Railway Deployment Setup - Quick Reference

## Files Created/Modified

### ✅ Configuration Files
- `Procfile` - Railway deployment command
- `railway.json` - Railway build configuration
- `.railwayignore` - Files to exclude from deployment
- `.github/workflows/ci-cd.yml` - Automated CI/CD pipeline

### ✅ Code Changes
- `app/database.py` - Updated to support PostgreSQL via `DATABASE_URL` environment variable
- `requirements.txt` - Added `psycopg2-binary` for PostgreSQL support

### ✅ Documentation
- `DEPLOYMENT.md` - Complete deployment guide

## Quick Start Steps

### 1. Initial Railway Setup

1. **Sign up/Login to Railway**
   - Go to https://railway.app
   - Sign in with GitHub

2. **Create New Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your `arthos-app` repository

3. **Add PostgreSQL Database**
   - In Railway project, click "+ New"
   - Select "Database" → "Add PostgreSQL"
   - Railway automatically creates `DATABASE_URL` environment variable

4. **Deploy**
   - Railway auto-detects your `Procfile` and deploys
   - Your app will be live at `https://your-app-name.up.railway.app`

### 2. Set Up Automated CI/CD

1. **Get Railway Token**
   - Railway Dashboard → Account Settings → Tokens
   - Create new token and copy it

2. **Get Service ID**
   - Railway Dashboard → Your Project → Settings
   - Copy the "Service ID"

3. **Add GitHub Secrets**
   - GitHub Repo → Settings → Secrets and variables → Actions
   - Add secret: `RAILWAY_TOKEN` (your Railway token)
   - Add secret: `RAILWAY_SERVICE_ID` (your service ID)

4. **Test the Pipeline**
   - Push a commit to `main` branch
   - GitHub Actions will:
     - Run all tests
     - Deploy to Railway if tests pass

## Local Development

### Environment Setup

Create a `.env` file in the project root:

```bash
# For SQLite (local development)
DATABASE_URL=sqlite:///arthos.db
ECHO_SQL=false
PORT=8000
```

### Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python run.py
# Or
uvicorn app.main:app --reload
```

### Run Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/ -v -k "not browser"

# Browser tests (requires server running on port 8000)
pytest tests/ -v -k "browser"
```

## Workflow

### Development Workflow

1. **Create feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes and test locally**
   ```bash
   pytest tests/ -v
   python run.py
   ```

3. **Commit and push**
   ```bash
   git add .
   git commit -m "Add feature"
   git push origin feature/my-feature
   ```

4. **Create Pull Request**
   - GitHub Actions runs tests automatically
   - Review and merge when ready

5. **Automatic Deployment**
   - When merged to `main`, tests run again
   - If tests pass → Railway automatically deploys

## Environment Variables

### Railway (Auto-configured)
- `DATABASE_URL` - Automatically set by Railway PostgreSQL service
- `PORT` - Automatically set by Railway

### Optional (Set in Railway Dashboard if needed)
- `ECHO_SQL` - Set to `"true"` to see SQL queries in logs

## Database Migration

The app automatically handles:
- SQLite → PostgreSQL compatibility
- Schema migrations (cache_version column)
- Database connection pooling

No manual migration needed - just deploy!

## Troubleshooting

### Database Connection Issues
- Check Railway Dashboard → Variables → `DATABASE_URL` exists
- Verify PostgreSQL service is running

### Deployment Failures
- Check Railway Dashboard → Deployments → View logs
- Check GitHub Actions → Workflow runs for test failures

### Local Issues
- Ensure `.env` file exists with `DATABASE_URL`
- Run `pip install -r requirements.txt` to ensure all dependencies

## Next Steps

1. ✅ Deploy to Railway (follow Quick Start above)
2. ✅ Set up CI/CD (add GitHub secrets)
3. ✅ Test the deployment
4. ✅ Monitor in Railway Dashboard

For detailed information, see `DEPLOYMENT.md`.

