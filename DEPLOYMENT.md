# Deployment Guide - Railway

This guide explains how to deploy the Arthos application to Railway and set up automated CI/CD.

## Prerequisites

1. A Railway account (sign up at [railway.app](https://railway.app))
2. A GitHub account with your repository
3. Railway CLI (optional, for local testing)

## Quick Start

### 1. Deploy to Railway

#### Option A: Deploy via Railway Dashboard (Recommended)

1. **Sign in to Railway**
   - Go to [railway.app](https://railway.app) and sign in with GitHub

2. **Create a New Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

3. **Add PostgreSQL Database**
   - In your Railway project, click "+ New"
   - Select "Database" → "Add PostgreSQL"
   - Railway will automatically create a `DATABASE_URL` environment variable

4. **Configure Environment Variables**
   - Railway automatically detects `DATABASE_URL` from the PostgreSQL service
   - No additional configuration needed for basic setup

5. **Deploy**
   - Railway will automatically detect the `Procfile` and deploy
   - Your app will be live at `https://your-app-name.up.railway.app`

#### Option B: Deploy via Railway CLI

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Link to existing project (if you created one in dashboard)
railway link

# Deploy
railway up
```

### 2. Set Up Automated CI/CD

#### Step 1: Get Railway Token

1. Go to Railway Dashboard → Account Settings → Tokens
2. Create a new token
3. Copy the token

#### Step 2: Get Service ID

1. In your Railway project, go to Settings
2. Copy the "Service ID"

#### Step 3: Add GitHub Secrets

1. Go to your GitHub repository → Settings → Secrets and variables → Actions
2. Add the following secrets:
   - `RAILWAY_TOKEN`: Your Railway token from Step 1
   - `RAILWAY_SERVICE_ID`: Your service ID from Step 2

#### Step 4: Push to Main

The GitHub Actions workflow (`.github/workflows/ci-cd.yml`) will:
1. Run all tests on every push/PR
2. Deploy to Railway automatically when tests pass on `main` branch

## Local Development

### Setup

1. **Copy environment file**
   ```bash
   cp .env.example .env
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python run.py
   # Or
   uvicorn app.main:app --reload
   ```

4. **Run tests**
   ```bash
   # All tests
   pytest tests/ -v
   
   # Unit tests only
   pytest tests/ -v -k "not browser"
   
   # Browser tests (requires server running)
   pytest tests/ -v -k "browser"
   ```

### Database Options

#### SQLite (Default for Local Development)

No setup needed. The app will create `arthos.db` automatically.

#### PostgreSQL (Recommended for Production-like Testing)

1. Install PostgreSQL locally or use Docker:
   ```bash
   docker run --name postgres-dev -e POSTGRES_PASSWORD=dev_password -e POSTGRES_DB=arthos_db -p 5432:5432 -d postgres:15
   ```

2. Update `.env`:
   ```
   DATABASE_URL=postgresql://postgres:dev_password@localhost:5432/arthos_db
   ```

## Workflow

### Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes and test locally**
   ```bash
   # Run tests
   pytest tests/ -v
   
   # Start server
   python run.py
   ```

3. **Commit and push**
   ```bash
   git add .
   git commit -m "Add feature"
   git push origin feature/my-feature
   ```

4. **Create Pull Request**
   - GitHub Actions will run tests automatically
   - Once tests pass, merge to `main`

5. **Automatic Deployment**
   - When merged to `main`, tests run again
   - If tests pass, Railway automatically deploys

### Manual Deployment

If you need to deploy manually:

```bash
# Using Railway CLI
railway up

# Or trigger via GitHub Actions
# Push an empty commit to main
git commit --allow-empty -m "Trigger deployment"
git push origin main
```

## Environment Variables

### Required (Auto-configured by Railway)

- `DATABASE_URL`: Automatically set by Railway when you add PostgreSQL

### Optional

- `ECHO_SQL`: Set to `"true"` to see SQL queries in logs (default: `"false"`)
- `PORT`: Railway sets this automatically (default: `8000`)

## Monitoring

### Railway Dashboard

- View logs: Railway Dashboard → Your Service → Logs
- View metrics: Railway Dashboard → Your Service → Metrics
- View deployments: Railway Dashboard → Your Service → Deployments

### Application Health

- Health check endpoint: `https://your-app.up.railway.app/` (homepage)
- API docs: `https://your-app.up.railway.app/docs` (FastAPI auto-generated)

## Troubleshooting

### Database Connection Issues

1. **Check DATABASE_URL**
   - Railway automatically provides this
   - Verify in Railway Dashboard → Variables

2. **Check PostgreSQL Service**
   - Ensure PostgreSQL service is running in Railway
   - Check logs for connection errors

### Deployment Failures

1. **Check Build Logs**
   - Railway Dashboard → Deployments → View logs

2. **Check Test Failures**
   - GitHub Actions → Workflow runs → View failed tests

3. **Common Issues**
   - Missing dependencies in `requirements.txt`
   - Database migration errors
   - Port configuration issues

### Local Development Issues

1. **Database not found**
   - Ensure `.env` file exists with `DATABASE_URL`
   - For SQLite, ensure write permissions in project directory

2. **Tests failing locally**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - For browser tests, ensure Playwright is installed: `playwright install`

## Best Practices

1. **Always test locally before pushing**
   ```bash
   pytest tests/ -v
   ```

2. **Use feature branches**
   - Never push directly to `main`
   - Create PRs for code review

3. **Monitor deployments**
   - Check Railway logs after deployment
   - Verify application is accessible

4. **Keep dependencies updated**
   - Regularly update `requirements.txt`
   - Test updates before deploying

5. **Database migrations**
   - The app handles schema migrations automatically
   - For major changes, test migrations locally first

## Cost Considerations

### Railway Pricing

- **Hobby Plan**: $5/month (includes $5 credit)
- **Pro Plan**: $20/month (includes $20 credit)
- **Pay-as-you-go**: Additional usage beyond credits

### Cost Optimization

- Use PostgreSQL only when needed (Railway provides free tier)
- Monitor usage in Railway Dashboard
- Consider using SQLite for development/testing

## Support

- Railway Docs: [docs.railway.app](https://docs.railway.app)
- Railway Discord: [discord.gg/railway](https://discord.gg/railway)
- GitHub Issues: Create an issue in your repository

