# Quick Start: Railway Deployment

## ✅ What You've Done
- [x] Signed up for Railway
- [x] Added PostgreSQL database
- [x] Created API token
- [x] Have Project ID

## 🔧 What You Need to Do Now

### 1. Find Service ID (or use Project ID)

**Option A: Find Service ID (Recommended)**
1. Railway Dashboard → Your Project
2. Click on your **web service** (the one running your app)
3. Click **Settings** (gear icon)
4. Copy the **Service ID** (UUID format)

**Option B: Use Project ID**
- If you can't find Service ID, your Project ID should work
- The workflow can use either

### 2. Add GitHub Secrets

1. **Go to GitHub Repository**
   - Navigate to: `https://github.com/YOUR_USERNAME/arthos-app`
   - Click **Settings** tab

2. **Go to Secrets**
   - Left sidebar: **Secrets and variables** → **Actions**
   - Click **New repository secret**

3. **Add First Secret: RAILWAY_TOKEN**
   ```
   Name: RAILWAY_TOKEN
   Value: [Paste your Railway API token]
   ```
   - Click **Add secret**

4. **Add Second Secret: RAILWAY_SERVICE_ID**
   - Click **New repository secret** again
   ```
   Name: RAILWAY_SERVICE_ID
   Value: [Paste your Service ID or Project ID]
   ```
   - Click **Add secret**

### 3. Verify Secrets

You should see:
- ✅ `RAILWAY_TOKEN`
- ✅ `RAILWAY_SERVICE_ID`

### 4. Test Deployment

Push your changes to trigger deployment:

```bash
git add .
git commit -m "Add Railway deployment setup"
git push origin main
```

Then:
1. Go to GitHub → **Actions** tab
2. Watch the workflow run (tests → deploy)
3. Check Railway Dashboard → **Deployments** tab

## 🎯 Your App Will Be Live At

After deployment, Railway will show your app URL:
```
https://your-app-name.up.railway.app
```

## ❓ Troubleshooting

**Can't find Service ID?**
- Use your Project ID instead - it should work
- Or check Railway Dashboard → Service Settings

**Deployment not working?**
- Verify secrets are spelled exactly: `RAILWAY_TOKEN` and `RAILWAY_SERVICE_ID`
- Check GitHub Actions tab for error messages
- Ensure you pushed to `main` branch

**Need help?**
- See `GITHUB_SECRETS_SETUP.md` for detailed instructions
- See `DEPLOYMENT.md` for full deployment guide

