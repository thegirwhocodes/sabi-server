#!/bin/bash
set -euo pipefail

# ============================================================
# Sabi Voice AI Server — One-Click Setup
# For: Hetzner GEX44 (RTX 4000 Ada, Ubuntu 22.04)
#
# Usage:
#   1. SSH into your server: ssh root@YOUR_SERVER_IP
#   2. Upload this script or clone the repo
#   3. Edit DOMAIN and EMAIL below
#   4. Run: bash server-setup.sh
#   5. After reboot prompt, SSH back in and run again
# ============================================================

# ========================
# EDIT THESE TWO LINES
# ========================
DOMAIN="${SABI_DOMAIN:-sabi.yourdomain.com}"
EMAIL="${SABI_EMAIL:-you@example.com}"

# Where to install
INSTALL_DIR="/opt/sabi"
REPO_DIR="$INSTALL_DIR/sabi-server"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "================================================"
echo "  Sabi Voice AI Server Setup"
echo "  Domain: $DOMAIN"
echo "  Email:  $EMAIL"
echo "================================================"
echo ""

if [ "$DOMAIN" = "sabi.yourdomain.com" ]; then
    error "Please edit DOMAIN at the top of this script (or set SABI_DOMAIN env var)"
    error "Example: SABI_DOMAIN=sabi.educationforequality.org bash server-setup.sh"
    exit 1
fi

if [ "$EMAIL" = "you@example.com" ]; then
    error "Please edit EMAIL at the top of this script (or set SABI_EMAIL env var)"
    error "Example: SABI_EMAIL=nivie@wesleyan.edu bash server-setup.sh"
    exit 1
fi

# ============================================================
# STEP 1: System Update
# ============================================================
info "[1/8] Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl wget git ufw software-properties-common \
    apt-transport-https ca-certificates gnupg lsb-release
info "System packages updated."

# ============================================================
# STEP 2: NVIDIA Drivers
# ============================================================
if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo "unknown")
    info "[2/8] NVIDIA driver already installed: $GPU_NAME"
else
    info "[2/8] Installing NVIDIA drivers..."

    # Add NVIDIA package repository
    if [ ! -f /usr/share/keyrings/cuda-archive-keyring.gpg ]; then
        wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
        dpkg -i cuda-keyring_1.1-1_all.deb
        rm -f cuda-keyring_1.1-1_all.deb
        apt-get update -qq
    fi

    apt-get install -y -qq nvidia-driver-535

    echo ""
    echo "================================================"
    echo "  NVIDIA driver installed!"
    echo ""
    echo "  Please REBOOT now, then re-run this script:"
    echo "    sudo reboot"
    echo "    (wait 30 seconds, then SSH back in)"
    echo "    bash server-setup.sh"
    echo "================================================"
    exit 0
fi

# ============================================================
# STEP 3: Docker + NVIDIA Container Toolkit
# ============================================================
if command -v docker &> /dev/null; then
    info "[3/8] Docker already installed."
else
    info "[3/8] Installing Docker..."

    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

# NVIDIA Container Toolkit
if dpkg -l | grep -q nvidia-container-toolkit; then
    info "NVIDIA Container Toolkit already installed."
else
    info "Installing NVIDIA Container Toolkit..."
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
        gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

    apt-get update -qq
    apt-get install -y -qq nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
fi

# Verify GPU is visible inside Docker
info "Verifying GPU access inside Docker..."
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi > /dev/null 2>&1 || {
    error "GPU not accessible inside Docker. Check NVIDIA Container Toolkit installation."
    exit 1
}
info "Docker + GPU verified."

# ============================================================
# STEP 4: Firewall
# ============================================================
info "[4/8] Configuring firewall..."
ufw default deny incoming > /dev/null 2>&1
ufw default allow outgoing > /dev/null 2>&1
ufw allow 22/tcp > /dev/null 2>&1    # SSH
ufw allow 80/tcp > /dev/null 2>&1    # HTTP (certbot + redirect)
ufw allow 443/tcp > /dev/null 2>&1   # HTTPS
echo "y" | ufw enable > /dev/null 2>&1
info "Firewall active: SSH (22), HTTP (80), HTTPS (443)"

# ============================================================
# STEP 5: Application Setup
# ============================================================
info "[5/8] Setting up Sabi application..."
mkdir -p "$INSTALL_DIR"

