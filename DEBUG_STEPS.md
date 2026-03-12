# Debug: 0 Products in Preview

## Current Status
✅ Preview endpoint works (no error)
❌ Shows 0 products to create/update/skip

## Debugging Steps

### 1. Check Render.com Logs (MOST IMPORTANT)

1. Go to https://dashboard.render.com/
2. Click on `mergado-shopify-connector` service
3. Click on "Logs" tab
4. Look for the most recent logs when you clicked "Generate Preview"

**What to look for:**
```
INFO - Generating preview for project {id}
INFO - Downloaded CSV from {url} to {path}
INFO - Parsed X products from CSV       ← THIS NUMBER IS KEY
INFO - Fetched X Shopify products, mapped X SKUs
INFO - Generated preview: X create, Y update, Z skip
```

### 2. Possible Issues Based on Logs

#### Issue A: "Parsed 0 products from CSV"
**Problem:** CSV is empty or has wrong format

**Check:**
1. Go to Mergado project settings
2. Look at the output feed URL
3. Download it manually and check if it has products
4. Verify columns match Shopify CSV format:
   - `Handle` (required)
   - `Title` (required)
   - `Variant SKU` (required)
   - `Variant Price`
   - `Status`

#### Issue B: "Parsed X products" but preview shows 0
**Problem:** Products don't have required fields or are being filtered out

**Causes:**
- Missing SKUs in variants
- Missing Handle
- All products marked as "skip" due to validation

#### Issue C: Error during CSV download
**Problem:** Can't download the feed

**Causes:**
- Feed URL is incorrect
- Feed URL requires authentication
- Feed is not yet generated

### 3. Quick Manual Test

Test the feed URL manually:

```bash
# Replace with your actual project's output URL
curl -I "https://feed.mergado.com/your-feed-url.csv"
```

Should return:
- `200 OK` status
- `Content-Type: text/csv` or similar

### 4. Check CSV Format

Download a sample and verify:

```csv
Handle,Title,Body (HTML),Vendor,Type,Tags,Published,Status,Variant SKU,Variant Price,Variant Inventory Qty
test-product,Test Product,Description,YourBrand,Clothing,tag1,TRUE,active,SKU-001,29.99,10
```

**Required columns:**
- Handle (not empty)
- Title (not empty)
- Variant SKU (not empty)
- Status (should be "active" or "draft")

### 5. Enable Debug Logging (If needed)

If logs don't show enough info, we can add more detailed logging.

### 6. Test with Sample CSV

Create a minimal test CSV and upload to a public URL to test the parser.
