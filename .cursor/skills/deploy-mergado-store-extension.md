# Deploy Mergado Store Extension

## Overview
Comprehensive guide for deploying Mergado Store extensions (Flask apps) with shop-scoped OAuth, including all common pitfalls and their solutions.

## When to Use
- Deploying a Flask app as a Mergado Store extension
- Debugging "Not Found" or 403 errors on deployed Mergado apps
- Setting up shop-scoped OAuth for Mergado apps
- Configuring Docker deployments on Render for Flask + Mergado

## Prerequisites
- Flask app with Mergado OAuth
- Mergado developer account with app registered
- Docker and Dockerfile (if using containerized deployment)
- Render account (or similar PaaS)

---

## Part 1: OAuth Configuration for Shop-Scoped Apps

### 1.1 Understanding Shop-Scoped OAuth

**Key Concept:** When your app is opened from the Mergado Store (not a standalone user app), Mergado requires `entity_id` in the OAuth flow.

- **User app**: OAuth without `entity_id` → token scoped to user
- **Shop app**: OAuth **with `entity_id`** → token scoped to shop

**Mergado sends:**
- `?eshop=<shop_id>` when opening your app from the Store
- You must forward this as `entity_id` to Mergado's OAuth authorize URL

### 1.2 Backend OAuth Implementation

```python
# app/auth/oauth.py
class MergadoOAuth:
    def get_authorization_url(
        self,
        state: str = None,
        entity_id: str = None,
    ) -> str:
        params = {
            'response_type': 'code',
            'grant_type': 'authorization_code',  # REQUIRED by Mergado
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
        }
        if state:
            params['state'] = state
        if entity_id:  # CRITICAL for shop apps
            params['entity_id'] = str(entity_id)
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"{self.auth_url}?{query_string}"

@auth_bp.route("/login")
def login():
    state = request.args.get('state')
    # Mergado sends 'eshop'; OAuth API expects 'entity_id'
    entity_id = request.args.get('entity_id') or request.args.get('eshop')
    auth_url = oauth.get_authorization_url(state=state, entity_id=entity_id)
    return redirect(auth_url)
```

### 1.3 Frontend Query Param Preservation

```javascript
// app/templates/base.html - AuthManager class
startOAuth() {
    const params = new URLSearchParams(window.location.search);
    const passthrough = new URLSearchParams();
    // Preserve entity_id, eshop, entity_type, state
    ['entity_id', 'eshop', 'entity_type', 'state'].forEach(key => {
        if (params.has(key)) passthrough.set(key, params.get(key));
    });
    const query = passthrough.toString();
    const loginUrl = '/auth/login' + (query ? '?' + query : '');
    window.location.replace(loginUrl);
}
```

### 1.4 Storing Token Metadata

```python
# app/auth/oauth.py - callback route
# Mergado token response includes entity_id and user_id
tokens = oauth.exchange_code_for_tokens(code)
entity_id = tokens.get('entity_id', '')
user_id = tokens.get('user_id', '')

# Store in localStorage via JavaScript
html = f"""
<script>
    localStorage.setItem('mergado_access_token', '{tokens['access_token']}');
    localStorage.setItem('mergado_entity_id', '{entity_id}');
    localStorage.setItem('mergado_user_id', '{user_id}');
    window.location.href = '/';
</script>
"""
```

**Common Errors:**
- `error=missing_entity_id` → `entity_id` not passed to authorize URL
- **403 FORBIDDEN** on API calls → Token issued without `entity_id`

---

## Part 2: Required OAuth Scopes

Configure in Mergado developer portal **before** users authenticate:

| Scope | Required For |
|-------|--------------|
| `shop.read` | Basic shop info |
| `shop.projects.read` | **List projects** (403 without this) |
| `project.read` | Project details |
| `project.products.read` | Read products from feed |
| `project.products.write` | Update product data |
| `project.elements.read` | Check elements |
| `project.elements.write` | Create elements (writeback) |
| `project.rules.write` | Create rules |
| `project.queries.write` | Create queries |
| `project.logs.read` | Read logs |
| `shop.proxy.read` | Shopify API reads |
| `shop.proxy.write` | Shopify API writes |

