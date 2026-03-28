# REST API Reference

Base URL: `http://localhost:8001`

## Endpoints

### Health Check

```
GET /api/health
```

Returns service health and status.

**Response:**
```json
{
  "ok": true,
  "jobs": 5,
  "queue_size": 0,
  "concurrency": 3
}
```

---

### Create Download

```
POST /api/download
Content-Type: application/json
```

**Request Body:**
```json
{
  "url": "https://youtube.com/watch?v=...",
  "quality": "best",
  "playlist": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | required | Video/playlist URL |
| `quality` | string | `"best"` | Quality: `best`, `1080p`, `720p`, `480p`, `audio` |
| `playlist` | boolean | `true` | Download as playlist if URL is playlist |

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "events_url": "/api/events/550e8400-e29b-41d4-a716-446655440000",
  "status_url": "/api/status/550e8400-e29b-41d4-a716-446655440000",
  "file_url": "/api/file/550e8400-e29b-41d4-a716-446655440000"
}
```

---

### Get Job Status

```
GET /api/status/{job_id}
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://youtube.com/watch?v=...",
  "quality": "best",
  "playlist": true,
  "status": "downloading",
  "title": "Video Title",
  "progress": 45.5,
  "speed": "2.5MiB/s",
  "eta": "00:30",
  "files": [],
  "logs": ["[download] 45.5% of 100MiB..."],
  "error": null,
  "created_at": 1710000000.0,
  "updated_at": 1710000100.0,
  "started_at": 1710000005.0,
  "completed_at": null,
  "log_tail": ["[download] 45.5% of 100MiB at 2.5MiB/s..."]
}
```

**Status Values:**
- `queued` - Waiting in queue
- `downloading` - Currently downloading
- `completed` - Successfully finished
- `failed` - Error occurred

---

### Stream Job Events (SSE)

```
GET /api/events/{job_id}
```

Server-Sent Events stream for real-time updates.

**Event Types:**
- `update` - Job state changed
- `complete` - Job finished successfully
- `failed` - Job failed

**Data Format:**
```json
{
  "job_id": "...",
  "status": "downloading",
  "title": "...",
  "progress": 45.5,
  "speed": "2.5MiB/s",
  "eta": "00:30",
  "error": null,
  "file_url": null
}
```

---

### Download File

```
GET /api/file/{job_id}
```

Returns the downloaded file(s).

- Single file: Direct file download
- Multiple files: ZIP archive

**Requirements:** Job status must be `completed`

**Response:** Binary file download

**Errors:**
- `404` - Job not found or file not found
- `409` - Job not yet completed

---

### List Jobs

```
GET /api/jobs
```

Returns last 100 jobs, ordered by creation time (newest first).

---

### Delete Job

```
DELETE /api/jobs/{job_id}
```

Removes job metadata and log file.

---

### yt-dlp Version

```
GET /api/ytdlp-version
```

**Response:**
```json
{
  "version": "2024.03.10",
  "binary": "/path/to/yt-dlp"
}
```

---

### Update yt-dlp

```
POST /api/admin/update-ytdlp
```

Updates yt-dlp to latest version via pip.

**Response:**
```json
{
  "ok": true,
  "version": "2024.03.11",
  "output": "Collecting yt-dlp..."
}
```

---

### List Cookie Files

```
GET /api/admin/cookies
```

**Response:**
```json
[
  {
    "site": "youtube",
    "domains": ["youtube.com", "youtu.be"],
    "size": 2048,
    "updated_at": 1710000000.0
  }
]
```

---

### Upload Cookie File

```
POST /api/admin/cookies
Content-Type: multipart/form-data
```

**Form Fields:**
- `site` - Site name: `youtube`, `twitter`, `instagram`, `threads`, `bluesky`
- `file` - Cookie file (Netscape format)

---

### Delete Cookie File

```
DELETE /api/admin/cookies/{site}
```

---

## Web UI Routes

| Route | Description |
|-------|-------------|
| `/` | Main download interface |
| `/job/{job_id}` | Job detail page |
| `/admin` | Admin panel (yt-dlp update, cookies) |
