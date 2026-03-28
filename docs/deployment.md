# Deployment Guide

## Systemd Service Setup

### Service File

Create `/etc/systemd/system/mosi-downloader.service`:

```ini
[Unit]
Description=Mosi Downloader API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/mosi-downloader
EnvironmentFile=/path/to/mosi-downloader/.env
ExecStart=/path/to/mosi-downloader/.venv/bin/uvicorn api.server:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

### Cleanup Service & Timer

For automatic cleanup of old downloads:

**Service** (`/etc/systemd/system/mosi-downloader-cleanup.service`):
```ini
[Unit]
Description=Mosi Downloader cleanup

[Service]
Type=oneshot
User=your_username
ExecStart=/usr/bin/find /path/to/downloads/media -type f -mtime +7 -delete
```

**Timer** (`/etc/systemd/system/mosi-downloader-cleanup.timer`):
```ini
[Unit]
Description=Run Mosi Downloader cleanup daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

### Enable Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mosi-downloader.service
sudo systemctl enable --now mosi-downloader-cleanup.timer
```

## Reverse Proxy Configuration

### Caddy (Recommended)

Caddy handles WebSocket upgrades automatically.

```caddy
# For subdomain
viddown.yourdomain.com {
    reverse_proxy localhost:8001
}
```

Or with path:
```caddy
yourdomain.com/viddown/* {
    reverse_proxy /viddown localhost:8001
}
```

For WebSocket support in API (SSE events), ensure your Caddy version supports WebSocket proxying (most recent versions do).

### Nginx

Nginx requires explicit WebSocket upgrade handling:

```nginx
server {
    listen 80;
    server_name viddown.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        client_max_body_size 100M;
    }
}
```

## Security Considerations

### Bind Address

Always bind to `127.0.0.1` (localhost) and access via reverse proxy. This prevents direct external access.

**Insecure (don't do this):**
```bash
uvicorn api.server:app --host 0.0.0.0 --port 8001
```

**Secure:**
```bash
uvicorn api.server:app --host 127.0.0.1 --port 8001
```

### Firewall

Ensure your firewall allows:
- Port 80/443 for HTTP/HTTPS (reverse proxy)
- Port 8001 should be blocked externally (only localhost)

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8001/tcp
```

### File Downloads

The service has no built-in authentication. Rely on:
1. Reverse proxy authentication (Caddy has built-in auth)
2. Network-level isolation
3. VPN/access controls

## Network Setup

### Port Forwarding (if behind NAT)

If your server is behind a router:
1. Forward ports 80/443 to your server
2. Use a dynamic DNS service if you have a dynamic IP
3. Configure your reverse proxy with the public domain

### SSL/TLS

**Caddy:** Automatically handles HTTPS via Let's Encrypt

**Nginx with Certbot:**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d viddown.yourdomain.com
```

## Updating the Service

```bash
# Pull latest code (if using git)
cd /path/to/mosi-downloader
git pull

# Or replace files manually

# Restart service
sudo systemctl restart mosi-downloader.service
```

## Monitoring

### View Logs

```bash
# Service logs
sudo journalctl -u mosi-downloader.service -f

# Download logs
tail -f /path/to/mosi-downloader/logs/*.log
```

### Check Status

```bash
sudo systemctl status mosi-downloader.service
curl http://localhost:8001/api/health
```

## Backup Considerations

Backup these files for disaster recovery:
- `cookies/` - Cookie authentication files
- `jobs/*.json` - Job metadata
- `.env` - Configuration (contains tokens)
- Download directory (`~/Downloads/media/`)
