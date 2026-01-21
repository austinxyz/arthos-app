# Setting Up GitHub Secrets for Railway Deployment

## Step-by-Step Guide

### Step 1: Find Your Railway Service ID

The Service ID is different from the Project ID. Here's how to find it:

#### Option A: Via Railway Dashboard (Easiest)

1. Go to your Railway project dashboard
2. Click on your **web service** (the service running your FastAPI app)
3. Click on **Settings** (gear icon)
4. Look for **Service ID** - it's a UUID like `abc123-def456-...`
5. Copy this Service ID

#### Option B: Via Railway CLI

```bash
# Install Railway CLI (if not already installed)
npm i -g @railway/cli

# Login
railway login

# Link to your project
railway link

# Get service ID
railway status
# Or
railway service
```

#### Option C: Check Railway API

If you have the Project ID, you can also use that - Railway's API will resolve it. But Service ID is more specific.

**Note**: If you only have one service in your project, the Project ID might work, but Service ID is recommended.

### Step 2: Add GitHub Secrets

1. **Go to Your GitHub Repository**
   - Navigate to: `https://github.com/YOUR_USERNAME/arthos-app`
   - (Replace `YOUR_USERNAME` with your actual GitHub username)

2. **Open Repository Settings**
   - Click on **Settings** tab (top menu bar)
   - In the left sidebar, click **Secrets and variables** → **Actions**

3. **Add RAILWAY_TOKEN Secret**
   - Click **New repository secret** button
   - Name: `RAILWAY_TOKEN`
   - Value: Paste your Railway API token
   - Click **Add secret**

4. **Add RAILWAY_SERVICE_ID Secret**
   - Click **New repository secret** button again
   - Name: `RAILWAY_SERVICE_ID`
   - Value: Paste your Railway Service ID (or Project ID if Service ID not available)
   - Click **Add secret**

### Step 3: Verify Secrets Are Added

You should now see two secrets listed:
- ✅ `RAILWAY_TOKEN`
- ✅ `RAILWAY_SERVICE_ID`

### Step 4: Test the Deployment

1. **Make a small change** (or just push existing changes)
   ```bash
   git add .
   git commit -m "Add Railway deployment configuration"
   git push origin main
   ```

2. **Check GitHub Actions**
   - Go to your GitHub repo → **Actions** tab
   - You should see a workflow run starting
   - It will:
     - Run all tests
     - Deploy to Railway if tests pass

3. **Check Railway Dashboard**
   - Go to Railway → Your Project
   - Check the **Deployments** tab
   - You should see a new deployment starting

## Troubleshooting

### "Service ID not found" Error

If the Service ID doesn't work, try:
1. Use the **Project ID** instead (Railway API can resolve it)
2. Or find the Service ID via Railway CLI:
   ```bash
   railway service
   ```

### "Invalid token" Error

1. Verify the token is correct (no extra spaces)
2. Make sure the token has the right permissions
3. Create a new token if needed

### Deployment Not Triggering

1. Check that you pushed to `main` branch
2. Verify GitHub Actions is enabled (Settings → Actions → General)
3. Check the Actions tab for any errors

## Alternative: Manual Deployment

If you want to deploy manually without CI/CD:

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to your project
railway link

# Deploy
railway up
```

## Next Steps

Once secrets are added:
1. ✅ Push to `main` branch
2. ✅ Watch GitHub Actions run tests
3. ✅ Railway automatically deploys on success
4. ✅ Access your app at `https://your-app.up.railway.app`

