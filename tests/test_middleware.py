"""
Unit tests for middleware components.
"""
import json
import sys
import logging
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from app.middleware.error_handlers import (
    handle_http_exception,
    handle_unexpected_error,
    _create_error_response,
    _is_api_request,
)
from app.middleware.logging import JSONFormatter, RequestIDFilter
from settings import Settings


@pytest.fixture
def app():
    """Create a test Flask application."""
    test_settings = Settings(
        flask_secret_key="test_secret_key",
        flask_testing=True,
        flask_debug=False,
    )

    app = Flask(__name__)
    app.config['SECRET_KEY'] = test_settings.flask_secret_key
    app.config['TESTING'] = True
    app.settings = test_settings

    return app


class TestJSONFormatter:
    """Test cases for JSONFormatter."""

    def test_format_log_record(self):
        """Test JSON log record formatting."""
        formatter = JSONFormatter()

        # Create a test log record
        record = logging.LogRecord(
            name='test.logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=10,
            msg='Test message',
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert log_data['level'] == 'INFO'
        assert log_data['logger'] == 'test.logger'
        assert log_data['message'] == 'Test message'
        assert 'timestamp' in log_data

    def test_format_log_record_with_exception(self):
        """Test JSON formatting with exception info."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name='test.logger',
            level=logging.ERROR,
            pathname='test.py',
            lineno=10,
            msg='Error occurred',
            args=(),
            exc_info=exc_info,
        )

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert log_data['level'] == 'ERROR'
        assert 'exception' in log_data


class TestRequestIDFilter:
    """Test cases for RequestIDFilter."""

    def test_filter_without_request_id(self):
        """Test filter when no request ID in context."""
        from unittest.mock import patch

        with patch('app.middleware.logging.g') as mock_g:
            # Mock g to not have request_id attribute
            del mock_g.request_id

            filter_obj = RequestIDFilter()
            record = logging.LogRecord(
                name='test',
                level=logging.INFO,
                pathname='',
                lineno=0,
                msg='test',
                args=(),
                exc_info=None,
            )

            result = filter_obj.filter(record)
            assert result is True
            assert not hasattr(record, 'request_id')


class TestErrorHandlers:
    """Test cases for error handlers."""

    def test_handle_http_exception(self, app):
        """Test HTTP exception handling."""
        from werkzeug.exceptions import BadRequest

        with app.test_request_context():
            exception = BadRequest("Test bad request")
            response, status_code = handle_http_exception(exception)

            assert status_code == 400
            assert b"Test bad request" in response.get_data()

    def test_handle_unexpected_error_debug_mode(self, app):
        """Test unexpected error handling in debug mode."""
        app.settings.flask_debug = True

        with app.test_request_context():
            try:
                raise ValueError("Test error")
            except ValueError as e:
                response, status_code = handle_unexpected_error(e)

                assert status_code == 500
                response_data = response.get_json()
                assert response_data['error']['type'] == 'ValueError'

    def test_handle_unexpected_error_production_mode(self, app):
        """Test unexpected error handling in production mode."""
        app.settings.flask_debug = False

        with app.test_request_context():
            try:
                raise ValueError("Test error")
            except ValueError as e:
                response, status_code = handle_unexpected_error(e)

                assert status_code == 500
                response_data = response.get_json()
                assert "An unexpected error occurred" in response_data['error']['message']

    def test_is_api_request_json_accept(self, app):
        """Test API request detection by Accept header."""
        with app.test_request_context(headers={'Accept': 'application/json'}):
            assert _is_api_request() is True

    def test_is_api_request_url_path(self, app):
        """Test API request detection by URL path."""
        with app.test_request_context('/api/test'):
            assert _is_api_request() is True

    def test_is_api_request_content_type(self, app):
        """Test API request detection by Content-Type."""
        with app.test_request_context(
            headers={'Content-Type': 'application/json'},
            method='POST'
        ):
            assert _is_api_request() is True

    def test_is_api_request_web_request(self, app):
        """Test that regular web requests are not considered API requests."""
        with app.test_request_context('/dashboard'):
            assert _is_api_request() is False

    @patch('app.middleware.error_handlers.render_template')
    def test_create_error_response_web_request(self, mock_render, app):
        """Test error response creation for web requests."""
        mock_render.return_value = "<html>Error</html>"

        with app.test_request_context('/dashboard'):
            response, status_code = _create_error_response(404, "Not found", "NotFound")

            assert status_code == 404
            mock_render.assert_called_once()

    def test_create_error_response_api_request(self, app):
        """Test error response creation for API requests."""
        with app.test_request_context(
            '/api/test',
            headers={'Accept': 'application/json'}
        ):
            response, status_code = _create_error_response(400, "Bad request", "BadRequest")

            assert status_code == 400
            response_data = response.get_json()
            assert response_data['error']['message'] == "Bad request"
            assert response_data['error']['status_code'] == 400