**After adding scopes, users MUST re-authenticate to get a new token with updated permissions.**

---

## Part 3: Docker Deployment on Render

### 3.1 Dockerfile Port Binding

**CRITICAL:** Render sets `$PORT` env var (usually 10000). Your app MUST bind to `$PORT`, not a hardcoded port.

```dockerfile
# BAD: Hardcoded port
CMD gunicorn --bind 0.0.0.0:5000 main:app

# GOOD: Use $PORT
CMD sh -c "exec gunicorn --bind 0.0.0.0:\${PORT:-5000} main:app"
```

**Why:** Render's proxy routes external traffic to `$PORT`. If your app binds to a different port, the proxy can't reach it → "Not Found" for all requests.

### 3.2 Health Check Configuration

```python
# app/routes/main.py
@main_bp.route('/health')
def health():
    health_status = {'status': 'healthy', 'checks': {}}
    
    # DB check (non-fatal: don't fail health check over DB)
    try:
        db.session.execute(text('SELECT 1'))
        health_status['checks']['database'] = 'healthy'
    except Exception as e:
        health_status['checks']['database'] = f'degraded: {str(e)}'
    
    return health_status, 200  # ALWAYS return 200
```

**Why:** If health check returns 503, Render considers the app unhealthy and **blocks ALL external traffic** → "Not Found".

Set in Render Settings → **Health Check Path**: `/health`

### 3.3 Database Migrations

```dockerfile
# Set FLASK_APP so Flask knows where to find the app factory
ENV FLASK_APP=main:app

# Run migrations before starting app
CMD sh -c "flask db upgrade || true && exec gunicorn ..."
```

**Fallback in config.py:**
```python
def _init_database(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    from app import models  # noqa
    
    # Auto-create tables if migrations haven't run
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            if 'shops' not in inspector.get_table_names():
                app.logger.info("Tables missing, running db.create_all()")
                db.create_all()
        except Exception as e:
            app.logger.warning(f"Table check failed: {e}")
```

### 3.4 Environment Variables

| Variable | Example | Notes |
|----------|---------|-------|
| `FLASK_SECRET_KEY` | Generate with `secrets.token_hex(32)` | Not literal string! |
| `DATABASE_URL` | Auto-set by Render when linking PostgreSQL | Required |
| `MERGADO_CLIENT_ID` | From developer portal | OAuth app ID |
| `MERGADO_CLIENT_SECRET` | From developer portal | OAuth secret |
| `MERGADO_REDIRECT_URI` | `https://<your-app>.onrender.com/auth/callback` | Must match exactly |
| `PORT` | Auto-set by Render | Don't override |

---

## Part 4: Mergado Developer Portal Configuration

### 4.1 App Settings

1. **Base URL**: `https://<your-app>.onrender.com`
2. **Hook URL**: `https://<your-app>.onrender.com/webhook` (if using webhooks)
3. **Routing Type**: `GET parameters` (e.g., `/?eshop=1&project=2`)
4. **OAuth Scopes**: Add all required scopes (see Part 2)

### 4.2 Redirect URI

Must match **exactly** what's in your environment variables:
- `https://<your-app>.onrender.com/auth/callback`
- **NOT** `http://` (HTTPS only in production)
- **NOT** missing `/auth/callback` path

---

## Part 5: Troubleshooting

### Issue: "Not Found" on all requests

**Symptoms:**
- External requests return plain text "Not Found"
- Internal health checks (HEAD /) succeed
- Render logs show `x-render-routing: no-server`

**Causes & Fixes:**

1. **Port mismatch**
   - Check: Dockerfile binds to `$PORT`
   - Fix: `CMD sh -c "gunicorn --bind 0.0.0.0:\${PORT:-5000} ..."`

