# Deploying Co-Founder Agent to Vercel

Your Co-Founder Agent now has a beautiful web interface! Here's how to deploy it.

## What You Got

### Web Dashboard Features:
- 📊 **Visual Dashboard** - See goals, tasks, opportunities at a glance
- 📈 **Progress Tracking** - Visual progress bars for each goal
- 🎯 **Next Actions** - Prioritized list of what to do next
- ✅ **Accountability Score** - Track your commitment completion rate
- 🔄 **Auto-refresh** - Updates every 30 seconds
- 📱 **Responsive** - Works on desktop and mobile

### API Endpoints:
- `GET /` - Dashboard homepage
- `GET /api/dashboard` - Complete dashboard data
- `GET /api/checkin` - Perform check-in
- `GET /api/goals` - List goals
- `POST /api/goals` - Create goal
- `GET /api/goals/{id}` - Get goal details with insights
- `GET /api/tasks` - List tasks
- `POST /api/tasks` - Create task
- `PATCH /api/tasks/{id}` - Update task
- `GET /api/opportunities` - List opportunities
- `POST /api/opportunities` - Create opportunity
- `GET /api/commitments` - List commitments
- `POST /api/commitments` - Create commitment
- `GET /api/next-actions` - Get next actions
- `GET /api/report` - Get weekly report

## Test Locally First

```bash
cd /workspace/cofounder_agent
python3 api.py
```

Then visit: http://localhost:8001

You should see your Co-Founder Agent dashboard!

## Deploy to Vercel

### Option 1: Using Vercel CLI (Recommended)

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy from workspace root
cd /workspace
vercel --prod

# Or with token
vercel --token YOUR_VERCEL_TOKEN --prod
```

### Option 2: Using GitHub + Vercel Dashboard

1. **Push to GitHub** (already done!)
   ```bash
   git push origin cursor/cofounder-agent-c729
   ```

2. **Import in Vercel**:
   - Go to [vercel.com](https://vercel.com)
   - Click "Add New Project"
   - Import `thegirwhocodes/sabi-server`
   - Select the `cursor/cofounder-agent-c729` branch
   - Framework Preset: **Other**
   - Root Directory: **.**
   - Build Command: (leave empty)
   - Output Directory: (leave empty)
   - Click **Deploy**

3. **Configure Environment** (if needed):
   - No environment variables needed for basic deployment
   - Data will be stored in Vercel's serverless environment

### Option 3: Manual Deployment

```bash
# From workspace root
vercel --token YOUR_VERCEL_TOKEN
```

## After Deployment

Once deployed, you'll get a URL like:
```
https://sabi-server-xxx.vercel.app
```

Visit that URL to see your Co-Founder Agent dashboard!

## Data Persistence Note

⚠️ **Important**: The Vercel deployment will create a new data directory on each deployment. For production use, you'll want to:

1. **Use a database** (Supabase, MongoDB, etc.) instead of JSON files
2. **Mount persistent storage** (Vercel Blob or external service)
3. **Keep using CLI locally** for now with local JSON storage

For immediate use, the web interface works great for **viewing** your data, but **continue using the CLI for creating** goals/tasks until we add database persistence.

## Architecture

```
┌─────────────────────────────────────┐
│         Vercel Deployment            │
├─────────────────────────────────────┤
│                                      │
│  ┌────────────────────────────────┐ │
│  │   FastAPI Backend (api.py)     │ │
│  │  - REST API endpoints          │ │
│  │  - Co-Founder Agent integration│ │
│  └────────────────────────────────┘ │
│              │                       │
│              ▼                       │
│  ┌────────────────────────────────┐ │
│  │   Static Frontend (HTML/CSS/JS)│ │
│  │  - Beautiful dashboard         │ │
│  │  - Real-time updates           │ │
│  └────────────────────────────────┘ │
│                                      │
└─────────────────────────────────────┘
           │
           ▼
   ┌──────────────┐
   │ JSON Storage │
   │ (local files)│
   └──────────────┘
```

## Troubleshooting

### "Module not found" errors
Make sure `vercel.json` is in the workspace root and points to the correct path.

### "No such file" for JSON data
The data files are created on first use. Initialize by running CLI commands first:
```bash
python3 cofounder_agent/cli.py dashboard
```

### API not responding
Check the Vercel deployment logs:
```bash
vercel logs YOUR_DEPLOYMENT_URL
```

## Next Steps

To make this production-ready:

1. **Add Database Backend**
   - Replace JSON files with Supabase/PostgreSQL
   - Update `agent_memory.py`, `goal_manager.py`, etc.

2. **Add Authentication**
   - Add login system
   - Protect API endpoints
   - User-specific data

3. **Add Forms**
   - Build web forms to create goals/tasks/opportunities
   - Currently shows placeholder alert

4. **Add Real-time Notifications**
   - WebSocket for live updates
   - Push notifications for deadlines

5. **Mobile App**
   - React Native or PWA
   - Push reminders to phone

## Current Limitations

- ✅ Beautiful dashboard view
- ✅ Real-time data display
- ✅ Progress visualization
- ⚠️ Forms show placeholder (use CLI for now)
- ⚠️ Data stored in local JSON (not persistent on Vercel)
- ⚠️ No authentication yet

## Best Use

For now, the best workflow is:

1. **Use CLI locally** to manage goals/tasks/opportunities
2. **Deploy web dashboard** to view progress anywhere
3. **Share the URL** with team members to show status

The web interface provides a beautiful way to **view** your operational status, while the CLI remains the primary way to **manage** it.

## Questions?

Check the main docs:
- `cofounder_agent/README.md` - Complete system documentation
- `cofounder_agent/QUICKSTART.md` - CLI usage guide
- `COFOUNDER_INTEGRATION.md` - Integration guide
