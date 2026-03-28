# Troubleshooting Guide

## Common Issues

### Instagram/Threads Stories Fail with "Postprocessing: To ignore this, add a trailing '?' to the map"

**Symptom:**
```
ERROR: Postprocessing: To ignore this, add a trailing '?' to the map.
```

**Cause:** Instagram, Threads, and Bluesky stories are often video-only (no audio track). The metadata embedder runs ffmpeg with a required audio map that fails on video-only files.

**Fix:** This is automatically handled for Apple-compat domains (instagram.com, threads.net, bsky.app) in the current version. The service skips metadata/thumbnail embedding for these URLs.

**Verification:** After updating, restart the service:
```bash
sudo systemctl restart mosi-downloader.service
```

---

### Download Stuck at 100% with Merger Error

**Symptom:**
```
[Merger] Merging formats into "..."
ERROR: Postprocessing: To ignore this, add a trailing '?' to the map.
```

**Cause:** yt-dlp selected separate video and audio streams that need merging, but the merge fails due to missing audio track or incompatible stream mapping.

**Fix:** For Instagram/Threads/Bluesky URLs, the service now skips the quality filter entirely to avoid forcing separate stream selection. If you're seeing this on other platforms, it may be a temporary YouTube/ extractor issue.

---

### yt-dlp "Video unavailable" or "404 Not Found"

**Possible Causes:**
1. Video was deleted or made private
2. Age-restriction requires cookie authentication
3. Geo-restriction (try `--geo-bypass-country`)

**Solutions:**
- Set up cookie file for the platform
- Try a different video URL
- Check if video works in browser incognito

---

### ffmpeg Not Found

**Symptom:**
```
ERROR: ffmpeg not found. Please install or provide the path using --ffmpeg-location
```

**Fix:**
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Verify
ffmpeg -version
```

---

### Telegram Notifications Not Working

**Check:**
1. Bot token is valid: `https://api.telegram.org/bot{TOKEN}/getMe`
2. Chat ID is correct: `https://api.telegram.org/bot{TOKEN}/getUpdates`
3. Bot has been started in Telegram first
4. `MOSI_PUBLIC_BASE_URL` is set correctly in `.env`

**Test:**
```bash
curl -X POST "https://api.telegram.org/bot{TOKEN}/sendMessage" \
  -d '{"chat_id": "{CHAT_ID}", "text": "Test"}'
```

---

### Service Won't Start

**Check logs:**
```bash
sudo journalctl -u mosi-downloader.service -e
```

**Common issues:**
- Port already in use: `sudo lsof -i :8001`
- .env syntax error: Check for missing quotes or newlines
- Virtual environment broken: Recreate with `python3 -m venv .venv`

---

### Permission Denied on Downloads

**Symptom:**
```
PermissionError: [Errno 13] Permission denied: '/home/user/Downloads/media/...'
```

**Cause:** Service runs as a different user than the file owner.

**Fix:**
```bash
# Change ownership of download directory
sudo chown -R $USER:$USER ~/Downloads/media

# Or run service as correct user (edit systemd service)
sudo nano /etc/systemd/system/mosi-downloader.service
# Change User= line
sudo systemctl daemon-reload
sudo systemctl restart mosi-downloader.service
```

---

### Cookie File Not Working

**Check cookie file format:**
```bash
head -5 cookies/youtube.txt
# Should start with:
# # Netscape HTTP Cookie File
```

**Common issues:**
- File was exported in wrong format (should be Netscape, not JSON)
- Session expired - re-export cookies from browser
- Wrong site - ensure correct cookie file matches URL

---

### Job Never Completes (Timeout)

**Symptom:** Job stays in "downloading" state indefinitely.

**Fix:**
```bash
# Check if process is hung
ps aux | grep yt-dlp

# Kill stuck job (find PID from logs)
kill {PID}

# Or restart service
sudo systemctl restart mosi-downloader.service
```

**Prevent:** Set `MOSI_JOB_TIMEOUT` in `.env` (default: 30 minutes)

---

### WebSocket/SSE Events Not Working

**Symptom:** Web UI doesn't show real-time progress.

**Check:**
1. Reverse proxy supports WebSocket (Caddy recommended)
2. Browser console shows WebSocket errors
3. Network firewall allows WebSocket connections

**Nginx users:** Ensure upgrade headers are set (see [deployment.md](deployment.md))

---

### High Memory Usage

**Normal:** Each concurrent download uses ~100-300MB memory.

**Excessive:** Check for stuck processes:
```bash
ps aux --sort=-%mem | head -10
```

**Fix:** Reduce `MOSI_CONCURRENCY` in `.env`

---

## Debug Mode

Enable verbose logging in `.env`:
```bash
# Add to .env (requires restart)
PYTHONUNBUFFERED=1
```

Or run directly with verbose output:
```bash
cd /path/to/mosi-downloader
source .venv/bin/activate
uvicorn api.server:app --host 127.0.0.1 --port 8001 --log-level debug
```

## Getting Help

If issues persist:
1. Check yt-dlp issues: https://github.com/yt-dlp/yt-dlp/issues
2. Check service logs in `logs/{job_id}.log`
3. Try running yt-dlp directly:
   ```bash
   /path/to/mosi-downloader/.venv/bin/yt-dlp -v {URL}
   ```
