# Mosi Downloader - Development Notes

## Instagram/Threads/Bluesky Story Downloads - Known Issue & Fix

### Problem
Downloads from Instagram (and likely Threads/Bluesky) stories were failing with:
```
ERROR: Postprocessing: To ignore this, add a trailing '?' to the map.
```

This occurred even though the video file was successfully downloaded.

### Root Cause
1. Instagram stories are often video-only (no audio track)
2. The service was using `--embed-metadata` which runs ffmpeg internally to embed metadata
3. ffmpeg's `-map`指令 for audio was failing because no audio stream exists

### Solution (applied in `api/server.py`)

For Apple-compat domains (`instagram.com`, `threads.net`, `bsky.app`, `bsky.social`):

1. Skip `--embed-thumbnail` and `--embed-metadata` entirely
2. Skip the quality filter (`-f bv*+ba/...`) which forces separate video+audio stream selection requiring merge
3. Use `--remux-video mp4` only to ensure MP4 container format

```python
APPLE_COMPAT_DOMAINS = ["instagram.com", "threads.net", "bsky.app", "bsky.social"]
apple_compat = any(d in url.lower() for d in APPLE_COMPAT_DOMAINS)

if apple_compat:
    cmd.extend([
        "--remux-video", "mp4",
        "--format-sort", "+codec:h264:m4a",
        "--no-embed-thumbnail",
        "--no-embed-metadata",
    ])
else:
    cmd.append("--embed-thumbnail")

# ...

if not apple_compat:
    cmd.extend(quality_args(quality))
```

### Files Modified
- `api/server.py`: Lines 263-289 (apple_compat block) and line 300 (quality_args condition)

### Service Management
```bash
# Restart the service
sudo systemctl restart mosi-downloader.service

# Check status
systemctl status mosi-downloader.service

# View logs
journalctl -u mosi-downloader.service -f
```

### Related Files
- Service definition: `/etc/systemd/system/mosi-downloader.service`
- Job files: `jobs/*.json`
- Log files: `logs/*.log`
