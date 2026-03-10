# Server Deployment Guide

This guide covers deploying Kiro Proxy on various server environments.

## Table of Contents

- [Run from Source](#run-from-source)
- [Docker Deployment](#docker-deployment)
- [Account Configuration](#account-configuration)
- [Auto-start on Boot](#auto-start-on-boot)
- [Reverse Proxy Setup](#reverse-proxy-setup)
- [Common Issues](#common-issues)

---

## Run from Source

Requires Python ≥ 3.14 and [uv](https://docs.astral.sh/uv/).

### Install uv

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Clone and Run

```bash
# Clone project
git clone <your-repo-url>
cd KiroProxy

# Install dependencies
uv sync

# Run (default port 8080)
uv run python run.py

# Specify port
uv run python run.py 9090

# Use CLI
uv run python run.py serve -p 8081
```

### Update to Latest Version

```bash
cd KiroProxy
git pull origin main
uv sync
```

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

COPY . .

# Expose port
EXPOSE 8080

# Data volume
VOLUME ["/app/data"]

# Start
CMD ["uv", "run", "python", "run.py"]
```

Build and run:

```bash
docker build -t kiro-proxy .
docker run -d -p 8080:8080 -v kiro-data:/app/data --name kiro-proxy kiro-proxy
```

### Docker Compose

```yaml
version: '3'
services:
  kiro-proxy:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

```bash
docker-compose up -d
```

---

## Account Configuration

Servers usually don't have browsers. Several ways to add accounts:

### Option 1: Remote Login Link (Recommended)

1. Start KiroProxy on server
2. Open `http://server-ip:8080` in local browser
3. Click "Remote Login Link" button
4. Copy generated link, open in local browser
5. Complete Google/GitHub authorization
6. Account auto-added to server

### Option 2: Import/Export

**On local computer:**
```bash
uv run python run.py
uv run python run.py accounts export -o accounts.json
```

**On server:**
```bash
uv run python run.py accounts import accounts.json
```

### Option 3: Manual Add Token

1. Login in local Kiro IDE
2. Find JSON files in `~/.aws/sso/cache/` directory
3. Copy `accessToken` and `refreshToken`

**On server:**
```bash
uv run python run.py accounts add
```

### Option 4: Scan Local Tokens

```bash
uv run python run.py accounts scan --auto
```

---

## Auto-start on Boot

### Linux (systemd)

Create `/etc/systemd/system/kiro-proxy.service`:

```ini
[Unit]
Description=Kiro API Proxy
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/KiroProxy
ExecStart=/root/.local/bin/uv run python run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable kiro-proxy
sudo systemctl start kiro-proxy

# Check status
sudo systemctl status kiro-proxy

# View logs
tail -f /opt/KiroProxy/data/logs/kiro-proxy.log
```

### Linux (screen / tmux)

```bash
# screen
screen -S kiro
uv run python run.py
# Ctrl+A D to detach, screen -r kiro to reattach

# tmux
tmux new -s kiro
uv run python run.py
# Ctrl+B D to detach, tmux attach -t kiro to reattach
```

### Linux (nohup)

```bash
nohup uv run python run.py > /dev/null 2>&1 &
tail -f data/logs/kiro-proxy.log
```

---

## Reverse Proxy Setup

### Nginx

```nginx
server {
    listen 80;
    server_name kiro.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;
    }
}
```

**Enable HTTPS:**

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d kiro.example.com
```

### Caddy

```caddyfile
kiro.example.com {
    reverse_proxy localhost:8080
}
```

Caddy auto-manages HTTPS certificates.

---

## Common Issues

### Port in Use

```bash
lsof -i :8080  # Linux/macOS
netstat -ano | findstr :8080  # Windows

uv run python run.py 8081
```

### Firewall

```bash
# Ubuntu/Debian
sudo ufw allow 8080/tcp

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

### View Logs

```bash
# Application logs
tail -f data/logs/kiro-proxy.log

# API call records
cat data/logs/flows/$(date +%Y-%m-%d).jsonl | python -m json.tool

# systemd logs
sudo journalctl -u kiro-proxy -f
```

### Update

```bash
cd /opt/KiroProxy
git pull origin main
uv sync
sudo systemctl restart kiro-proxy
```
