# Troubleshooting GitHub Actions CI/CD

## How to Get Help

### Option 1: Share Error Messages
1. Go to GitHub → Actions tab
2. Click on the failed workflow run
3. Click on the failed job (e.g., "Run Tests" or "Deploy to Railway")
4. Copy the error message
5. Share it with me and I'll help fix it

### Option 2: Use GitHub CLI (if installed)
```bash
# List recent runs
gh run list

# View latest run details
gh run view

# Watch a running workflow
gh run watch

# View logs
gh run view [RUN_ID] --log
```

## Common Issues & Fixes

### 1. Playwright Installation Issues
**Error**: `playwright: command not found`
**Fix**: Already fixed - Playwright is now in requirements.txt

### 2. Test Failures
**Error**: Tests failing
**Check**:
- Are tests passing locally? Run: `pytest tests/ -v`
- Database connection issues? Check DATABASE_URL in workflow
- Missing dependencies? Check requirements.txt

### 3. Deployment Failures
**Error**: Railway deployment failing
**Check**:
- GitHub Secrets are set correctly:
  - `RAILWAY_TOKEN` - Your Railway API token
  - `RAILWAY_SERVICE_ID` - Your Project/Service ID
- Token has correct permissions
- Service ID is correct

### 4. Database Connection Issues
**Error**: Can't connect to PostgreSQL
**Check**:
- PostgreSQL service is running in workflow
- DATABASE_URL is set correctly
- Database is ready before tests run

## Quick Local Testing

Before pushing, test locally:

```bash
# Run all tests
pytest tests/ -v

# Run unit tests only
pytest tests/ -v -k "not browser"

# Run browser tests (requires server on port 8000)
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
pytest tests/ -v -k "browser"
```

## What I Can Help With

✅ **I can help if you share**:
- Error messages from GitHub Actions
- Workflow file issues
- Test failures
- Configuration problems

❌ **I cannot**:
- Directly access your GitHub Actions
- See your repository secrets
- Access Railway dashboard
- View live workflow runs

## Best Workflow

1. **Test locally first**
   ```bash
   pytest tests/ -v
   ```

2. **Push to GitHub**
   ```bash
   git push origin main
   ```

3. **Check Actions tab**
   - Go to GitHub → Actions
   - Watch the workflow run

4. **If it fails**:
   - Copy the error message
   - Share it with me
   - I'll help fix it

5. **Fix and push again**
   - I'll provide the fix
   - You commit and push
   - Workflow runs again

## Proactive Checks

Before pushing, I can:
- ✅ Review workflow file for issues
- ✅ Check requirements.txt completeness
- ✅ Verify test configuration
- ✅ Suggest improvements

Just ask me to review the workflow or check for potential issues!

