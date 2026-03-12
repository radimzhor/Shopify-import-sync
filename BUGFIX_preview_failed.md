# Bug Fix: "Failed to generate preview: Preview failed"

## Issue Summary

The preview generation was failing with a generic "Preview failed" error. The root cause was a combination of issues:

1. **Project ID mismatch**: Frontend was sending database `id` but backend was expecting `mergado_project_id`
2. **Missing output_url**: Projects were synced from `/shops/{shop_id}/projects/` endpoint which doesn't include the feed URL
3. **Poor error messages**: Generic error message didn't help identify the actual issue

## Changes Made

### 1. Fixed Project ID Lookup (`app/routes/import_routes.py`)

**Before:**
```python
project = Project.query.filter_by(mergado_project_id=project_id).first()
```

**After:**
```python
# Try database ID first, then fall back to Mergado project ID
try:
    project = Project.query.get(int(project_id))
except (ValueError, TypeError):
    project = None

if not project:
    project = Project.query.filter_by(mergado_project_id=str(project_id)).first()
```

**Rationale:** Frontend stores and sends database ID, so we should accept both types.

### 2. Fetch Full Project Details (`app/routes/project_routes.py`)

**Before:**
```python
projects = mergado_client.get_projects(shop_id)
# Used api_project.get('output_url') which was None
```

**After:**
```python
projects = mergado_client.get_projects(shop_id)
# Fetch full details for each project
for api_project in projects:
    project_id = str(api_project['id'])
    project_details = mergado_client.get_project(project_id)
    # Use project_details.get('url') which contains the feed URL
```

**Rationale:** The list endpoint doesn't include `output_url`, but the individual project endpoint at `/projects/{id}/` includes the `url` field with the feed URL.

### 3. Improved Error Messages (`app/routes/import_routes.py`)

Added detailed logging and contextual error messages:
- Download errors → "Failed to download product feed. Please check if the project output is configured..."
- Parse errors → "Failed to parse CSV feed. Please check if the project is configured for Shopify CSV output..."
- Shopify errors → "Failed to connect to Shopify. Please check if Shopify is connected in your Mergado Keychain..."

## Testing Steps

1. **Login to the application** with your Mergado account
2. **Go to Projects page** and enter your Shop ID
3. **Click "Load Projects"** - this should now fetch full project details including output URLs
4. **Select a project** with a Shopify CSV output configured
5. **Go to Import page** and click "Generate Preview"
6. **Verify preview shows** correct counts for products to create/update/skip

## Deployment Instructions

### Local Development

```bash
# No database migration needed for this fix
python main.py
```

### Docker

```bash
docker-compose down
docker-compose build web
docker-compose up -d
```

### Render.com (Production)

The changes will be automatically deployed when pushed to the main branch. To manually trigger:

1. Go to Render dashboard: https://dashboard.render.com/
2. Select `mergado-shopify-connector` service
3. Click "Manual Deploy" → "Deploy latest commit"

Monitor the logs during deployment:
```bash
# Look for successful project syncing logs:
# "Fetched project {id} details: {url}"
# "Generated preview: X create, Y update, Z skip"
```

## Potential Issues to Monitor

### 1. Output URL Still Missing

**Symptom:** Error "Project is missing output URL. Please reload the project list."

**Cause:** Project in Mergado doesn't have output configured

**Solution:**
1. Go to Mergado project settings
2. Configure Shopify CSV output
3. Reload the projects list in the app

### 2. CSV Download Timeout

**Symptom:** Error "Failed to download product feed"

**Cause:** Large CSV file takes longer than 5 minutes (timeout)

**Solution:** Increase timeout in `csv_downloader.py`:
```python
self.timeout = 600  # 10 minutes
```

### 3. Shopify Connection Error

**Symptom:** Error "Failed to connect to Shopify"

**Cause:** Shopify not connected in Mergado Keychain

**Solution:**
1. Go to Mergado → Keychain
2. Connect your Shopify store
3. Ensure connection is active

## Additional Debugging

If issues persist, check the application logs for detailed error traces:

**Render.com:**
- Dashboard → Service → Logs
- Look for lines with `ERROR` or `Preview failed`

**Docker:**
```bash
docker logs shopify_connector_web -f
```

**Local:**
```bash
# Logs are printed to stdout
# Check for detailed traceback
```

## Related Files

- `app/routes/import_routes.py` - Preview endpoint
- `app/routes/project_routes.py` - Project sync endpoint
- `app/services/mergado_client.py` - Mergado API client
- `app/services/csv_downloader.py` - CSV download logic
- `app/templates/projects.html` - Frontend project selection
- `app/templates/import_wizard.html` - Frontend preview UI

## Follow-up Tasks

- [ ] Add integration test for preview endpoint
- [ ] Add UI feedback when project output_url is missing
- [ ] Consider caching project details to reduce API calls
- [ ] Add progress indicator for large CSV downloads

---

**Fixed Date:** 2026-03-12
**Fixed By:** Cursor AI Assistant
**Tested:** Pending user verification
