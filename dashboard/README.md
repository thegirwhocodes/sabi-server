# Sabi Operations Dashboard

Comprehensive operational dashboard for running Education for Equality / Sabi.

## Features

### Core Modules

1. **Mission Control** - Real-time operational metrics and system health
2. **Student Operations** - Student lifecycle management and cohort tracking
3. **Learning Analytics** - Outcomes tracking and intervention triggers
4. **Call Quality & Safety** - Enhanced QA workflow with safeguarding
5. **Financial Operations** - Cost tracking, burn rate, and ROI analysis
6. **Team Management** - Staff capacity and role-based access control
7. **Research & Evidence** - Pilot tracking and impact measurement
8. **Infrastructure** - Service monitoring and provider status
9. **Communications Hub** - SMS campaigns and parent engagement
10. **Settings** - System configuration and integrations

## Tech Stack

- **Frontend**: React 18 + TypeScript + Vite
- **UI**: TailwindCSS with custom Sabi brand theme
- **Data**: TanStack Query for state management
- **Charts**: Recharts for data visualization
- **Backend**: FastAPI with operational API endpoints
- **Icons**: Lucide React

## Development

### Frontend Setup

```bash
cd dashboard
npm install
npm run dev
```

Frontend runs on `http://localhost:3000` with API proxy to backend.

### Backend Setup

The operations API is integrated into the main Sabi server:

```bash
# From workspace root
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Design System

### Colors

- **Ink**: `#201a13` (primary text)
- **Paper**: `#f7f2e7` (background)
- **Gold**: `#cba868` (primary accent)
- **Green**: `#1e7b43` (success)
- **Warn**: `#9b5b00` (warning)
- **Bad**: `#b42318` (error)

### Typography

- **Serif**: Cormorant Garamond (headings)
- **Sans**: Lexend (body text)

## API Endpoints

All operations endpoints are prefixed with `/api/operations`:

- `GET /metrics/mission-control` - Dashboard metrics
- `GET /alerts/active` - Active system alerts
- `GET /activity/recent` - Recent activity feed
- `GET /health/status` - System health
- `GET /students` - Student list with filters
- `GET /learning/analytics` - Learning analytics
- `GET /learning/interventions` - Intervention triggers
- `GET /calls` - Call quality review queue
- `GET /finance/metrics` - Financial metrics
- `GET /team` - Team members
- `GET /research/summary` - Research summary
- `GET /infrastructure/status` - Infrastructure status
- `GET /communications/campaigns` - SMS campaigns

## Deployment

### Production Build

```bash
cd dashboard
npm run build
```

Build output goes to `dashboard/dist/` and can be served statically or via FastAPI.

### Serving via FastAPI

Mount the built frontend in `main.py`:

```python
from fastapi.staticfiles import StaticFiles

app.mount("/dashboard", StaticFiles(directory="dashboard/dist", html=True), name="dashboard")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Operations Dashboard                     │
│                     (React + TypeScript)                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/REST
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Operations API                           │
│                     (FastAPI Router)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Call Admin   │    │  Student     │    │  Background  │
│ (existing)   │    │  Memory      │    │  Jobs        │
└──────────────┘    └──────────────┘    └──────────────┘
```

## License

Private - Education for Equality
