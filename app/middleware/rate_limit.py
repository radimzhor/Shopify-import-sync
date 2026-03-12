"""
Rate limiting middleware for API endpoints.

Prevents abuse and protects against excessive API calls.
"""
from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def get_user_identifier():
    """
    Get unique identifier for rate limiting.
    
    Uses IP address for unauthenticated requests.
    For production, consider using user ID from JWT token.
    """
    return get_remote_address()


def _exempt_from_rate_limit() -> bool:
    """Skip rate limiting for health checks and import status polling."""
    return request.path == "/health" or request.path.startswith("/api/import/status/")


def init_rate_limiter(app: Flask) -> Limiter:
    """
    Initialize Flask-Limiter with app.
    
    Args:
        app: Flask application instance
        
    Returns:
        Configured Limiter instance
    """
    limiter = Limiter(
        app=app,
        key_func=get_user_identifier,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",
        strategy="fixed-window",
    )

    limiter.request_filter(_exempt_from_rate_limit)

    return limiter