# If we're running from the repo directory, copy files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/docker-compose.yml" ] && [ "$SCRIPT_DIR" != "$REPO_DIR" ]; then
    info "Copying files from $SCRIPT_DIR to $REPO_DIR..."
    mkdir -p "$REPO_DIR"
    cp -r "$SCRIPT_DIR"/* "$REPO_DIR/"
    cp -r "$SCRIPT_DIR"/.env.example "$REPO_DIR/" 2>/dev/null || true
fi

if [ ! -f "$REPO_DIR/docker-compose.yml" ]; then
    error "docker-compose.yml not found at $REPO_DIR"
    error "Please clone the sabi-server repo to $REPO_DIR first, or run this script from the repo directory."
    exit 1
fi

cd "$REPO_DIR"

# Replace domain placeholder in nginx.conf
sed -i "s|sabi.yourdomain.com|$DOMAIN|g" nginx.conf
info "nginx.conf updated with domain: $DOMAIN"

# Create .env from example if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    sed -i "s|sabi.yourdomain.com|$DOMAIN|g" .env

    echo ""
    echo "================================================"
    echo "  IMPORTANT: Edit your .env file!"
    echo ""
    echo "  nano $REPO_DIR/.env"
    echo ""
    echo "  Fill in these values:"
    echo "    SUPABASE_URL       — from your Supabase dashboard"
    echo "    SUPABASE_SERVICE_ROLE_KEY — Supabase > Settings > API"
    echo "    AT_API_KEY         — Africa's Talking dashboard"
    echo ""
    echo "  After editing, save (Ctrl+X, Y, Enter)"
    echo "  Then re-run: bash server-setup.sh"
    echo "================================================"
    exit 0
fi

# Verify .env has been configured
if grep -q "your-project.supabase.co" .env 2>/dev/null; then
    warn ".env still has placeholder values. Please edit $REPO_DIR/.env"
    warn "Then re-run this script."
    exit 0
fi

info "Application files ready."

# ============================================================
# STEP 6: SSL Certificate
# ============================================================
info "[6/8] Setting up SSL certificates..."

mkdir -p certbot/conf certbot/www

if [ -f "certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    info "SSL certificate already exists for $DOMAIN"
else
    info "Getting SSL certificate from Let's Encrypt..."

    # Use the HTTP-only nginx config for certbot validation
    if [ -f nginx-init.conf ]; then
        # Backup current nginx.conf, use init config temporarily
        cp nginx.conf nginx-ssl.conf
        sed "s|DOMAIN_PLACEHOLDER|$DOMAIN|g" nginx-init.conf > nginx.conf

        # Start nginx with HTTP-only config
        docker compose up -d nginx
        sleep 3

        # Request certificate
        docker compose run --rm certbot certonly \
            --webroot \
            --webroot-path=/var/www/certbot \
            --email "$EMAIL" \
            --agree-tos \
            --no-eff-email \
            -d "$DOMAIN" || {
            error "SSL certificate request failed."
            error "Make sure your DNS A record for $DOMAIN points to this server's IP."
            error "Check: nslookup $DOMAIN"
            # Restore SSL nginx config
            cp nginx-ssl.conf nginx.conf
            docker compose down
            exit 1
        }

        # Restore the full SSL nginx config
        cp nginx-ssl.conf nginx.conf
        rm -f nginx-ssl.conf

        # Stop temporary nginx
        docker compose down
    else
        warn "nginx-init.conf not found. Attempting certbot standalone..."
        docker run --rm \
            -v "$REPO_DIR/certbot/conf:/etc/letsencrypt" \
            -v "$REPO_DIR/certbot/www:/var/www/certbot" \
            -p 80:80 \
            certbot/certbot certonly \
            --standalone \
            --email "$EMAIL" \
            --agree-tos \
            --no-eff-email \
            -d "$DOMAIN"
    fi

    info "SSL certificate obtained!"
fi

# ============================================================
# STEP 7: Start Services
# ============================================================
info "[7/8] Starting Sabi services..."

# Build the Sabi container (downloads Whisper model — takes 5-15 min first time)
info "Building Sabi container (this downloads AI models — may take 10-15 minutes)..."
docker compose build sabi

# Start everything
docker compose up -d

# Wait for Ollama to be ready, then pull the LLM model
info "Waiting for Ollama to start..."
sleep 15

# Check if model already exists
if docker exec sabi-ollama ollama list 2>/dev/null | grep -q "llama3.1"; then
    info "Llama 3.1 8B model already downloaded."
else
    info "Downloading Llama 3.1 8B model (~4.7GB, may take 5-10 minutes)..."
    docker exec sabi-ollama ollama pull llama3.1:8b-instruct-q4_K_M
fi

info "All services started."

# ============================================================
# STEP 8: Audio Cache Cleanup Cron Job
# ============================================================
info "[8/8] Setting up maintenance..."

# Add cron job to clean up old audio files (older than 24 hours)
CRON_JOB="0 */6 * * * find $REPO_DIR/audio_cache -name '*.wav' -o -name '*.mp3' -mmin +1440 -delete 2>/dev/null"
if ! crontab -l 2>/dev/null | grep -q "audio_cache"; then
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    info "Audio cache cleanup cron job added (runs every 6 hours)."
else
    info "Audio cache cleanup cron job already exists."
fi

# ============================================================
# VERIFICATION
# ============================================================
echo ""
info "Waiting 30 seconds for services to fully load..."
sleep 30

echo ""
echo "================================================"
echo "  Container Status"
echo "================================================"
docker compose ps
echo ""

# Health check
echo "================================================"
echo "  Health Check"
echo "================================================"
HEALTH=$(curl -s "https://$DOMAIN/health" 2>/dev/null || echo "FAILED")
echo "  Response: $HEALTH"
echo ""

# GPU check
echo "================================================"
echo "  GPU Status"
echo "================================================"
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader
echo ""

echo "================================================"
echo "  Sabi Voice AI Server Setup Complete!"
echo ""
echo "  URL:    https://$DOMAIN"
echo "  Health: https://$DOMAIN/health"
echo ""
echo "  Useful commands:"
echo "    docker compose logs -f sabi    # View app logs"
echo "    docker compose logs -f ollama  # View LLM logs"
echo "    docker compose ps              # Check status"
echo "    docker compose restart         # Restart all"
echo "    nvidia-smi                     # Check GPU"
echo ""
echo "  Next steps:"
echo "    1. Set up Africa's Talking webhook:"
echo "       Voice callback → https://$DOMAIN/voice/incoming"
echo "    2. Test with: curl https://$DOMAIN/health"
echo "================================================"
