# Vercel Deployment - Quick Start

## 🚀 Deploy Right Now

### Fastest Way (5 minutes):

```bash
# 1. Install Vercel CLI
npm i -g vercel

# 2. Login
vercel login

# 3. Deploy from workspace root
cd /workspace
vercel

# 4. Set your backend URL
vercel env add VITE_API_URL production
# Enter: https://your-backend.com (or keep localhost:8000 for testing)

# 5. Deploy to production
vercel --prod
```

**Done!** Your dashboard will be live at `https://sabi-operations.vercel.app`

---

## 🔧 What I've Set Up

- ✅ `vercel.json` - Auto-configured for your dashboard
- ✅ `dashboard/.env.production` - Environment template
- ✅ Updated `vite.config.ts` - Production build optimization
- ✅ Added `vercel-build` script to package.json

## 📝 Important: Backend Setup

Your **frontend** will be on Vercel, but your **backend** (FastAPI) needs to be accessible.

**Three options:**

1. **Keep it on your current server** - Just set `VITE_API_URL` to your server URL
2. **Deploy backend to Fly.io** - Free tier, perfect for FastAPI
3. **Deploy backend to Railway** - Auto-detects Python, easy setup

See `VERCEL_DEPLOY.md` for detailed backend deployment guides.

## 🔐 CORS (Important!)

Add this to your `main.py` backend:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sabi-operations.vercel.app",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 💰 Cost

- **Vercel**: FREE (hobby tier is perfect for this)
- **Backend hosting**: ~$5-10/month (Fly.io or Railway)

---

Need the full guide? See `VERCEL_DEPLOY.md`
