---
name: debug-flask-render-resource-limits
description: Debug and optimize Flask apps for Render's resource-constrained plans (512MB RAM, limited CPU). Use when Flask apps crash, return 503 errors, get stuck, or OOM on Render Starter/Free plans. Covers rate limiter health check issues, memory optimization, logging configuration, and background task patterns.
---

# Debug Flask Apps on Render Resource-Constrained Plans

## Common Issues on Render Starter/Free Plans

### Issue 1: Service Returns 503 After Running Fine Initially

**Symptoms:**
- App works for 10-30 minutes then starts returning 503
- Frontend gets `503 Service Unavailable` during polling
- Render dashboard shows service as "unhealthy"

**Root cause:** Rate limiter blocking Render's health check agent.

Render pings `/health` every ~30 seconds (~120 requests/hour). If your rate limiter is set to `50 per hour` globally, health checks exceed the limit after ~25 minutes. Render sees 429 responses from `/health` and marks the service unhealthy → all requests get 503.

**Fix:** Exempt health check and polling endpoints from rate limiting.

```python
# app/middleware/rate_limit.py
from flask import Flask, request
from flask_limiter import Limiter

def _exempt_from_rate_limit() -> bool:
    """Skip rate limiting for health checks and status polling."""
    return (
        request.path == "/health" or
        request.path.startswith("/api/import/status/")
    )

def init_rate_limiter(app: Flask) -> Limiter:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
    )
    limiter.request_filter(_exempt_from_rate_limit)
    return limiter
```

### Issue 2: Application Logs Missing in Render

**Symptoms:**
- Only see gunicorn startup logs, no application logs
- `logger.info(...)` statements produce no output
- Can't debug what's happening during crashes

**Root cause:** Flask's `setup_logging()` only configured `app.logger`, but application modules use `logging.getLogger(__name__)` which falls through to the unconfigured root logger.

**Fix:** Configure both Flask's logger AND the root logger.

```python
# app/middleware/logging.py
import logging
import sys

def setup_logging(app: Flask) -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Choose formatter
    if settings.log_format.lower() == 'json':
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # Configure ROOT logger so getLogger(__name__) works
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
    
    # Configure Flask's app.logger
    app.logger.handlers.clear()
    app.logger.addHandler(console_handler)
    app.logger.setLevel(log_level)
    app.logger.propagate = False
```

Also wrap `request` access in JSONFormatter with try-except:

```python
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Safely access request (may not exist in background threads)
        try:
            if request and request.method:
                log_entry.update({
                    'method': request.method,
                    'url': request.url,
                })
        except RuntimeError:
            pass  # No request context
        
        return json.dumps(log_entry, default=str)
```

### Issue 3: Process Crashes or OOM During Long-Running Tasks

**Symptoms:**
- Import/processing gets stuck at 15-25% and never progresses
- Service returns 503 after running for a while
- No error messages in logs

**Root cause:** Memory accumulation on 512MB RAM Starter plan.

**Memory leak sources:**
1. Large data structures (CSV rows, API responses) never freed
2. SQLAlchemy session identity map accumulating objects
3. Python objects with circular references not garbage collected
4. Background thread holding references to processed data

**Fix: Aggressive memory management**

```python
# During data pipeline in background thread
import gc

# 1. Delete large objects immediately after use
matcher = ProductMatcher(shopify_service)
matches = matcher.match_products(csv_products)

del csv_products, parser, downloader, matcher
gc.collect()

# 2. Release processed objects during iteration
for idx, match in enumerate(matches):
    # Process the match
    process_product(match)
    
    # Immediately release the match object
    matches[idx] = None
    
    # Expire SQLAlchemy cache after each commit
    db.session.commit()
    db.session.expire_all()
    
    # Periodic garbage collection
    if idx % 25 == 0:
        gc.collect()

# 3. Batch-commit for operations that don't need immediate persistence
pending_count = 0
for item in skipped_items:
    log_skip(item)
    pending_count += 1
    if pending_count >= 50:
        db.session.commit()
        db.session.expire_all()
        pending_count = 0
```

