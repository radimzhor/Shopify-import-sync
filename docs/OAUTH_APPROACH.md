# OAuth Implementation Approach

## Current Design (MVP)

**Token Storage**: localStorage (client-side)  
**Token Management**: Frontend `AuthManager` JavaScript class  
**Backend Role**: Provides OAuth endpoints only

## Why This Approach?

1. **It Works**: The original template had this working
2. **Simplicity**: No server-side session management needed
3. **Frontend Control**: `AuthManager` handles token lifecycle automatically
4. **MVP First**: Can improve security post-MVP without breaking functionality

## Flow

```
User → /auth/login → Mergado OAuth → /auth/callback
                                           ↓
                                    Exchange code for tokens
                                           ↓
                                    Return HTML with <script>
                                           ↓
                                    localStorage.setItem(tokens)
                                           ↓
                                    Redirect to dashboard
```

## Frontend (AuthManager in base.html)

The `AuthManager` JavaScript class:
- Checks for tokens in localStorage on page load
- Redirects to login if no tokens
- Checks token expiry (5-minute buffer)
- Auto-refreshes via `/auth/refresh-token` POST endpoint
- Shows loading spinner vs. content

## Backend (app/auth/oauth.py)

Three simple endpoints:

1. **`GET /auth/login`** - Redirects to Mergado OAuth
2. **`GET /auth/callback`** - Exchanges code, returns HTML with JS to store tokens
3. **`POST /auth/refresh-token`** - Accepts refresh_token, returns new tokens

## Security Considerations

### Current (MVP)
- ✅ Tokens in localStorage (client-side)
- ✅ HTTPS in production (Render enforces)
- ✅ Never log tokens
- ✅ Simple and working

### Potential Improvements (Post-MVP)
- 🔄 HttpOnly cookies instead of localStorage (prevents XSS token theft)
- 🔄 Server-side session store (Redis)
- 🔄 OAuth state parameter validation (CSRF protection)
- 🔄 Token encryption at rest

**Decision**: Keep it simple for MVP. Security improvements can come later without breaking the working flow.

## Testing

```bash
# 1. Clear localStorage
localStorage.clear()

# 2. Navigate to app
# Should redirect to /auth/login

# 3. Complete Mergado OAuth flow

# 4. Check localStorage
localStorage.getItem('mergado_access_token')  // Should have value
localStorage.getItem('mergado_refresh_token')  // Should have value
localStorage.getItem('mergado_expires_at')     // Should have timestamp

# 5. Refresh page
# Should NOT redirect to login (AuthManager finds tokens)
```

## API Calls Pattern

When building API clients (Phase 2), use this pattern:

```python
# app/services/mergado_client.py
class MergadoClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
    
    def _request(self, method, url, **kwargs):
        headers = kwargs.get('headers', {})
        headers['Authorization'] = f'Bearer {self.access_token}'
        kwargs['headers'] = headers
        return requests.request(method, url, **kwargs)
```

In routes:
```python
@app.route('/api/projects')
def get_projects():
    # Frontend sends token in Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return {'error': 'Unauthorized'}, 401
    
    token = auth_header.split(' ')[1]
    client = MergadoClient(access_token=token)
    projects = client.get_projects(shop_id)
    return jsonify(projects)
```

## References

- Original template: Uses localStorage + AuthManager pattern
- [app/auth/CLAUDE.md](../app/auth/CLAUDE.md) - Detailed OAuth module guide
- [base.html](../app/templates/base.html) - AuthManager implementation (lines ~80-280)
