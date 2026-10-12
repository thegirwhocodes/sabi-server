# Sabi Remote Development & iPad Setup Guide

This guide details how to set up and run a secure, persistent remote development environment for **Sabi** (`sabi-server` and `cofounder_agent`) on your **Vultr Ubuntu 24.04/26.04 server**, accessible directly from **iPad Safari** using **VS Code Remote Tunnels** and **Roo Code**.

---

## 1. Quick Technical Breakdown & Fixes for the Original Guide

The standard draft has a few critical points that need tuning for Ubuntu Linux and Sabi:

1. **Architecture & CLI Download URL:**  
   Downloading from `https://visualstudio.com` returns HTML, not the CLI binary. The official Microsoft direct download link for the standalone 64-bit Linux CLI is:
   ```bash
   curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz
   ```
2. **Ubuntu Release Note:**  
   The current LTS is Ubuntu 24.04 (Noble), and Ubuntu 26.04 is the next LTS. Both use standard `systemd` and glibc/musl compatibility, which works seamlessly with the official standalone binary.
3. **Dedicated User (Best Practice):**  
   Running development environments, browser tunnels, and Roo Code directly as `root` is a security risk. It is recommended to create a dedicated developer user (e.g., `sabi-dev`) with `sudo` and `docker` permissions.
4. **Permanent Background Persistence:**  
   Instead of keeping an interactive SSH session open, `code tunnel service install` registers a `systemd` service that keeps the tunnel alive across disconnects and reboots.
5. **Port Forwarding for Sabi & Co-Founder Agent:**  
   VS Code Remote Tunnels automatically lets you forward internal ports (`8000` for Sabi FastAPI, `8001` for Co-Founder Agent dashboard) so you can test them directly from Safari on your iPad without opening firewall ports to the public internet.

---

## Phase 1: Prepare Your Vultr Server

