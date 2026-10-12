#!/usr/bin/env bash
# ==============================================================================
# Sabi Vultr Remote Dev Setup: VS Code Tunnel & Roo Code (iPad-Ready)
# Server IP: 139.84.246.103
# ==============================================================================
set -euo pipefail

DEV_USER="sabi-dev"
TUNNEL_NAME="sabi-vultr-dev"

echo "=================================================================="
echo "  Setting up Sabi Remote Development Environment on Vultr"
echo "  Target User: $DEV_USER"
echo "  Tunnel Name: $TUNNEL_NAME"
echo "=================================================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "[ERROR] Please run this bootstrap script as root: sudo bash vultr-setup-tunnel.sh"
  exit 1
fi

# 1. System packages
echo "[1/6] Updating system packages & installing dependencies..."
apt update -qq
apt install -y -qq curl wget git tar ufw ca-certificates gnupg python3 python3-pip python3-venv

# 2. Setup user
echo "[2/6] Ensuring developer user '$DEV_USER' exists..."
if ! id -u "$DEV_USER" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "$DEV_USER"
    usermod -aG sudo "$DEV_USER"
    echo "$DEV_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/99-$DEV_USER"
    echo "Created user $DEV_USER with passwordless sudo."
fi

# Docker group permissions if docker exists
if getent group docker >/dev/null 2>&1; then
    usermod -aG docker "$DEV_USER"
fi

# 3. Download VS Code standalone CLI
echo "[3/6] Installing official VS Code CLI binary..."
USER_HOME=$(eval echo "~$DEV_USER")
TMP_DIR=$(mktemp -d)
cd "$TMP_DIR"
curl -sSLk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz
tar -xf vscode_cli.tar.gz
install -m 755 code /usr/local/bin/code
cd - >/dev/null
rm -rf "$TMP_DIR"
echo "VS Code CLI installed to /usr/local/bin/code ($(code --version))"

# 4. Clone Sabi Server if not already present
DEV_WORKSPACE="$USER_HOME/sabi-server"
if [ ! -d "$DEV_WORKSPACE" ]; then
    echo "[4/6] Cloning sabi-server into $DEV_WORKSPACE..."
    sudo -u "$DEV_USER" git clone https://github.com/thegirwhocodes/sabi-server.git "$DEV_WORKSPACE"
else
    echo "[4/6] Workspace already exists at $DEV_WORKSPACE."
fi

# 5. UFW basic firewall check (allowing SSH port 22)
echo "[5/6] Checking firewall configuration..."
if command -v ufw >/dev/null 2>&1; then
    ufw allow 22/tcp >/dev/null 2>&1 || true
    echo "SSH port 22 verified in firewall."
fi

# 6. Launch Tunnel instructions
echo ""
echo "=================================================================="
echo "  Setup Complete! Next Step: Start & Link your VS Code Tunnel"
echo "=================================================================="
echo ""
echo "Now switch to your developer user and link GitHub:"
echo ""
echo "  su - $DEV_USER"
echo "  code tunnel --name $TUNNEL_NAME"
echo ""
echo "1. Press 'y' to accept license terms."
echo "2. Select 'GitHub' authentication."
echo "3. Open https://github.com/login/device on your iPad and enter the code."
echo "4. Once linked, press Ctrl+C and install as a background service:"
echo "     code tunnel service install"
echo "     code tunnel service start"
echo ""
echo "5. Then open in Safari on iPad: https://vscode.dev/tunnel/$TUNNEL_NAME"
echo "=================================================================="
