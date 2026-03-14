# Debug Session Summary - Load Project 500 Error

**Date**: March 13-14, 2026  
**Issue**: HTTP 500 error when clicking "Load project" button  
**Status**: ✅ RESOLVED

## Problem

When users clicked "Load project" in the UI, the backend returned a 500 error:

```
psycopg2.errors.UndefinedColumn: column projects.shopify_writeback_rule_id does not exist
```

The SQLAlchemy ORM was trying to SELECT a column that didn't exist in the Render Postgres database.

## Root Cause

The `projects` table on Render was missing the `shopify_writeback_rule_id` column because:

1. The Alembic migration that should have added it (`a3f1c9d2e8b4`) existed in the code
2. BUT the migration had never been applied to the production database
3. The initial `render.yaml` config didn't include a `releaseCommand` to run migrations on deploy
4. The `start.sh` script ran migrations but used `|| echo "Migration failed..."`, which swallowed errors and allowed the app to start with an outdated schema

## Hypothesis Testing (with Runtime Evidence)

### H1: Schema mismatch - column missing from DB ✅ CONFIRMED
- **Evidence**: Render logs showed exact error: `column projects.shopify_writeback_rule_id does not exist`
- **Evidence**: Successful OAuth and API calls to Mergado proved the token was valid
- **Evidence**: Logs showed project data being fetched successfully, then failing at DB query stage

### H2: Alembic migration state drift ✅ CONFIRMED
- **Evidence**: Even after adding `releaseCommand` and redeploying, the column was still missing
- **Evidence**: Manual column addition via `/admin/add-column-directly` succeeded immediately
- **Conclusion**: Alembic's revision tracking had drifted from actual schema

## Solution Applied

### Step 1: Configure automatic migrations on deploy
**Files changed**:
- `render.yaml` - Added `releaseCommand: "export FLASK_APP=main.py && flask db upgrade"`
- `start.sh` - Removed `|| echo "Migration failed..."` so migration failures now stop the app from starting

**Rationale**: Ensures migrations run during every Render deploy, and deploy fails if migrations fail.

### Step 2: Add idempotent migration
**File created**: `migrations/versions/b9e3e1e52c34_ensure_shopify_writeback_rule_id_column.py`

Uses `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` so it can safely run even if the column already exists.

### Step 3: Emergency column addition (applied in production)
**Method**: Called `POST /admin/add-column-directly` endpoint

Directly executed:
```sql
ALTER TABLE projects 
ADD COLUMN IF NOT EXISTS shopify_writeback_rule_id VARCHAR(50);
```

This bypassed Alembic and fixed the production issue immediately.

### Step 4: Admin tooling for future debugging
**File created**: `app/routes/admin_routes.py`

Added three endpoints:
- `GET /admin/db-status` - Check Alembic state, column existence
- `POST /admin/run-migrations` - Manually trigger migrations
- `POST /admin/add-column-directly` - Emergency schema fix

**Note**: These are permanent debugging tools, not temporary instrumentation.

## Verification

**Before fix**:
```json
{
  "timestamp": "2026-03-13 20:58:20",
  "level": "ERROR",
  "message": "Failed to fetch projects: (psycopg2.errors.UndefinedColumn) column projects.shopify_writeback_rule_id does not exist"
}
```

**After fix**:
- `POST /admin/add-column-directly` returned: `{"status":"success","message":"Column added successfully"}`
- "Load project" button worked successfully
- No more `UndefinedColumn` errors in logs

## Lessons Learned

1. **Always run migrations on deploy**: Use `releaseCommand` in `render.yaml` for Render deployments
2. **Fail fast on migration errors**: Don't swallow migration failures with `|| echo`
3. **Idempotent migrations are safer**: Use `IF NOT EXISTS` / `IF EXISTS` when possible
4. **Keep admin tooling**: The `/admin/` routes proved essential for diagnosing and fixing the issue without shell access

## Files Modified

### Production fixes (deployed):
- `render.yaml` - Added release command
- `start.sh` - Removed error swallowing
- `migrations/versions/b9e3e1e52c34_ensure_shopify_writeback_rule_id_column.py` - Idempotent migration
- `app/routes/admin_routes.py` - Admin debugging endpoints (new file)
- `config.py` - Registered admin blueprint

### Temporary debug instrumentation (already cleaned up):
- None remaining - debug logs in `app/routes/project_routes.py` were removed after initial diagnosis

## Current State

✅ Production database schema is correct  
✅ Future deploys will run migrations automatically  
✅ Admin tools available for future issues  
✅ No temporary debug code remaining in codebase  

---

**Resolution time**: ~4 hours (including multiple deploy cycles and OAuth troubleshooting)
