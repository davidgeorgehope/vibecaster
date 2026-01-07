# Vibecaster Development Guidelines

## Architecture Notes

### SSE Streaming Through Cloudflare

Cloudflare has a ~100 second proxy timeout. Long-running operations MUST emit SSE events regularly to keep connections alive.

**Pattern for long-running operations:**

```python
# BAD - blocks for 60+ seconds, Cloudflare times out
def generate_thing():
    result = slow_api_call()  # blocks
    return result

# GOOD - yields progress events during polling
def generate_thing_stream():
    operation = start_async_operation()
    while not operation.done:
        yield ('progress', poll_count, max_polls)  # keepalive
        time.sleep(10)
        operation = poll_operation()
    yield ('complete', result)

# Keep blocking wrapper for tests/scripts
def generate_thing():
    for event_type, *data in generate_thing_stream():
        if event_type == 'complete':
            return data[0]
    return None
```

**Files using this pattern:**
- `backend/video_generation.py`: `generate_video_from_image_stream()`

### Google GenAI SDK Notes

- `types.Image.from_file()` requires keyword arg: `from_file(location=path)`
- `VideoGenerationReferenceImage` uses camelCase: `referenceType="ASSET"`
- Veo API: `image` (first frame) and `reference_images` are mutually exclusive

### Chunked Uploads for Large Files

Cloudflare has per-request size limits (~100MB on Pro). To support video uploads up to 500MB, we use chunked uploads.

**How it works:**

1. Frontend splits file into 50MB chunks
2. Backend stores chunks in memory (`pending_uploads` dict)
3. After all chunks received, backend assembles them
4. Assembled file is processed normally

**Endpoints:**

| Endpoint | Purpose |
|----------|---------|
| `POST /api/upload/init` | Initialize upload, returns `upload_id` |
| `POST /api/upload/chunk/{upload_id}` | Upload a single chunk |
| `POST /api/upload/complete/{upload_id}` | Assemble chunks, validate |

**Frontend pattern (`VideoPostBox.tsx`):**

```typescript
// Must read as ArrayBuffer for Chrome compatibility
const chunkSlice = file.slice(start, end);
const arrayBuffer = await chunkSlice.arrayBuffer();
const chunkBlob = new Blob([arrayBuffer], { type: 'application/octet-stream' });

formData.append('chunk', chunkBlob, `chunk_${i}.bin`);
```

**Important notes:**

- Nginx must allow chunk size: `client_max_body_size 60M;` in `/etc/nginx/sites-available/vibecaster`
- Chunks expire after 30 minutes (cleanup job runs every 5 min)
- Files <50MB use direct upload (no chunking)

**Testing:**

E2E test available: `tests/e2e/chunked_upload.test.js` (requires Playwright)

### Testing

- Unit tests: `pytest tests/` (mocked, fast)
- Integration tests: `pytest -m integration tests/` (live API, slow)
- Integration tests catch SDK API issues that mocks miss
- E2E tests: `node tests/e2e/*.test.js` (requires Playwright + chromium)

## Infrastructure

- Runs behind Cloudflare proxy
- Nginx reverse proxy on server
- Backend: FastAPI on port 8001
- Frontend: Next.js on port 3001

## Database

SQLite database at `backend/vibecaster.db`.

**Users table:**

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    is_active INTEGER DEFAULT 1,
    is_admin INTEGER DEFAULT 0
);
```

**Creating test users via API:**

```bash
# Signup (returns JWT token)
curl -X POST http://localhost:8001/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}'

# Login
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}'
```

**Cleaning up test users:**

```python
import sqlite3
conn = sqlite3.connect('backend/vibecaster.db')
cursor = conn.cursor()
cursor.execute("DELETE FROM users WHERE email LIKE '%test%'")
conn.commit()
conn.close()
```

**Note:** User ID column is `id`, not `user_id`. Foreign keys in other tables use `user_id` referencing `users.id`.

## Server Management

**Start/Stop:**

```bash
./start_production.sh   # Builds frontend, starts both services
./stop_production.sh    # Graceful shutdown
```

**Logs:**

```bash
tail -f logs/backend.log
tail -f logs/frontend.log
```

**Nginx config:** `/etc/nginx/sites-available/vibecaster`

- `client_max_body_size 60M` required for chunked uploads
