# Sabi Operations Dashboard - Deployment Guide

## Quick Start

### 1. Install Dependencies

```bash
# Backend
pip install -r requirements.txt

# Frontend
cd dashboard
npm install
```

### 2. Environment Configuration

Create a `.env` file in the workspace root:

```env
# Core API
SABI_API_KEY=your-secure-api-key-here
SABI_ADMIN_PIN=your-admin-pin

# Database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key

# AI Services
ANTHROPIC_API_KEY=your-anthropic-key
GROQ_API_KEY=your-groq-key
ELEVENLABS_API_KEY=your-elevenlabs-key

# Telephony
AFRICAS_TALKING_API_KEY=your-at-key
AFRICAS_TALKING_USERNAME=your-at-username

# Storage
SABI_SHARED_AUDIO_DIR=/shared/audio

# Security
SABI_PASSWORD_SALT=your-secure-salt
```

### 3. Development Mode

Terminal 1 (Backend):
```bash
uvicorn main:app --reload --port 8000
```

Terminal 2 (Frontend):
```bash
cd dashboard
npm run dev
```

Dashboard: `http://localhost:3000`
API: `http://localhost:8000`
API Docs: `http://localhost:8000/docs`

### 4. Production Build

```bash
# Build frontend
cd dashboard
npm run build

# Serve everything through FastAPI
cd ..
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Production Deployment

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Node.js for dashboard build
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Build dashboard
RUN cd dashboard && npm install && npm run build

# Expose port
EXPOSE 8000

# Run server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t sabi-operations .
docker run -p 8000:8000 --env-file .env sabi-operations
```

### Using systemd (Linux Server)

Create `/etc/systemd/system/sabi-operations.service`:

```ini
[Unit]
Description=Sabi Operations Dashboard
After=network.target

[Service]
Type=simple
User=sabi
WorkingDirectory=/opt/sabi-server
Environment=PATH=/opt/sabi-server/venv/bin
ExecStart=/opt/sabi-server/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable sabi-operations
sudo systemctl start sabi-operations
sudo systemctl status sabi-operations
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name operations.sabi.org;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name operations.sabi.org;

    ssl_certificate /etc/letsencrypt/live/operations.sabi.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/operations.sabi.org/privkey.pem;

    # Dashboard
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support for real-time features
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Security

### API Authentication

All operations API endpoints require authentication. Include the API key in requests:

```bash
# Via header (recommended)
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/operations/metrics/mission-control

# Via query parameter
curl http://localhost:8000/api/operations/metrics/mission-control?api_key=your-api-key
```

### User Management

Add team members in `operations_auth.py`:

```python
users_db = {
    "user-token-1": User(
        id="user-1",
        email="user@e4e.org",
        name="User Name",
        role="reviewer",
        permissions=ROLES["reviewer"],
    ),
}
```

### Roles & Permissions

- **admin**: Full access to all modules
- **reviewer**: Call quality review and research
- **researcher**: View-only access to research and finance
- **support**: Basic dashboard access

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
```

### Logs

```bash
# Follow logs
journalctl -u sabi-operations -f

# Last 100 lines
journalctl -u sabi-operations -n 100
```

### Metrics Collection

Background jobs run automatically:
- Daily metrics aggregation (midnight)
- Hourly health checks
- Intervention detection (every 4 hours)

Metrics are stored in `data/metrics/` as JSON files.

## Backup

### Database Backup

```bash
# Backup call data
tar -czf backup-$(date +%Y%m%d).tar.gz /shared/audio/call_*.json

# Backup metrics
tar -czf metrics-$(date +%Y%m%d).tar.gz data/metrics/
```

### Automated Backups

```bash
# Add to crontab
0 2 * * * /opt/sabi-server/scripts/backup.sh
```

## Troubleshooting

### Dashboard not loading

1. Check if frontend built: `ls dashboard/dist/index.html`
2. Rebuild: `cd dashboard && npm run build`
3. Check backend logs: `journalctl -u sabi-operations -n 50`

### API errors

1. Verify API key: `echo $SABI_API_KEY`
2. Check service status: `systemctl status sabi-operations`
3. View error logs: `tail -f /var/log/sabi/error.log`

### Performance issues

1. Check system resources: `htop`
2. Monitor API latency in Infrastructure dashboard
3. Increase workers: `--workers 8`

## Support

For issues or questions:
- Email: support@educationforequality.org
- Slack: #sabi-ops
- Docs: https://docs.sabi.org/operations
