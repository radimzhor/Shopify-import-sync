"""
Error handling middleware for the Mergado Flask application.

Provides centralized error handling with appropriate responses
for both API and web requests.
"""
import traceback
from typing import Dict, Any, Tuple

from flask import Flask, jsonify, render_template, current_app, request
from werkzeug.exceptions import HTTPException

from settings import settings


def register_error_handlers(app: Flask) -> None:
    """
    Register all error handlers with the Flask application.

    Args:
        app: Flask application instance
    """
    # HTTP exceptions (400, 404, 500, etc.)
    app.register_error_handler(HTTPException, handle_http_exception)

    # Generic exception handler for unhandled errors
    app.register_error_handler(Exception, handle_unexpected_error)

    # Specific error codes
    app.register_error_handler(400, handle_bad_request)
    app.register_error_handler(401, handle_unauthorized)
    app.register_error_handler(403, handle_forbidden)
    app.register_error_handler(404, handle_not_found)
    app.register_error_handler(422, handle_unprocessable_entity)
    app.register_error_handler(500, handle_internal_server_error)


def handle_http_exception(error: HTTPException) -> Tuple[Any, int]:
    """
    Handle HTTP exceptions with appropriate responses.

    Args:
        error: HTTPException instance

    Returns:
        Response tuple (data, status_code)
    """
    return _create_error_response(
        error.code,
        error.description or "An error occurred",
        error.__class__.__name__
    )


def handle_unexpected_error(error: Exception) -> Tuple[Any, int]:
    """
    Handle unexpected exceptions with detailed logging.

    Args:
        error: Exception instance

    Returns:
        Response tuple (data, status_code)
    """
    # Log the full traceback
    current_app.logger.error(
        "Unexpected error occurred",
        extra={
            'extra_fields': {
                'error_type': error.__class__.__name__,
                'error_message': str(error),
                'traceback': traceback.format_exc(),
                'url': request.url,
                'method': request.method,
            }
        }
    )

    return _create_error_response(
        500,
        "An unexpected error occurred" if not settings.flask_debug else str(error),
        error.__class__.__name__
    )


def handle_bad_request(error: Exception = None) -> Tuple[Any, int]:
    """Handle 400 Bad Request errors."""
    message = "Bad request" if error is None else str(error)
    return _create_error_response(400, message, "BadRequest")


def handle_unauthorized(error: Exception = None) -> Tuple[Any, int]:
    """Handle 401 Unauthorized errors."""
    message = "Authentication required" if error is None else str(error)
    return _create_error_response(401, message, "Unauthorized")


def handle_forbidden(error: Exception = None) -> Tuple[Any, int]:
    """Handle 403 Forbidden errors."""
    message = "Access forbidden" if error is None else str(error)
    return _create_error_response(403, message, "Forbidden")


def handle_not_found(error: Exception = None) -> Tuple[Any, int]:
    """Handle 404 Not Found errors."""
    message = "Resource not found" if error is None else str(error)
    return _create_error_response(404, message, "NotFound")


def handle_unprocessable_entity(error: Exception = None) -> Tuple[Any, int]:
    """Handle 422 Unprocessable Entity errors."""
    message = "Unprocessable entity" if error is None else str(error)
    return _create_error_response(422, message, "UnprocessableEntity")


def handle_internal_server_error(error: Exception = None) -> Tuple[Any, int]:
    """Handle 500 Internal Server Error."""
    message = "Internal server error" if error is None else str(error)
    return _create_error_response(500, message, "InternalServerError")


def _create_error_response(status_code: int, message: str, error_type: str) -> Tuple[Any, int]:
    """
    Create an appropriate error response based on request type.

    Args:
        status_code: HTTP status code
        message: Error message
        error_type: Type of error for logging

    Returns:
        Response tuple (data, status_code)
    """
    error_data = {
        'error': {
            'type': error_type,
            'message': message,
            'status_code': status_code,
        }
    }

    # Check if this is an API request or web request
    if _is_api_request():
        # Return JSON for API requests
        response = jsonify(error_data)
        response.status_code = status_code
        return response, status_code
    else:
        # Return HTML template for web requests
        template_name = f"errors/{status_code}.html"

        # Try to render specific error template, fall back to generic
        try:
            return render_template(
                template_name,
                error=error_data['error'],
                settings=settings
            ), status_code
        except Exception:
            # Fallback to generic error template
            return render_template(
                'errors/generic.html',
                error=error_data['error'],
                settings=settings
            ), status_code


def _is_api_request() -> bool:
    """
    Determine if the current request is an API request.

    Returns:
        True if API request, False if web request
    """
    # Check Accept header for JSON preference
    accept_header = request.headers.get('Accept', '')
    if 'application/json' in accept_header:
        return True

    # Check if URL starts with /api/
    if request.path.startswith('/api/'):
        return True

    # Check Content-Type for JSON requests
    content_type = request.headers.get('Content-Type', '')
    if 'application/json' in content_type:
        return True

    return False
