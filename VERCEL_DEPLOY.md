# Deploying Sabi Operations Dashboard to Vercel

## Quick Deploy

### Option 1: Deploy via Vercel CLI (Recommended)

1. **Install Vercel CLI**:
   ```bash
   npm i -g vercel
   ```

2. **Login to Vercel**:
   ```bash
   vercel login
   ```

3. **Deploy from workspace root**:
   ```bash
   cd /workspace
   vercel
   ```

4. **Follow prompts**:
   - Set up and deploy? **Y**
   - Which scope? Choose your account
   - Link to existing project? **N**
   - Project name? `sabi-operations`
   - Directory? `./` (workspace root)
   - Override settings? **N**

5. **Set environment variable**:
   ```bash
   vercel env add VITE_API_URL production
   ```
   Then paste your backend URL (e.g., `https://api.sabi.org`)

6. **Deploy to production**:
   ```bash
   vercel --prod
   ```

### Option 2: Deploy via Vercel Dashboard

1. **Go to [vercel.com](https://vercel.com)** and sign in

2. **Click "Add New" → "Project"**

3. **Import your GitHub repository**:
   - Select `thegirwhocodes/sabi-server`
   - Branch: `cursor/operational-dashboard-0f38`

4. **Configure Project**:
   - **Framework Preset**: Vite
   - **Root Directory**: `./` (leave as workspace root)
   - **Build Command**: `cd dashboard && npm install && npm run build`
   - **Output Directory**: `dashboard/dist`

5. **Add Environment Variables**:
   - Key: `VITE_API_URL`
   - Value: Your backend URL (e.g., `https://api.sabi.org`)

6. **Click "Deploy"**

## Configuration Files Added

- ✅ `vercel.json` - Vercel configuration with API rewrites
- ✅ `dashboard/.env.production` - Production environment template
- ✅ Updated `vite.config.ts` - Build optimizations

## After Deployment

Your dashboard will be live at: `https://sabi-operations.vercel.app`

### Configure Custom Domain (Optional)

1. In Vercel dashboard, go to your project
2. Settings → Domains
3. Add your domain (e.g., `operations.sabi.org`)
4. Follow DNS instructions

## Backend Setup

**Important**: Your backend API needs to be deployed separately. Options:

### Option A: Deploy Backend to Fly.io (Recommended)
```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Deploy from workspace root
fly launch
fly deploy
```

### Option B: Deploy Backend to Railway
1. Go to [railway.app](https://railway.app)
2. New Project → Deploy from GitHub
3. Select your repo
4. Railway auto-detects Python/FastAPI

### Option C: Keep Backend on Current Server
- Update `VITE_API_URL` in Vercel to point to your current backend
- Ensure CORS is configured to allow Vercel domain

## CORS Configuration

Add to `main.py`:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sabi-operations.vercel.app",
        "https://operations.sabi.org",  # your custom domain
        "http://localhost:3000",  # development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Monitoring

- **Vercel Dashboard**: Monitor deployments, analytics, and logs
- **Real-time Updates**: Push to GitHub → Auto-deploys to Vercel

## Troubleshooting

### Build fails
- Check `vercel.json` paths are correct
- Ensure `dashboard/package.json` exists
- Run `cd dashboard && npm install && npm run build` locally first

### API requests fail
- Verify `VITE_API_URL` is set in Vercel environment variables
- Check CORS configuration on backend
- Ensure backend is publicly accessible

### Blank page after deploy
- Check browser console for errors
- Verify `dashboard/dist/index.html` was generated
- Check Vercel function logs

## Cost

- **Vercel**: Free for hobby projects (plenty for this dashboard)
- **Fly.io/Railway**: ~$5-10/month for backend

## Need Help?

- Vercel Docs: https://vercel.com/docs
- Vercel Support: support@vercel.com
