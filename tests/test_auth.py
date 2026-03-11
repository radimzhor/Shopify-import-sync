"""
Unit tests for Mergado OAuth authentication module.
"""
import json
import time
from unittest.mock import Mock, patch, MagicMock

import pytest
from flask import Flask, session

from app.auth.oauth import MergadoOAuth, oauth, require_auth
from settings import Settings


@pytest.fixture
def app():
    """Create a test Flask application."""
    test_settings = Settings(
        mergado_client_id="test_client_id",
        mergado_client_secret="test_client_secret",
        mergado_redirect_uri="http://localhost:5000/callback",
        flask_secret_key="test_secret_key",
        flask_testing=True,
    )

    app = Flask(__name__)
    app.config['SECRET_KEY'] = test_settings.flask_secret_key
    app.config['TESTING'] = True

    # Store settings on app for access in tests
    app.settings = test_settings

    with app.app_context():
        yield app


@pytest.fixture
def oauth_instance(app):
    """Create a MergadoOAuth instance for testing."""
    return MergadoOAuth()


class TestMergadoOAuth:
    """Test cases for MergadoOAuth class."""

    def test_initialization(self, oauth_instance):
        """Test OAuth instance initialization."""
        assert oauth_instance.client_id == "test_client_id"
        assert oauth_instance.client_secret == "test_client_secret"
        assert oauth_instance.redirect_uri == "http://localhost:5000/callback"

    def test_get_authorization_url(self, oauth_instance):
        """Test authorization URL generation."""
        url = oauth_instance.get_authorization_url()
        assert "https://app.mergado.com/oauth2/authorize" in url
        assert "response_type=code" in url
        assert "client_id=test_client_id" in url

    def test_get_authorization_url_with_state(self, oauth_instance):
        """Test authorization URL with state parameter."""
        url = oauth_instance.get_authorization_url("test_state")
        assert "state=test_state" in url

    @patch('app.auth.oauth.requests.post')
    def test_exchange_code_for_tokens_success(self, mock_post, oauth_instance):
        """Test successful token exchange."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'access_token': 'test_access_token',
            'refresh_token': 'test_refresh_token',
            'expires_in': 3600,
        }
        mock_post.return_value = mock_response

        tokens = oauth_instance.exchange_code_for_tokens('test_code')

        assert tokens['access_token'] == 'test_access_token'
        assert tokens['refresh_token'] == 'test_refresh_token'
        assert 'expires_at' in tokens
        assert isinstance(tokens['expires_at'], float)

    @patch('app.auth.oauth.requests.post')
    def test_exchange_code_for_tokens_failure(self, mock_post, oauth_instance):
        """Test token exchange failure."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_post.return_value = mock_response

        with pytest.raises(Exception):
            oauth_instance.exchange_code_for_tokens('test_code')

    @patch('app.auth.oauth.requests.post')
    def test_refresh_access_token_success(self, mock_post, oauth_instance):
        """Test successful token refresh."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'access_token': 'new_access_token',
            'refresh_token': 'new_refresh_token',
            'expires_in': 3600,
        }
        mock_post.return_value = mock_response

        tokens = oauth_instance.refresh_access_token('old_refresh_token')

        assert tokens['access_token'] == 'new_access_token'
        assert tokens['refresh_token'] == 'new_refresh_token'

    def test_is_token_expired_false(self, oauth_instance):
        """Test token not expired."""
        future_time = time.time() + 3600  # 1 hour from now
        assert not oauth_instance.is_token_expired(future_time)

    def test_is_token_expired_true(self, oauth_instance):
        """Test token expired."""
        past_time = time.time() - 3600  # 1 hour ago
        assert oauth_instance.is_token_expired(past_time)

    def test_is_token_expired_soon(self, oauth_instance):
        """Test token expires soon (within 5 minutes)."""
        soon_time = time.time() + 200  # 3 minutes from now
        assert oauth_instance.is_token_expired(soon_time)


class TestOAuthIntegration:
    """Test OAuth integration with Flask session."""

    def test_get_valid_access_token_no_tokens(self, app, oauth_instance):
        """Test getting access token when no tokens exist."""
        with app.test_request_context():
            session.clear()
            token = oauth_instance.get_valid_access_token()
            assert token is None

    def test_get_valid_access_token_valid(self, app, oauth_instance):
        """Test getting valid access token."""
        with app.test_request_context():
            session['access_token'] = 'test_token'
            session['refresh_token'] = 'test_refresh'
            session['expires_at'] = time.time() + 3600

            token = oauth_instance.get_valid_access_token()
            assert token == 'test_token'

    @patch.object(MergadoOAuth, 'refresh_access_token')
    def test_get_valid_access_token_refresh(self, mock_refresh, app, oauth_instance):
        """Test automatic token refresh."""
        mock_refresh.return_value = {
            'access_token': 'new_token',
            'refresh_token': 'new_refresh',
            'expires_at': time.time() + 3600,
        }

        with app.test_request_context():
            session['access_token'] = 'old_token'
            session['refresh_token'] = 'old_refresh'
            session['expires_at'] = time.time() - 100  # Expired

            token = oauth_instance.get_valid_access_token()

            assert token == 'new_token'
            mock_refresh.assert_called_once_with('old_refresh')

    @patch.object(MergadoOAuth, 'refresh_access_token')
    def test_get_valid_access_token_refresh_failure(self, mock_refresh, app, oauth_instance):
        """Test token refresh failure clears session."""
        from requests import HTTPError
        mock_refresh.side_effect = HTTPError("Refresh failed")

        with app.test_request_context():
            session['access_token'] = 'old_token'
            session['refresh_token'] = 'old_refresh'
            session['expires_at'] = time.time() - 100

            token = oauth_instance.get_valid_access_token()

            assert token is None
            assert 'access_token' not in session
            assert 'refresh_token' not in session
            assert 'expires_at' not in session


class TestOAuthDecorator:
    """Test the require_auth decorator."""

    def test_require_auth_authenticated(self, app, monkeypatch):
        """Test decorator allows authenticated requests."""
        with app.test_request_context():
            # Mock authenticated state
            monkeypatch.setattr('app.auth.oauth.oauth.get_valid_access_token', lambda: 'test_token')

            @require_auth
            def test_function():
                return "success"

            result = test_function()
            assert result == "success"

    def test_require_auth_not_authenticated(self, app, monkeypatch):
        """Test decorator redirects unauthenticated requests."""
        from flask import url_for

        with app.test_request_context():
            # Mock unauthenticated state
            monkeypatch.setattr('app.auth.oauth.oauth.get_valid_access_token', lambda: None)

            @require_auth
            def test_function():
                return "should not reach here"

            with pytest.raises(RuntimeError):  # url_for needs app context for redirect
                test_function()
