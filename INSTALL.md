# Installation Guide

## Prerequisites

- **Python 3.10+** - Download from [python.org](https://www.python.org/downloads/) or via your package manager
- **ffmpeg** - Required for post-processing (merging, metadata embedding, thumbnail attachment)
  ```bash
  # Ubuntu/Debian
  sudo apt install ffmpeg

  # macOS
  brew install ffmpeg

  # Arch
  sudo pacman -S ffmpeg
  ```
- **yt-dlp** - Auto-installed in virtual environment, or `sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp`

## Step-by-Step Installation

### 1. Clone or Extract Project

```bash
cd /path/to/your/projects
# If using git
git clone https://github.com/yourrepo/mosi-downloader.git
# Or just extract/copy the project folder
cd mosi-downloader
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -U yt-dlp fastapi uvicorn python-multipart
```

Or if using the requirements file:
```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Concurrency (max simultaneous downloads)
MOSI_CONCURRENCY=3

# Public URL for Telegram notifications and file downloads
MOSI_PUBLIC_BASE_URL=https://your-domain.com/viddown

# Telegram bot for notifications (optional)
MOSI_TELEGRAM_BOT_TOKEN=your_bot_token
MOSI_TELEGRAM_CHAT_ID=your_chat_id

# Job timeout in seconds (30 minutes default)
MOSI_JOB_TIMEOUT=1800
```

### 5. Create Download Directories

The service auto-creates these on startup:
- `jobs/` - Job metadata JSON files
- `logs/` - Download logs
- `cookies/` - Cookie files for authentication

Your downloads will be saved to: `~/Downloads/media/`

### 6. Setup Cookie Files (Optional)

For premium/restricted content, export cookies from your browser:

1. Install ["Get cookies.txt LOCALLY"](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/) extension
2. Visit each site and log in
3. Export cookies: Extension icon → Export
4. Save as `cookies/{site}.txt`:
   - `youtube.txt` for youtube.com
   - `twitter.txt` for twitter.com/x.com
   - `instagram.txt` for instagram.com
   - `threads.txt` for threads.net
   - `bluesky.txt` for bsky.app

### 7. Test the Service

```bash
uvicorn api.server:app --host 127.0.0.1 --port 8001
```

Visit `http://localhost:8001/` to access the web UI.

### 8. Setup Systemd Service (Production)

```bash
# Copy the service file
sudo cp docs/mosi-downloader.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start
sudo systemctl enable --now mosi-downloader.service

# Check status
sudo systemctl status mosi-downloader.service
```

### 9. Setup Reverse Proxy (Recommended)

See [docs/deployment.md](docs/deployment.md) for Caddy or nginx configuration with WebSocket support.

## Updating

### Update yt-dlp

Via web UI: Admin panel → "Update yt-dlp"

Or via CLI:
```bash
source .venv/bin/activate
pip install -U yt-dlp
```

### Update the Service

```bash
cd /path/to/mosi-downloader
git pull  # if using git
# or replace files manually
sudo systemctl restart mosi-downloader.service
```

## Directory Structure

```
mosi-downloader/
├── api/
│   └── server.py          # Main FastAPI application
├── web/
│   ├── static/            # CSS, JS assets
│   └── templates/         # HTML templates
├── cookies/               # Cookie files for each site
├── jobs/                  # Job metadata (auto-created)
├── logs/                  # Download logs (auto-created)
├── docs/                  # Documentation
├── .env                   # Environment configuration
├── .env.example           # Config template
└── requirements.txt       # Python dependencies
```

## Troubleshooting

- **Service won't start**: Check logs with `journalctl -u mosi-downloader.service`
- **Downloads fail**: Verify ffmpeg is installed (`ffmpeg -version`)
- **Instagram/Threads issues**: See [docs/troubleshooting.md](docs/troubleshooting.md)
- **Permission errors**: Ensure user owns the project directory

## Uninstall

```bash
# Stop and disable service
sudo systemctl disable --now mosi-downloader.service
sudo rm /etc/systemd/system/mosi-downloader.service

# Remove files (your downloads in ~/Downloads/media are untouched)
rm -rf /path/to/mosi-downloader
```