### Step 1.1: Connect via SSH
Open your terminal (macOS/Linux terminal, or on iPad: **Blink Shell**, **Termius**, or **Prompt**) and SSH into your Vultr server:
```bash
ssh root@<YOUR_VULTR_IP>
```
*(Replace `<YOUR_VULTR_IP>` with your instance's IP address, e.g., `139.84.246.103`)*

### Step 1.2: Update System Packages & Install Essentials
```bash
apt update && apt upgrade -y
apt install -y curl wget git tar ufw ca-certificates gnupg
```

### Step 1.3: Create a Dedicated Developer User
```bash
# Create user 'sabi-dev' with sudo privileges
adduser --gecos "" sabi-dev
usermod -aG sudo sabi-dev

# If Docker is installed, allow sabi-dev to run containers without sudo
usermod -aG docker sabi-dev 2>/dev/null || true

# Switch to the developer user
su - sabi-dev
```

### Step 1.4: Download the Official VS Code CLI
Download and unpack the official standalone VS Code command line tool:
```bash
cd ~
curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' --output vscode_cli.tar.gz
tar -xf vscode_cli.tar.gz
rm vscode_cli.tar.gz

# Verify installation
./code --version
```
*(Optional: Move `code` to `/usr/local/bin/code` with `sudo mv code /usr/local/bin/` so it is globally available)*

---

## Phase 2: Start and Link the Remote Tunnel

### Step 2.1: Run the Tunnel Wizard
```bash
./code tunnel
```

1. **Terms Acceptance:** Press `y` to accept the license agreement.
2. **Provider Selection:** Choose `GitHub` as your authentication provider.
3. **GitHub Device Authentication:**  
   The terminal will print:
   ```text
   To grant access to the server, please go to https://github.com/login/device and use code XXXX-XXXX
   ```
4. **Authenticate on your iPad or Phone:**  
   Open `https://github.com/login/device` in Safari, log in with your GitHub account, and enter the 8-character code.
5. **Name Your Tunnel:**  
   The terminal will prompt for a name for the tunnel. Type a clear name, such as:
   ```text
   sabi-vultr-dev
   ```
6. **Confirmation:**  
   The terminal will output your dedicated URL:
   ```text
   Open this link in your browser: https://vscode.dev/tunnel/sabi-vultr-dev
   ```

---

## Phase 3: Set Up Permanent Background Service (24/7 Uptime)

To ensure the tunnel stays running without needing an active SSH terminal open:

1. In your SSH terminal running `./code tunnel`, press `Ctrl + C` to stop the interactive session.
2. Install the tunnel as a `systemd` service:
   ```bash
   ./code tunnel service install
   ```
3. Start the service:
   ```bash
   ./code tunnel service start
   ```
4. Check the service status:
   ```bash
   ./code tunnel service status
   ```

Your Vultr server is now permanently connected to `vscode.dev`!

---

## Phase 4: Configure Workspace & Roo Code on iPad Safari

### Step 4.1: Open VS Code in Safari
1. On your iPad, open **Safari** and navigate to your tunnel URL:
   ```text
   https://vscode.dev/tunnel/sabi-vultr-dev
   ```
2. Log in with the same GitHub account.
3. Open the Sabi workspace folder:
   - Tap **Menu (hamburger icon top-left) > File > Open Folder...**
   - Select `/home/sabi-dev` or the path where `sabi-server` is cloned (e.g. `/opt/sabi/sabi-server` or `~/sabi-server`).

### Step 4.2: Add to Home Screen (PWA Mode)
To get a full-screen, distraction-free IDE experience:
1. In Safari, tap the **Share** button (box with upward arrow).
2. Tap **Add to Home Screen**.
3. Name it **Sabi VS Code** and tap **Add**.
4. Launching from your home screen gives you full screen space without Safari URL bars or tabs.

### Step 4.3: Install Roo Code
1. In VS Code, tap the **Extensions** icon on the activity bar (four squares).
2. Search for `Roo Code`.
3. Tap **Install** (installs on the remote Vultr server).
4. Tap the **Roo Code** icon in the activity bar.
5. In Roo Code settings:
   - Configure your preferred LLM Provider (Anthropic, OpenRouter, DeepSeek, OpenAI, etc.).
   - Paste your API key.

---

## Phase 5: iPad Developer Workspace Optimization

Mobile browsers have specific quirks with touch targets and virtual keyboards. Here are the best configuration tweaks for iPad:

### 1. Essential VS Code Settings for iPad
Open Settings in VS Code (`Cmd + ,` or Menu > Preferences > Settings), switch to the **Remote** or **User** tab, and set:

- **Touch Menu Bar:** Ensure `"workbench.layoutControl.type": "menu"` or `"compact"`.
- **Disable Minimap:** Saves valuable horizontal screen real estate:
  ```json
  "editor.minimap.enabled": false
  ```
- **Word Wrap:**
  ```json
  "editor.wordWrap": "on"
  ```
- **Font Size:** Set to `14` or `15` with comfortable line height:
  ```json
  "editor.fontSize": 15,
  "editor.lineHeight": 24
  ```
- **Virtual Keyboard / Quick Suggestions:**
  ```json
  "editor.quickSuggestions": {
    "other": true,
    "comments": false,
    "strings": false
  }
  ```

### 2. Safari Settings
- Under **iPad Settings > Safari > Page Zoom**, set default zoom to **85%** or **90%** for `vscode.dev` to comfortably fit the sidebar and code editor on 11" or 13" iPad displays.
- Use a hardware keyboard (Magic Keyboard or Bluetooth keyboard) for full access to keyboard shortcuts like `Cmd + P` (Quick Open) and `Ctrl + ~` (Terminal).

---

## Phase 6: Running & Testing Sabi on the Vultr Server

### 1. Clone the Sabi Repository
In your VS Code integrated terminal (`Ctrl + ~` or Terminal > New Terminal):
```bash
git clone https://github.com/thegirwhocodes/sabi-server.git
cd sabi-server
```

### 2. Sabi Backend & Co-Founder Agent
You can test the **Co-Founder Agent** or the **Sabi Voice Server**:
```bash
# Example: Running the Co-Founder Agent Dashboard locally
cd cofounder_agent
python3 -m pip install -r requirements.txt
python3 api.py
```

### 3. Port Forwarding in VS Code
1. In the bottom panel, click the **Ports** tab.
2. Click **Forward a Port** and enter `8001` (for Co-Founder Agent dashboard) or `8000` (for Sabi FastAPI).
3. VS Code creates a secure forwarded address that you can open directly in Safari on your iPad to see the live UI!
