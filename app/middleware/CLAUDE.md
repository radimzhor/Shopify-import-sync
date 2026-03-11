# app/middleware/ - Middleware Layer

This module contains Flask middleware that processes requests and responses before they reach routes or after they leave.

## What's Here

- `logging.py` - Request/response logging with unique request IDs
- `error_handlers.py` - Global error handlers for all exceptions

## Request Lifecycle

```
1. HTTP Request arrives
   ↓
2. Logging middleware (before_request)
   - Generate request ID
   - Log incoming request
   ↓
3. Route handler executes
   - Business logic
   - Returns response or raises exception
   ↓
4a. Success path:
    - Logging middleware (after_request)
    - Log response
    - Return to client
    
4b. Error path:
    - Error handler catches exception
    - Logs error
    - Returns error response (JSON or HTML)
```

## Logging Middleware

### Request ID Generation
Every request gets a unique ID for tracing across logs:

```python
import uuid
from flask import g

@app.before_request
def generate_request_id():
    g.request_id = str(uuid.uuid4())
```

### Structured Logging
Use JSON format in production for easy parsing:

```python
import logging
import json
from flask import request, g

logger = logging.getLogger(__name__)

@app.before_request
def log_request():
    logger.info("Request started", extra={
        "request_id": g.request_id,
        "method": request.method,
        "path": request.path,
        "remote_addr": request.remote_addr,
        "user_agent": request.user_agent.string
    })

@app.after_request
def log_response(response):
    logger.info("Request completed", extra={
        "request_id": g.request_id,
        "status_code": response.status_code,
        "content_length": response.content_length
    })
    return response
```

### Log Formats

**Development** (human-readable):
```
2026-03-04 10:15:30 INFO Request started: GET /api/projects
2026-03-04 10:15:31 INFO Request completed: 200 OK (1.2s)
```

**Production** (JSON):
```json
{
  "timestamp": "2026-03-04T10:15:30Z",
  "level": "INFO",
  "message": "Request started",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "method": "GET",
  "path": "/api/projects",
  "remote_addr": "192.168.1.1"
}
```

## Error Handlers

### Global Exception Handler
```python
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error("Unhandled exception", extra={
        "request_id": g.request_id,
        "error": str(e),
        "path": request.path
    }, exc_info=True)
    
    # Return JSON for API requests
    if request.path.startswith('/api/') or request.accept_mimetypes.accept_json:
        return jsonify({
            "error": "Internal server error",
            "request_id": g.request_id
        }), 500
    
    # Return HTML for web requests
    return render_template('errors/500.html', request_id=g.request_id), 500
```

### HTTP Exception Handlers
```python
@app.errorhandler(404)
def not_found(e):
    if request.accept_mimetypes.accept_json:
        return jsonify({"error": "Not found"}), 404
    return render_template('errors/404.html'), 404

@app.errorhandler(401)
def unauthorized(e):
    if request.accept_mimetypes.accept_json:
        return jsonify({"error": "Unauthorized"}), 401
    return redirect(url_for('auth.login'))
```

### Custom Exception Handlers
```python
from app.services.exceptions import APIError, ValidationError

@app.errorhandler(APIError)
def handle_api_error(e):
    logger.error(f"API error: {e.message}", extra={
        "request_id": g.request_id,
        "status_code": e.status_code,
        "details": e.details
    })
    return jsonify({
        "error": e.message,
        "request_id": g.request_id
    }), e.status_code or 500

@app.errorhandler(ValidationError)
def handle_validation_error(e):
    return jsonify({
        "error": "Validation failed",
        "details": str(e)
    }), 400
```

## Security Considerations

### Don't Log Sensitive Data
```python
# WRONG - logs access token!
logger.info(f"User authenticated: {session.get('access_token')}")

# RIGHT - log non-sensitive info only
logger.info("User authenticated", extra={
    "user_id": session.get('user_id'),
    "expires_at": session.get('expires_at')
})
```

### Sanitize Error Messages
```python
# WRONG - exposes internal details to users
return jsonify({"error": f"Database query failed: {sql_error}"}), 500

# RIGHT - generic message for users, detailed log for developers
logger.error(f"Database error: {sql_error}", exc_info=True)
return jsonify({"error": "An internal error occurred", "request_id": g.request_id}), 500
```

## Performance Monitoring

### Request Timing
```python
import time

@app.before_request
def start_timer():
    g.start_time = time.time()

@app.after_request
def log_timing(response):
    duration = time.time() - g.start_time
    logger.info("Request timing", extra={
        "request_id": g.request_id,
        "duration_ms": int(duration * 1000),
        "path": request.path
    })
    return response
```

### Slow Request Alerting
```python
SLOW_REQUEST_THRESHOLD = 3.0  # seconds

@app.after_request
def alert_slow_requests(response):
    duration = time.time() - g.start_time
    if duration > SLOW_REQUEST_THRESHOLD:
        logger.warning("Slow request detected", extra={
            "request_id": g.request_id,
            "duration_s": duration,
            "path": request.path,
            "method": request.method
        })
    return response
```

## CORS Handling (if needed)

```python
from flask_cors import CORS

# Allow CORS for API endpoints only
CORS(app, resources={r"/api/*": {"origins": "https://app.mergado.com"}})
```

## Request Context Helpers

### Getting Current User
```python
from flask import g

@app.before_request
def load_user():
    g.user_id = session.get('user_id')
    g.access_token = session.get('access_token')

# Usage in routes:
@app.route('/api/projects')
def get_projects():
    if not g.access_token:
        return jsonify({"error": "Not authenticated"}), 401
    
    client = MergadoClient(access_token=g.access_token)
    projects = client.get_projects(g.user_id)
    return jsonify(projects)
```

## Testing Middleware

### Test Error Handlers
```python
def test_404_handler(client):
    response = client.get('/nonexistent')
    assert response.status_code == 404
    assert b'Not Found' in response.data

def test_404_handler_json(client):
    response = client.get('/api/nonexistent')
    assert response.status_code == 404
    assert response.json['error'] == 'Not found'
```

### Test Request ID Generation
```python
def test_request_id_generated(client, caplog):
    with caplog.at_level(logging.INFO):
        response = client.get('/health')
        
        # Check request ID in logs
        assert any('request_id' in record.message for record in caplog.records)
```

## Common Gotchas

### 1. Flask Context Not Available
```python
# WRONG - no request context in background jobs
def background_task():
    logger.info(f"Processing for {request.path}")  # Error!

# RIGHT - pass data explicitly
def background_task(path):
    logger.info(f"Processing for {path}")
```

### 2. Response Modified After Error Handler
```python
# WRONG - after_request still runs after error handler
@app.after_request
def add_header(response):
    response.headers['X-Custom'] = 'value'
    return response

@app.errorhandler(500)
def handle_error(e):
    return "Error", 500  # Missing custom header!

# RIGHT - add headers in error handler too
@app.errorhandler(500)
def handle_error(e):
    response = make_response("Error", 500)
    response.headers['X-Custom'] = 'value'
    return response
```

### 3. Logging Before Logger Configuration
```python
# WRONG - logger not configured yet
logger = logging.getLogger(__name__)
logger.info("Starting app")  # Might not appear

# RIGHT - configure logger first
def create_app():
    app = Flask(__name__)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s'
    )
    
    logger.info("App created")
    return app
```

## References

- [Flask Error Handling](https://flask.palletsprojects.com/en/2.3.x/errorhandling/)
- [Python Logging](https://docs.python.org/3/library/logging.html)
- [Structured Logging Best Practices](https://www.structlog.org/)
