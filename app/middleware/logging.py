"""
Logging middleware for structured JSON logging.

Provides configurable logging with JSON format for production
and human-readable format for development.
"""
import json
import logging
import sys
import time
from typing import Dict, Any

from flask import Flask, request, g

from settings import settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Create base log entry
        log_entry = {
            'timestamp': self.formatTime(record, self.default_time_format),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        # Add request context if available
        try:
            if hasattr(g, 'request_id'):
                log_entry['request_id'] = g.request_id
        except RuntimeError:
            # No application context available
            pass

        if request:
            log_entry.update({
                'method': request.method,
                'url': request.url,
                'remote_addr': request.remote_addr,
                'user_agent': request.headers.get('User-Agent'),
            })

        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        # Add extra fields from record
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        return json.dumps(log_entry, default=str)


class RequestIDFilter(logging.Filter):
    """Filter to add request ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request ID to log record if available."""
        try:
            if hasattr(g, 'request_id'):
                record.request_id = g.request_id
        except RuntimeError:
            # No application context available
            pass
        return True


def setup_logging(app: Flask) -> None:
    """
    Setup application logging with appropriate formatters and handlers.

    Args:
        app: Flask application instance
    """
    # Clear existing handlers
    app.logger.handlers.clear()

    # Set log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    app.logger.setLevel(log_level)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Add request ID filter
    console_handler.addFilter(RequestIDFilter())

    # Choose formatter based on settings
    if settings.log_format.lower() == 'json':
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    console_handler.setFormatter(formatter)
    app.logger.addHandler(console_handler)

    # Prevent duplicate logs
    app.logger.propagate = False

    # Log application startup
    app.logger.info("Application logging initialized", extra={
        'extra_fields': {
            'log_format': settings.log_format,
            'log_level': settings.log_level,
            'environment': settings.flask_env,
        }
    })


def log_request_start() -> None:
    """Log the start of a request with timing."""
    g.request_start_time = time.time()
    g.request_id = f"{int(time.time() * 1000000)}"  # Simple request ID


def log_request_end(response) -> Any:
    """
    Log the end of a request with timing and status.

    Args:
        response: Flask response object

    Returns:
        The response object (unchanged)
    """
    if hasattr(g, 'request_start_time'):
        duration = time.time() - g.request_start_time
        current_app.logger.info("Request completed", extra={
            'extra_fields': {
                'status_code': response.status_code,
                'duration_ms': round(duration * 1000, 2),
                'content_length': response.headers.get('Content-Length'),
            }
        })

    return response


def init_request_logging(app: Flask) -> None:
    """
    Initialize request-level logging middleware.

    Args:
        app: Flask application instance
    """
    @app.before_request
    def before_request():
        """Set up request logging context."""
        log_request_start()

    @app.after_request
    def after_request(response):
        """Log request completion."""
        return log_request_end(response)