2. **Health check failing**
   - Check: `/health` returns 200 (not 503)
   - Fix: Make health check always return 200 (DB issues = "degraded", not failure)
   - Set Health Check Path in Render Settings

3. **App not deployed**
   - Check: Render dashboard shows "Live" (green)
   - Fix: Trigger manual deploy or check build logs for errors

### Issue: 403 FORBIDDEN on API calls

**Symptoms:**
- Auth succeeds, token stored
- API calls return 403 with specific endpoint (e.g., `/shops/123/projects/`)

**Causes & Fixes:**

1. **Missing OAuth scopes**
   - Check: Developer portal → App → Scopes
   - Fix: Add required scopes (e.g., `shop.projects.read`)
   - **Users must re-authenticate after adding scopes**

2. **Token issued without entity_id**
   - Check: localStorage has `mergado_entity_id`
   - Fix: Clear tokens, re-authenticate (flow now includes `entity_id`)

### Issue: `error=missing_entity_id` in callback

**Cause:** `entity_id` not passed to Mergado authorize URL

**Fix:**
1. Check `/auth/login` route passes `entity_id` to `get_authorization_url()`
2. Check frontend preserves `eshop` param when redirecting to `/auth/login`
3. Check Mergado sends `?eshop=<id>` when opening app (verify in browser URL)

### Issue: Database tables missing

**Symptoms:**
- `psycopg2.errors.UndefinedTable: relation "shops" does not exist`

**Causes & Fixes:**

1. **Migrations not running**
   - Check: Dockerfile has `flask db upgrade || true` before gunicorn
   - Check: `FLASK_APP=main:app` set in ENV
   - Fix: Add fallback `db.create_all()` in `_init_database()` (see Part 3.3)

2. **DATABASE_URL not set**
   - Check: Render Environment variables
   - Fix: Link PostgreSQL database or set manually

---

## Part 6: Deployment Checklist

### Before Deploy
- [ ] OAuth scopes configured in developer portal
- [ ] `entity_id` support in OAuth flow (backend + frontend)
- [ ] Health check returns 200 always
- [ ] Dockerfile binds to `$PORT`
- [ ] `FLASK_APP` set for migrations
- [ ] Database fallback in place

### After Deploy
- [ ] Health check path set in Render
- [ ] Environment variables set (secret key, DB, OAuth creds)
- [ ] Redirect URI updated (correct domain)
- [ ] Base URL updated in developer portal
- [ ] Test: Open app from Store → auth succeeds
- [ ] Test: API call (e.g., load projects) succeeds

### Post-Deploy Testing
1. Clear localStorage / Sign out
2. Open app from Mergado Store
3. Complete OAuth flow
4. Check localStorage: `mergado_entity_id` present
5. Make API call → should succeed (not 403)

---

## Summary

**Key Lessons:**
1. **Shop apps require `entity_id` in OAuth** — forward `?eshop=<id>` to authorize URL
2. **OAuth scopes must be configured** before users authenticate
3. **Docker apps on Render must bind to `$PORT`** — not hardcoded 5000
4. **Health check must return 200** — don't fail on degraded DB
5. **Re-authenticate after scope/config changes** — old tokens lack new permissions

**Common Mistake Timeline:**
1. Deploy without `entity_id` → `error=missing_entity_id`
2. Add `entity_id`, but no scopes → **403 FORBIDDEN**
3. Add scopes, but old token → **403 FORBIDDEN** (need re-auth)
4. Re-auth, but port mismatch → **"Not Found"**
5. Fix port, but health check fails → **"Not Found"**
6. Fix health, but tables missing → **500 error**
7. Add DB fallback → **Everything works! 🎉**

## References
- `/docs/OAUTH_APPROACH.md` - Detailed OAuth documentation
- `/docs/DEPLOY_MERGADO_STORE.md` - Render deployment guide
- Mergado API docs: https://mergado.github.io/docs/api/
