# app/auth/ - Authentication Module

⚠️ **IMPORTANT** - This module handles OAuth authentication. Keep it simple and working.

## What's Here

- `oauth.py` - Mergado OAuth 2.0 implementation
- OAuth login flow, callback handling, token management

## Current Implementation (MVP)

**Token Storage**: Tokens are stored in **localStorage** (client-side), managed by `AuthManager` JavaScript in `base.html`.

**Why localStorage?**: 
- Simple and working in the template
- No server-side session management needed
- Frontend handles token refresh automatically
- Can improve security post-MVP if needed

## Security Rules

### NEVER
- ❌ Log access tokens or refresh tokens
- ❌ Expose tokens in error messages or API responses
- ❌ Commit hardcoded client secrets

### ALWAYS
- ✅ Use HTTPS in production (enforced by Render)
- ✅ Let frontend `AuthManager` handle token lifecycle
- ✅ Backend just provides OAuth endpoints

## OAuth Flow

```
1. User clicks "Connect with Mergado" (in frontend)
   → frontend redirects to /auth/login

2. Backend redirects to Mergado OAuth authorize URL
   → with client_id, redirect_uri

3. User approves in Mergado

4. Mergado redirects to /auth/callback
   → with authorization code

5. Backend exchanges code for tokens
   → POST to Mergado token endpoint
   → receives access_token, refresh_token, expires_in

6. Backend returns HTML with inline JS
   → JS stores tokens in localStorage
   → JS redirects to dashboard

7. Frontend AuthManager handles:
   → Token expiry checking
   → Automatic refresh via /auth/refresh-token
   → Redirecting to login if expired
```

## Common Gotchas

### 1. Token Expiry
**Handled by Frontend**: The `AuthManager` in `base.html` automatically checks token expiry and refreshes via `/auth/refresh-token` endpoint.

**Backend just needs to provide the refresh endpoint:**
```python
@auth_bp.route("/refresh-token", methods=['POST'])
def refresh_token():
    data = request.get_json()
    refresh_token = data.get('refresh_token')
    # Call oauth.refresh_access_token(refresh_token)
    # Return new tokens as JSON
```

### 2. Error Handling
**Don't expose sensitive info:**
```python
# Bad:
return {"error": f"OAuth failed: {token_response.text}"}

# Good:
logger.error(f"OAuth token exchange failed: {token_response.text}")
return {"error": "Authentication failed. Please try again."}
```

### 3. Callback Must Return HTML with JS
The callback **must** return HTML that stores tokens in localStorage:
```python
html = f"""
<script>
    localStorage.setItem('mergado_access_token', '{tokens['access_token']}');
    localStorage.setItem('mergado_refresh_token', '{tokens['refresh_token']}');
    localStorage.setItem('mergado_expires_at', '{tokens['expires_at']}');
    window.location.href = '/';
</script>
"""
return html
```

Don't try to redirect before storing tokens!

## Token Storage

### Current Approach (localStorage - MVP)
```javascript
// Frontend (AuthManager in base.html):
localStorage.setItem('mergado_access_token', token);
localStorage.setItem('mergado_refresh_token', refresh);
localStorage.setItem('mergado_expires_at', expires);
```

**Pros**:
- Simple and working
- No server-side session needed
- Frontend handles all token lifecycle
- Persistent across page reloads

**Cons**:
- Vulnerable to XSS (if we have XSS bugs)
- Can improve post-MVP if needed

**Post-MVP**: Can switch to HttpOnly cookies or server-side sessions for better security.

## OAuth Scopes Required

```python
REQUIRED_SCOPES = [
    "shop.read",
    "shop.projects.read",
    "shop.proxy.read",
    "shop.proxy.write",
    "project.read",
    "project.elements.read",
    "project.elements.write",
    "project.products.read",
    "project.rules.write",
    "project.queries.write",
]
```

Set in `settings.py` and passed to OAuth authorize URL.

## Debugging OAuth Issues

### "Redirect URI mismatch"
- Check `MERGADO_REDIRECT_URI` in `.env`
- Must match EXACTLY what's in Mergado Dev Portal (including https://)

### "Invalid client"
- Check `MERGADO_CLIENT_ID` and `MERGADO_CLIENT_SECRET`
- Verify they're for the correct environment (dev vs production)

### "Invalid state"
- State validation is working (good!)
- User may have bookmarked /callback URL
- Or session expired between steps 3 and 5

### Token refresh fails
- Refresh token may have expired (typically 30 days)
- User needs to re-authenticate

## Testing Authentication

### Unit Tests
```python
def test_oauth_callback_validates_state(client, mocker):
    # Mock token exchange
    mocker.patch.object(oauth, 'exchange_code_for_tokens', return_value={...})
    
    # Call callback without state
    response = client.get('/auth/callback?code=123')
    assert response.status_code == 400  # Should reject
    
    # Call with mismatched state
    with client.session_transaction() as sess:
        sess['oauth_state'] = 'valid_state'
    response = client.get('/auth/callback?code=123&state=wrong_state')
    assert response.status_code == 400  # Should reject
```

### Manual Testing
1. Clear localStorage in browser DevTools
2. Click "Connect with Mergado"
3. Verify redirected to Mergado
4. Approve in Mergado
5. Verify redirected back to home page
6. Check localStorage contains tokens:
   - Open DevTools → Application → Local Storage
   - Should see `mergado_access_token`, `mergado_refresh_token`, `mergado_expires_at`
7. Navigate to dashboard - should work (not redirect to login)

## References

- OAuth 2.0 Spec: https://tools.ietf.org/html/rfc6749
- Mergado OAuth Docs: https://api-docs.mergado.com/?specs=mergado-api#/Authorization
- OWASP OAuth Security: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
