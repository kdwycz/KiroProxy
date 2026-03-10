# 服务器部署指南

本文档详细介绍如何在各种服务器环境中部署 Kiro Proxy。

## 目录

- [从源码运行](#从源码运行)
- [Docker 部署](#docker-部署)
- [账号配置](#账号配置)
- [开机自启配置](#开机自启配置)
- [反向代理配置](#反向代理配置)
- [常见问题](#常见问题)

---

## 从源码运行

需要 Python ≥ 3.14 和 [uv](https://docs.astral.sh/uv/)。

### 安装 uv

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 克隆并运行

```bash
# 克隆项目
git clone https://github.com/your-username/KiroProxy.git
cd KiroProxy

# 安装依赖
uv sync

# 运行（默认端口 8080）
uv run python run.py

# 指定端口
uv run python run.py 9090

# 使用 CLI
uv run python run.py serve -p 8081
```

### 更新到最新版本

```bash
cd KiroProxy
git pull origin main
uv sync
```

---

## Docker 部署

### Dockerfile

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# 安装 uv
RUN pip install uv

# 复制项目文件
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

COPY . .

# 暴露端口
EXPOSE 8080

# 数据目录
VOLUME ["/app/data"]

# 启动
CMD ["uv", "run", "python", "run.py"]
```

构建并运行：

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

## 账号配置

服务器通常没有浏览器，有以下几种方式添加账号：

### 方式一：远程登录链接（推荐）

1. 在服务器上启动 KiroProxy
2. 在本地浏览器打开 `http://服务器IP:8080`
3. 点击「远程登录链接」按钮
4. 复制生成的链接，在本地浏览器打开
5. 完成 Google/GitHub 授权
6. 账号自动添加到服务器

### 方式二：导入导出

**本地电脑：**
```bash
# 运行 KiroProxy 并登录
uv run python run.py

# 导出账号
uv run python run.py accounts export -o accounts.json
```

**服务器：**
```bash
# 上传 accounts.json 到服务器后导入
uv run python run.py accounts import accounts.json

# 或使用 curl
curl -X POST http://localhost:8080/api/accounts/import \
  -H "Content-Type: application/json" \
  -d @accounts.json
```

### 方式三：手动添加 Token

1. 在本地 Kiro IDE 登录
2. 找到 `~/.aws/sso/cache/` 目录下的 JSON 文件
3. 复制 `accessToken` 和 `refreshToken`

**服务器上：**
```bash
# 交互式添加
uv run python run.py accounts add

# 或使用 API
curl -X POST http://localhost:8080/api/accounts/manual \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的账号",
    "access_token": "eyJ...",
    "refresh_token": "eyJ..."
  }'
```

### 方式四：扫描本地 Token

如果服务器上安装了 Kiro IDE 并已登录：

```bash
uv run python run.py accounts scan --auto
```

---

## 开机自启配置

### Linux (systemd)

创建服务文件 `/etc/systemd/system/kiro-proxy.service`：

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
# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable kiro-proxy
sudo systemctl start kiro-proxy

# 查看状态
sudo systemctl status kiro-proxy

# 查看日志
sudo journalctl -u kiro-proxy -f
# 或查看文件日志
tail -f /opt/KiroProxy/data/logs/kiro-proxy.log
```

### Linux (screen / tmux)

**screen：**
```bash
screen -S kiro
uv run python run.py
# Ctrl+A D 退出会话（程序继续运行）

# 重新连接
screen -r kiro
```

**tmux：**
```bash
tmux new -s kiro
uv run python run.py
# Ctrl+B D 退出会话

# 重新连接
tmux attach -t kiro
```

### Linux (nohup)

```bash
nohup uv run python run.py > /dev/null 2>&1 &
# 日志已自动写入 data/logs/kiro-proxy.log
tail -f data/logs/kiro-proxy.log
```

---

## 反向代理配置

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
        
        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400;
    }
}
```

**启用 HTTPS：**

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

Caddy 会自动申请和续期 HTTPS 证书。

---

## 常见问题

### 端口被占用

```bash
# 查看端口占用
lsof -i :8080  # Linux/macOS
netstat -ano | findstr :8080  # Windows

# 使用其他端口
uv run python run.py 8081
```

### 防火墙配置

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 8080/tcp

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

### 查看日志

```bash
# 应用日志
tail -f data/logs/kiro-proxy.log

# API 调用记录
cat data/logs/flows/$(date +%Y-%m-%d).jsonl | python -m json.tool

# systemd 日志
sudo journalctl -u kiro-proxy -f
```

### 更新版本

```bash
cd /opt/KiroProxy
git pull origin main
uv sync
sudo systemctl restart kiro-proxy
```
