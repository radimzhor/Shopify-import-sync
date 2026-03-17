"""
Mergado OAuth2 authorization module.

Handles the complete OAuth2 flow for Mergado app authorization,
including token storage, refresh logic, and session management.
"""
import time
from typing import Dict, Optional, Tuple

import requests
from flask import Blueprint, redirect, request, session, url_for, current_app, jsonify

from settings import settings


auth_bp = Blueprint('auth', __name__)


class MergadoOAuth:
    """Handles Mergado OAuth2 authentication flow."""

    def __init__(self):
        """Initialize OAuth handler with settings."""
        self.client_id = settings.mergado_client_id
        self.client_secret = settings.mergado_client_secret
        self.redirect_uri = settings.mergado_redirect_uri
        self.auth_url = settings.mergado_auth_url
        self.token_url = settings.mergado_token_url
        self.api_base_url = settings.mergado_api_base_url

    def get_authorization_url(
        self,
        state: str = None,
        entity_id: str = None,
    ) -> str:
        """
        Generate the authorization URL for Mergado OAuth.

        For Store extensions bound to a shop or project, Mergado requires entity_id
        in the authorization request. Mergado passes entity_id when opening the app
        from the Store (e.g. in the initial URL or when redirecting to login).

        Args:
            state: Optional state parameter for CSRF protection
            entity_id: Required for shop/project app types; ID of the shop (or project)

        Returns:
            Complete authorization URL
        """
        params = {
            'response_type': 'code',
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
        }

        if state:
            params['state'] = state

        # Required for shop/project app types; omit for user-type apps
        if entity_id:
            params['entity_id'] = str(entity_id)

        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"{self.auth_url}?{query_string}"

    def exchange_code_for_tokens(self, code: str) -> Dict[str, str]:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from callback

        Returns:
            Dictionary containing access_token, refresh_token, etc.

        Raises:
            requests.HTTPError: If token exchange fails
        """
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }

        response = requests.post(self.token_url, data=data)
        response.raise_for_status()

        tokens = response.json()
        # Add token expiration time
        tokens['expires_at'] = time.time() + tokens.get('expires_in', 3600)

        return tokens

    def refresh_access_token(self, refresh_token: str) -> Dict[str, str]:
        """
        Refresh an expired access token using the refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New token dictionary

        Raises:
            requests.HTTPError: If token refresh fails
        """
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }

        response = requests.post(self.token_url, data=data)
        response.raise_for_status()

        tokens = response.json()
        tokens['expires_at'] = time.time() + tokens.get('expires_in', 3600)

        return tokens

    def is_token_expired(self, expires_at: float) -> bool:
        """
        Check if a token is expired or will expire soon.

        Args:
            expires_at: Token expiration timestamp

        Returns:
            True if token is expired or expires within 5 minutes
        """
        # Consider token expired if it expires within 5 minutes
        return time.time() > (expires_at - 300)


# Global OAuth instance
oauth = MergadoOAuth()


@auth_bp.route("/login")
def login():
    """
    Initiate Mergado OAuth login flow.

    For Store extensions (shop/project type), Mergado sends entity_id or eshop
    when opening the app. Pass it through so Mergado can authorize in the correct context.
    """
    state = request.args.get('state')
    # Mergado Store opens the app with ?eshop=<id>; OAuth API expects entity_id
    entity_id = request.args.get('entity_id') or request.args.get('eshop')
    auth_url = oauth.get_authorization_url(state=state, entity_id=entity_id)
    return redirect(auth_url)


@auth_bp.route("/callback")
def callback():
    """Handle OAuth callback and exchange code for tokens."""
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        error_description = request.args.get("error_description", "Unknown error")
        current_app.logger.error(f"OAuth error: {error} - {error_description}")
        return redirect(url_for('routes.index', error=error))

    if not code:
        current_app.logger.error("No authorization code received")
        return redirect(url_for('routes.index', error='no_code'))

    try:
        tokens = oauth.exchange_code_for_tokens(code)
        current_app.logger.info(
            "Successfully authenticated with Mergado"
            f" (entity_id={tokens.get('entity_id')}, user_id={tokens.get('user_id')})"
        )
        
        entity_id = tokens.get('entity_id', '')
        user_id = tokens.get('user_id', '')
        refresh_token_val = tokens.get('refresh_token', '')
        
        # Store tokens in database for background sync operations
        from app import db
        from app.models.shop import Shop
        from datetime import datetime, timedelta
        
        if entity_id:
            shop = Shop.query.filter_by(mergado_shop_id=entity_id).first()
            if shop:
                shop.access_token = tokens['access_token']
                shop.refresh_token = refresh_token_val
                # Calculate expiry time (typically 1 hour from now)
                expires_in = tokens.get('expires_in', 3600)
                shop.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                db.session.commit()
                current_app.logger.info(f"Updated tokens in database for shop {shop.id}")

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Authenticating...</title>
</head>
<body>
    <div style="text-align: center; padding: 50px;">
        <h2>Connecting to Mergado...</h2>
        <p>Please wait while we complete authentication.</p>
    </div>
    <script>
        localStorage.setItem('mergado_access_token', '{tokens['access_token']}');
        if ('{refresh_token_val}') {{
            localStorage.setItem('mergado_refresh_token', '{refresh_token_val}');
        }}
        localStorage.setItem('mergado_expires_at', '{tokens['expires_at']}');
        localStorage.setItem('mergado_entity_id', '{entity_id}');
        localStorage.setItem('mergado_user_id', '{user_id}');
        window.location.href = '/';
    </script>
</body>
</html>
"""
        return html
        
    except requests.HTTPError as e:
        current_app.logger.error(f"Token exchange failed: {e}")
        return redirect(url_for('routes.index', error='token_exchange_failed'))


@auth_bp.route("/refresh-token", methods=['POST'])
def refresh_token():
    """Refresh access token endpoint."""
    data = request.get_json()
    refresh_token = data.get('refresh_token')

    if not refresh_token:
        return jsonify({
            'success': False,
            'error': 'no_refresh_token',
            'error_description': 'No refresh token provided'
        }), 400

    try:
        tokens = oauth.refresh_access_token(refresh_token)

        current_app.logger.info("Successfully refreshed Mergado access token")

        return jsonify({
            'success': True,
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'expires_at': tokens['expires_at'],
            'expires_in': tokens.get('expires_in', 3600)
        })

    except requests.HTTPError as e:
        current_app.logger.error(f"Token refresh failed: {e}")
        return jsonify({
            'success': False,
            'error': 'token_refresh_failed',
            'error_description': 'Failed to refresh access token'
        }), 500


def require_auth(f):
    """
    Decorator to require valid Mergado authentication.

    Note: This decorator now checks for tokens in request headers
    since tokens are stored in localStorage on frontend.
    """
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check Authorization header first
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            return f(*args, **kwargs)

        # Fallback: check query parameter (needed for SSE/EventSource which can't set headers)
        token_param = request.args.get('token')
        if token_param:
            return f(*args, **kwargs)

        # For web routes, redirect to login; preserve entity_id/eshop/entity_type
        # so Store extensions get the right OAuth context (Mergado requires entity_id for shop/project apps)
        next_url = url_for('auth.login')
        passthrough = {}
        for key in ('entity_id', 'eshop', 'entity_type', 'state'):
            if request.args.get(key):
                passthrough[key] = request.args.get(key)
        if passthrough:
            from urllib.parse import urlencode
            next_url += '?' + urlencode(passthrough)
        return redirect(next_url)

    return decorated_function
