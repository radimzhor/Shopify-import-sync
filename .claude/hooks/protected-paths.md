# Protected Paths Hook

## Paths That Require Extra Care

⚠️ **Think twice before editing these directories:**

### app/auth/ - Authentication & Security
- **Risk**: OAuth vulnerabilities, token leaks, CSRF attacks
- **Before editing**:
  - Read `app/auth/CLAUDE.md` for gotchas
  - Ensure OAuth state validation is maintained
  - Never log tokens or secrets
  - Test OAuth flow thoroughly after changes

### migrations/ - Database Migrations
- **Risk**: Data loss, production downtime, irreversible changes
- **Before editing**:
  - Read `.claude/skills/database-migration.md`
  - NEVER manually edit migration files (use `flask db migrate`)
  - Test migration locally before production
  - Ensure downgrade path exists
  - Back up production database

### config.py, settings.py - Application Configuration
- **Risk**: Breaking the app, exposing secrets, misconfigured services
- **Before editing**:
  - Understand impact on all environments (dev, prod)
  - Never hardcode secrets (use environment variables)
  - Test with both development and production settings
  - Update `.env.example` if adding new settings

### Dockerfile, render.yaml - Deployment Configs
- **Risk**: Deployment failures, service outages
- **Before editing**:
  - Read `.claude/skills/deployment.md`
  - Test Docker build locally: `docker build -t test .`
  - Verify health check still works
  - Consider impact on running instances

### requirements.txt - Dependencies
- **Risk**: Version conflicts, breaking changes, security vulnerabilities
- **Before editing**:
  - Pin specific versions (e.g., `Flask==2.3.3`)
  - Test locally after changes: `pip install -r requirements.txt`
  - Check for security issues: `pip-audit` or `safety check`
  - Update CI/CD if needed

## Approval Required For

These changes should be reviewed by another developer or require explicit user approval:

- [ ] Changes to OAuth flow (`app/auth/oauth.py`)
- [ ] New database migrations (`migrations/versions/`)
- [ ] Deployment configuration changes
- [ ] Adding/upgrading major dependencies
- [ ] Changes to error handling middleware
- [ ] Modifications to logging (could expose sensitive data)

## Warning Signs

🚨 **Stop and reconsider if you're about to:**

- Drop a database table or column
- Change OAuth redirect URI or scopes
- Modify token storage or validation
- Add a dependency with <1000 GitHub stars
- Change database connection string format
- Disable security middleware
- Expose internal IDs in API responses
- Remove error handling
- Add `git add -f` to bypass .gitignore

## Safe Zones

✅ **These are generally safe to edit freely:**

- `app/routes/` - API endpoints (but test thoroughly)
- `app/services/` - Business logic (but maintain error handling)
- `app/templates/` - UI templates (but don't break layouts)
- `tests/` - Tests (always good to add more!)
- `docs/` - Documentation (keep it updated!)
- `.claude/` - These guides (improve as you learn)

## Recovery Procedures

**If you broke something in a protected path:**

### OAuth is broken
1. Check Mergado Dev Portal settings
2. Verify redirect URI in settings.py
3. Check OAuth state validation in callback
4. Test with `curl` to isolate issue

### Migration failed
1. `flask db downgrade` to rollback
2. Fix the issue in model code
3. Delete failed migration file
4. Generate new migration: `flask db migrate`

### Docker won't build
1. Check Dockerfile syntax
2. Test base image: `docker pull python:3.11-slim`
3. Build step-by-step to isolate issue
4. Revert to last working commit if stuck

### App won't start
1. Check logs for stack trace
2. Verify all environment variables set
3. Test database connection
4. Roll back to last working deploy

## Prevention

- **Before editing protected paths**: Read the relevant CLAUDE.md
- **After editing protected paths**: Run full test suite
- **Before committing**: Double-check changes to protected files
- **Before deploying**: Test locally with production-like config
