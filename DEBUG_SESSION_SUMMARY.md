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

## Session 2: Shopify ID Writeback Rule Creation Issues

**Date**: March 14, 2026  
**Issue**: Shopify ID writeback failing with Mergado API errors  
**Status**: ✅ RESOLVED

### Problem

After fixing the database schema issues, the writeback operation reached the rule creation step but failed with Mergado API errors:
1. First: `400 BAD REQUEST` with no details
2. After adding logging: `"Rule must have at least one query"`
3. After adding `♥ALLPRODUCTS♥` query: `"Query does not exist in the rule's project"`

### Root Causes

1. **Missing query in rule**: Mergado API requires every rule to have at least one query attached, but we were passing `queries=[]`
2. **Wrong query ID approach**: The `♥ALLPRODUCTS♥` identifier is not universal - each project has its own numeric ID for the "all products" query

### Hypothesis Testing (with Runtime Evidence)

#### H1: Insufficient error details from Mergado API ✅ CONFIRMED
- **Evidence**: Initial logs showed generic "BAD REQUEST" without Mergado's actual error message
- **Fix**: Enhanced error logging to include full API response body
- **Result**: Could see actual error: `"Rule must have at least one query"`

#### H2: Rule needs at least one query ✅ CONFIRMED  
- **Evidence**: Mergado API returned `{"message": "Rule must have at least one query."}`
- **Initial attempt**: Used `♥ALLPRODUCTS♥` as universal query ID
- **Result**: Failed with `"Query does not exist in the rule's project"`

#### H3: All-products query ID varies per project ✅ CONFIRMED
- **Evidence**: User confirmed the all-products query exists in every project but with different numeric IDs (e.g., `7975344`)
- **Fix**: Added `get_queries()` method to list project queries and find the all-products query dynamically
- **Result**: Successfully creates rules using the correct project-specific query ID

### Solution Applied

**Step 1: Add query listing to MergadoClient**
```python
def get_queries(self, project_id: str) -> List[Dict[str, Any]]:
    """List all queries in a project."""
    response = self._request('GET', f'/projects/{project_id}/queries/')
    # Handle both {data: [...]} and [...] response formats
    ...
```

**Step 2: Look up all-products query before creating rule**
```python
# Find the "all products" query (exists in every project by default)
queries = self.client.get_queries(self.project.mergado_project_id)
all_products_query_id = None

for query in queries:
    query_name = query.get('name', '').lower()
    if 'all' in query_name and 'product' in query_name:
        all_products_query_id = str(query.get('id'))
        break

# Create rule with the project-specific query ID
rule = self.client.create_rule(
    project_id=self.project.mergado_project_id,
    rule_type='app',
    data={'app_rule_type': settings.mergado_writeback_rule_type},
    queries=[{'id': all_products_query_id}],  # ✅ Uses correct project-specific ID
    ...
)
```

**Step 3: Enhanced error logging**
- Changed error logging to include full Mergado API response body
- Made rule payload logging debug-level (was too verbose for production)

### Verification

**Before fix**:
```json
{"message": "Query does not exist in the rule's project."}
```

**After fix**:
- Log shows: `"Found all-products query: 7975344"` (or similar per-project ID)
- Rule creation succeeds
- Shopify ID writeback completes successfully

### Files Modified

- `app/services/mergado_client.py` - Added `get_queries()` method, enhanced error logging
- `app/services/shopify_id_writeback.py` - Dynamic query lookup before rule creation
- `app/routes/admin_routes.py` - Added `/admin/create-shopify-id-mappings-table` endpoint (from Session 1 continuation)

### Lessons Learned

1. **Always log full API error responses**: Generic HTTP status codes aren't enough; the response body contains the actual error
2. **Don't assume universal IDs**: Even "standard" entities like "all products" queries have project-specific IDs
3. **Query the API for dynamic data**: When IDs vary per project, look them up rather than hardcoding
4. **Use debug-level for verbose logging**: Detailed payloads are useful for debugging but too verbose for production INFO logs

---

**Total resolution time**: ~6 hours (across two sessions, including DB schema fixes and OAuth setup)
