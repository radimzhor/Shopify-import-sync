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

### Shop-Scoped OAuth (Critical for Store Extensions)

When your app is a **Mergado Store extension** (not a standalone user app), it must be authorized in the context of a specific shop. This requires passing `entity_id` to Mergado's OAuth authorize endpoint.

**How Mergado opens Store extensions:**
- User opens app from Store (e.g., from a shop's app list)
- Mergado redirects to your app with **`?eshop=<shop_id>`** (or `?entity_id=<shop_id>`)
- Your app must forward this to `/auth/login` and then to Mergado's authorize URL

**Implementation:**

```python
# app/auth/oauth.py - get_authorization_url()
def get_authorization_url(self, state: str = None, entity_id: str = None) -> str:
    params = {
        'response_type': 'code',
        'grant_type': 'authorization_code',  # Required by Mergado
        'client_id': self.client_id,
        'redirect_uri': self.redirect_uri,
    }
    if state:
        params['state'] = state
    if entity_id:  # CRITICAL for shop-scoped apps
        params['entity_id'] = str(entity_id)
    return f"{self.auth_url}?{urlencode(params)}"

# app/auth/oauth.py - login route
@auth_bp.route("/login")
def login():
    state = request.args.get('state')
    # Mergado sends 'eshop' param; OAuth API expects 'entity_id'
    entity_id = request.args.get('entity_id') or request.args.get('eshop')
    auth_url = oauth.get_authorization_url(state=state, entity_id=entity_id)
    return redirect(auth_url)
```

**Frontend preservation (app/templates/base.html):**
```javascript
// AuthManager.startOAuth() - preserve entity_id when redirecting to login
startOAuth() {
    const params = new URLSearchParams(window.location.search);
    const passthrough = new URLSearchParams();
    ['entity_id', 'eshop', 'entity_type', 'state'].forEach(key => {
        if (params.has(key)) passthrough.set(key, params.get(key));
    });
    const query = passthrough.toString();
    const loginUrl = '/auth/login' + (query ? '?' + query : '');
    window.location.replace(loginUrl);
}
```

**Token response:**
The Mergado token response includes `entity_id` and `user_id`. Store these in localStorage for future API calls:

```javascript
// app/auth/oauth.py - callback route
localStorage.setItem('mergado_entity_id', '{entity_id}');
localStorage.setItem('mergado_user_id', '{user_id}');
```

**Common error:**
- `error=missing_entity_id` → You didn't pass `entity_id` to the authorize URL
- **403 FORBIDDEN** on API calls → Token was issued without `entity_id` (user-level token trying to access shop resources)

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

## Required OAuth Scopes

Configure these in the Mergado developer portal (your app settings) **before** users authenticate:

| Scope | Description | Used for |
|-------|-------------|----------|
| `shop.read` | Read shop info | Basic shop data |
| `shop.projects.read` | List shop projects | **Required** to call `/shops/{id}/projects/` |
| `project.read` | Read project details | Feed URL, output format |
| `project.products.read` | Read products | Import products from feed |
| `project.products.write` | Update products | Product data changes |
| `project.elements.read` | Read element definitions | Check existing elements |
| `project.elements.write` | Create/update elements | Shopify ID writeback |
| `project.rules.write` | Create/update rules | Writeback automation |
| `project.queries.write` | Create/update queries | Query creation |
| `project.logs.read` | Read project logs | Error monitoring |
| `shop.proxy.read` | Read via Shopify proxy | Shopify API read operations |
| `shop.proxy.write` | Write via Shopify proxy | Shopify API write operations |

**Without proper scopes, API calls return 403 FORBIDDEN** even with a valid token.

## API Calls Pattern

When building API clients (Phase 2), use this pattern:

```python
# app/services/mergado_client.py
class MergadoClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = 'https://api.mergado.com'
    
    def _request(self, method, path, **kwargs):
        url = urljoin(self.base_url, path.lstrip('/'))
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {self.access_token}'
        headers['Content-Type'] = 'application/json'
        response = requests.request(method, url, headers=headers, **kwargs)
        
        if response.status_code == 401:
            raise AuthenticationError("Access token expired or invalid")
        if response.status_code == 403:
            raise AuthenticationError("Token lacks required scope for this operation")
        
        response.raise_for_status()
        return response
```

In routes:
```python
@app.route('/api/project/shops/<shop_id>/projects')
def get_projects(shop_id):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return {'error': 'Unauthorized'}, 401
    
    token = auth_header.replace('Bearer ', '')
    client = MergadoClient(access_token=token)
    projects = client.get_projects(shop_id)  # Requires shop.projects.read scope
    return jsonify({'projects': projects})
```

## References

- Original template: Uses localStorage + AuthManager pattern
- [app/auth/CLAUDE.md](../app/auth/CLAUDE.md) - Detailed OAuth module guide
- [base.html](../app/templates/base.html) - AuthManager implementation (lines ~80-280)