**Memory tracking during debug:**

```python
def _get_mem_mb() -> float:
    """Return current RSS in MB."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except Exception:
        return -1.0

# Log at key phases
logger.info(f"[MEM] phase=after_parse mem_mb={_get_mem_mb():.1f}")
logger.info(f"[MEM] phase=after_gc mem_mb={_get_mem_mb():.1f}")
```

### Issue 4: Background Tasks Block HTTP Responses

**Symptoms:**
- POST request to start import hangs for entire import duration
- Frontend shows loading spinner indefinitely
- Can't get progress updates

**Root cause:** Long-running work done in request handler instead of background thread.

**Fix:** Launch background thread, return immediately, poll for status.

```python
# app/routes/import_routes.py
import threading
from flask import current_app

def _run_import_in_background(app, job_id: int, token: str):
    """Run in background thread with Flask app context."""
    with app.app_context():
        job = ImportJob.query.get(job_id)
        # ... do the actual work ...
        job.status = 'completed'
        db.session.commit()

@import_bp.route('/start', methods=['POST'])
def start_import():
    # Create job record
    job = ImportJob(status='pending')
    db.session.add(job)
    db.session.commit()
    
    # Launch background thread
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_import_in_background,
        args=(app, job.id, token),
        daemon=True
    )
    thread.start()
    
    # Return immediately
    return jsonify({'job_id': job.id})

@import_bp.route('/status/<int:job_id>')
def get_status(job_id: int):
    """Frontend polls this every 2 seconds."""
    job = ImportJob.query.get_or_404(job_id)
    return jsonify(job.to_dict())
```

Frontend polling pattern:

```javascript
async function pollImportStatus(jobId) {
    while (true) {
        await new Promise(r => setTimeout(r, 2000));
        const resp = await fetch(`/api/import/status/${jobId}`);
        if (!resp.ok) continue;
        
        const data = await resp.json();
        updateProgress(data);
        
        if (data.status === 'completed' || data.status === 'failed') {
            break;
        }
    }
}
```

## Gunicorn Configuration for Render Starter Plan

```bash
# start.sh
exec gunicorn main:app \
  --workers 1 \
  --threads 8 \
  --bind 0.0.0.0:$PORT \
  --timeout 120 \
  --log-level info
```

**Why these settings:**
- `--workers 1`: Single process conserves RAM (each worker = ~100-150MB base)
- `--threads 8`: Handle concurrent requests without multiple processes
- `--timeout 120`: Short timeout since background threads handle long tasks
- Each request handler returns quickly; long work runs in background threads

## Diagnostic Pattern

When debugging mysterious crashes or stuck processes on Render:

1. **Enable structured logging** to see what's happening
2. **Add memory tracking** at key phases to identify leaks
3. **Check rate limiter** isn't blocking health checks
4. **Monitor Render logs** for OOM killer messages
5. **Profile locally first** with `memory_profiler` to find hotspots

```python
# Temporary diagnostic logging
logger.info(f"[DEBUG] phase=X value={y} mem_mb={_get_mem_mb():.1f}")
```

Remove diagnostic logs after confirming the fix works in production.

## Quick Reference

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| 503 after 25 min | Rate limiter blocking health check | Exempt `/health` from limits |
| No app logs | Root logger not configured | Configure `logging.getLogger()` |
| Stuck at 20% | Memory exhaustion (OOM) | Add gc.collect(), expire_all() |
| POST hangs forever | Work in request handler | Move to background thread |
| Works locally, fails Render | Resource limits hit | Reduce workers, optimize memory |

## When to Use Multiple Workers

Only use `--workers 2+` if:
- You have >= 1GB RAM available
- Most requests are I/O bound (waiting on databases/APIs)
- Memory profiling shows each worker uses < 30% of available RAM

For Starter plan (512MB), stick with `--workers 1 --threads 8`.
