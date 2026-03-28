# Mosi Downloader

A self-hosted video downloader service powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp). Download videos from YouTube, Twitter/X, Instagram, Threads, Bluesky, and other platforms via a web UI or REST API.

## Features

- **Multi-platform support**: YouTube, Twitter/X, Instagram, Threads, Bluesky, and more
- **Quality options**: best, 1080p, 720p, 480p, or audio-only (MP3)
- **Playlist support**: Download entire playlists or individual items
- **Cookie-based authentication**: Support for premium/age-restricted content
- **Telegram notifications**: Get notified when downloads complete
- **Concurrent downloads**: Process multiple jobs simultaneously
- **Web UI**: Simple interface at `/` and admin panel at `/admin`
- **REST API**: Programmatic access for integrations

## Quick Start

### Prerequisites

- Python 3.10+
- ffmpeg (for post-processing)
- yt-dlp (auto-installed in venv)

### Installation

```bash
# Clone or navigate to the project
cd /path/to/mosi-downloader

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -U yt-dlp fastapi uvicorn python-multipart

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# Start the service
uvicorn api.server:app --host 127.0.0.1 --port 8001
```

### Systemd Service (Production)

```bash
sudo cp docs/mosi-downloader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mosi-downloader.service
```

### Reverse Proxy

See [docs/deployment.md](docs/deployment.md) for Caddy/nginx configuration with WebSocket support.

## Usage

### Web UI

- Main interface: `http://localhost:8001/`
- Admin panel: `http://localhost:8001/admin`

### REST API

```bash
# Create a download job
curl -X POST http://localhost:8001/api/download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=...", "quality": "best", "playlist": false}'

# Check job status
curl http://localhost:8001/api/status/{job_id}

# Get file when complete
curl -O http://localhost:8001/api/file/{job_id}
```

### Supported Quality Options

| Quality | Description |
|---------|-------------|
| `best` | Highest available quality (default) |
| `1080p` | Max 1080p resolution |
| `720p` | Max 720p resolution |
| `480p` | Max 480p resolution |
| `audio` | Audio only (MP3) |

## Configuration

See [docs/configuration.md](docs/configuration.md) for all environment variables.

Key settings in `.env`:
- `MOSI_CONCURRENCY` - Max concurrent downloads (default: 3)
- `MOSI_TELEGRAM_BOT_TOKEN` - Telegram bot for notifications
- `MOSI_PUBLIC_BASE_URL` - Public URL for Telegram download links
- `MOSI_JOB_TIMEOUT` - Max download time in seconds (default: 1800)

## Cookie Setup

For premium content, export cookies using the "Get cookies.txt LOCALLY" browser extension:

1. Install the browser extension
2. Log into the desired site
3. Export cookies to `cookies/{site}.txt`

Supported sites: `youtube`, `twitter`, `instagram`, `threads`, `bluesky`

## API Reference

See [docs/api.md](docs/api.md) for full endpoint documentation.

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md) for common issues.

## License

MIT
