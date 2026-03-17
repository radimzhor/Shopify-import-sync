# Debug Stock/Price Sync Issues

## When to Use This Skill

Use when:
- Stock or price syncs return "0 synced, 0 failed"
- Automatic syncs aren't triggering
- Products are being skipped during sync
- Inventory tracking errors appear
- Variant matching fails

## Quick Diagnosis Checklist

```bash
# 1. Check if products are being fetched
# Look for: "Fetched X products from Mergado"

# 2. Check if products have mappings
# Products without ShopifyIDMapping entries will be skipped

# 3. Check if inventory tracking is enabled
# Error: "Inventory item does not have inventory tracking enabled"

# 4. Check if scheduler is running (for automatic syncs)
# Look for: "Background sync scheduler initialized"
```

## Common Issues & Solutions

### Issue 1: All Products Skipped (0 synced, 0 failed)

**Symptoms:**
- Logs show "Fetched X products from Mergado"
- But "Stock sync completed: 0 synced, 0 failed"
- No error messages

**Root Causes:**

#### A) Wrong Element Names
```python
# ❌ BAD - Mergado internal element names
SKU_ELEMENT = 'ITEM_ID'
STOCK_ELEMENT = 'STOCK_AMOUNT'

# ✅ GOOD - Shopify CSV output feed names
SKU_ELEMENT = 'Variant SKU'
STOCK_ELEMENT = 'Variant Inventory Qty'
INVENTORY_TRACKER_ELEMENT = 'Variant Inventory Tracker'
```

**Fix:** Use Shopify CSV column names, not internal Mergado element names.

#### B) Wrong Data Structure
```python
# ❌ BAD - Mergado API doesn't return 'values' key
sku = product.get('values', {}).get('Variant SKU')

# ✅ GOOD - Use 'data' key
sku = product.get('data', {}).get('Variant SKU')
```

**Fix:** Mergado API returns product data under `product['data']`, not `product['values']`.

#### C) No ShopifyIDMapping Records
Products must be imported first to create mapping records. Check:
```python
mapping = ShopifyIDMapping.query.filter_by(
    project_id=project.id,
    sku=sku
).first()

if not mapping:
    # Product not imported yet - skip
    continue
```

**Fix:** Import products first, or check why mappings weren't created during import.

### Issue 2: Variant Not Found

**Symptoms:**
- Warning: "Variant not found for SKU X in product Y"
- items_failed > 0

**Root Causes:**

#### A) Simple Products with Null variant_id
For simple products (non-variant), the mapping may have `shopify_variant_id = NULL`.

**Solution:** Implement fallback matching logic:
```python
# 1. Try matching by variant_id (multi-variant products)
if shopify_variant_id:
    for v in variants:
        if str(v.get('id')) == str(shopify_variant_id):
            variant = v
            break

# 2. Fall back to matching by SKU (simple products with SKU)
if not variant:
    for v in variants:
        if v.get('sku') == sku:
            variant = v
            break

# 3. If only 1 variant exists, use it (simple products)
if not variant and len(variants) == 1:
    variant = variants[0]
```

### Issue 3: Inventory Tracking Not Enabled

**Symptoms:**
- Error: `"Inventory item does not have inventory tracking enabled"`
- All syncs fail with 422 error

**Root Cause:** Variants were imported without `inventory_management = 'shopify'`.

**Solution A - Import Fix (Preventive):**
```python
# In product_importer.py
variant_data['inventory_management'] = csv_variant.inventory_tracker or 'shopify'
variant_data['inventory_policy'] = csv_variant.inventory_policy or 'deny'
```

**Solution B - Sync Auto-Fix (Reactive):**
```python
try:
    self.shopify.update_inventory_level(...)
except APIError as e:
    if 'inventory tracking enabled' in str(e).lower():
        # Enable tracking and retry
        self.shopify.update_variant(
            variant_id=str(variant.get('id')),
            variant_data={
                'variant': {
                    'id': variant.get('id'),
                    'inventory_management': inventory_tracker,  # From Mergado feed
                    'inventory_policy': 'deny'
                }
            }
        )
        # Retry the inventory update
        self.shopify.update_inventory_level(...)
```

### Issue 4: Automatic Syncs Not Triggering

**Symptoms:**
- Manual "Run now" works fine
- But automatic syncs don't execute
- Scheduler never triggers

**Root Causes:**

#### A) Scheduler Not Implemented
Check if APScheduler is installed and initialized:
```python
# In config.py
from app.services.scheduler import sync_scheduler

def _init_scheduler(app: Flask) -> None:
    sync_scheduler.init_app(app)
    sync_scheduler.start()
    app.logger.info("Background sync scheduler initialized")
    
    import atexit
    atexit.register(lambda: sync_scheduler.shutdown())
```

#### B) No OAuth Tokens in Database
Scheduler needs OAuth tokens to run syncs in background:

```python
# In app/auth/oauth.py callback
if entity_id:
    shop = Shop.query.filter_by(mergado_shop_id=entity_id).first()
    if shop:
        shop.access_token = tokens['access_token']
        shop.refresh_token = tokens.get('refresh_token', '')
        shop.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        db.session.commit()
```

**Fix:** 
1. Add OAuth token columns to Shop model
2. Run migration to add columns
3. Re-authenticate to populate tokens

#### C) Scheduler Logic Error
Check scheduler executes syncs:
```python
def _is_sync_due(self, config: SyncConfig) -> bool:
    if config.last_sync_at is None:
        return True
    
    next_sync_at = config.last_sync_at + timedelta(minutes=config.interval_minutes)
    return datetime.utcnow() >= next_sync_at
```

## Debug Workflow

### Step 1: Add Debug Instrumentation

```python
# In stock_sync.py, add temporary logging:

# After fetching products
logger.info(f"Fetched {len(products)} products from Mergado")

# In the loop (first 3 products only)
if debug_counter <= 3:
    product_data = product.get('data', {})
    logger.info(f"Product {debug_counter}: keys={list(product_data.keys())[:10]}")
    logger.info(f"  SKU={sku}, Stock={stock}, shopify_id={shopify_id}")

# Track skips
if not mapping:
    logger.debug(f"SKIPPED: No mapping for SKU {sku}")
    continue
```

### Step 2: Run Sync and Collect Evidence

```bash
# Trigger manual sync and capture logs
# Look for patterns:
# - Are products being fetched?
# - What keys are in product data?
# - Why are products being skipped?
```

### Step 3: Fix Based on Evidence

**If products have wrong keys:**
→ Fix element names to match Shopify CSV format

**If SKUs/IDs are None:**
→ Fix data structure (use 'data' not 'values')

**If no mappings found:**
→ Check import process, ensure mappings are created

**If variants not found:**
→ Add fallback matching logic

**If inventory tracking disabled:**
→ Add auto-enable logic

### Step 4: Remove Debug Code

After confirming fixes work, remove all debug logging.

## Database Migrations (Manual via API)

For production environments where direct DB access isn't available:

### Add OAuth Token Columns to Shop Table

```bash
# 1. Check current state
curl https://your-app.onrender.com/admin/db-status

# 2. Add columns
curl -X POST https://your-app.onrender.com/admin/add-shop-oauth-tokens

# 3. Verify
curl https://your-app.onrender.com/admin/db-status
# Should show: "has_oauth_tokens": true
```

### Endpoint Implementation

```python
@admin_bp.route('/add-shop-oauth-tokens', methods=['POST'])
def add_shop_oauth_tokens():
    from sqlalchemy import text
    
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE shops ADD COLUMN IF NOT EXISTS access_token TEXT"))
        conn.execute(text("ALTER TABLE shops ADD COLUMN IF NOT EXISTS refresh_token TEXT"))
        conn.execute(text("ALTER TABLE shops ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMP"))
        conn.execute(text("UPDATE alembic_version SET version_num = 'shop_oauth_v1'"))
        conn.commit()
    
    return jsonify({'status': 'success', 'message': 'OAuth token columns added'})
```

## Key Learnings

### 1. Element Names Matter
Always use the **Shopify CSV output feed** column names when fetching from Mergado:
- `Variant SKU` (not `ITEM_ID`)
- `Variant Inventory Qty` (not `STOCK_AMOUNT`)
- `Variant Inventory Tracker` (not `inventory_tracker`)

### 2. Data Structure is Key
Mergado API returns: `product['data'][element_name]`, not `product['values']`.

### 3. Mappings are Required
Products must have `ShopifyIDMapping` records to sync. Created during import.

### 4. Use Database Mappings Over Elements
Database mappings are more reliable than waiting for Mergado's `shopify_id` element to populate via batch_rewriting rules.

### 5. Simple Product Handling
Shopify treats all products as having variants (even simple products). Handle:
- Match by variant_id when available
- Fall back to SKU matching
- Use single variant for simple products

### 6. Inventory Tracking Auto-Enable
Variants need `inventory_management = 'shopify'` to update stock. Auto-enable it during sync if disabled.

### 7. Background Scheduler Needs Tokens
Store OAuth tokens in Shop model so scheduler can execute syncs without user session.

## Architecture Patterns

### Sync Service Pattern
```python
class StockSyncService:
    def __init__(self, mergado_client, shopify_service, sync_config):
        self.mergado = mergado_client
        self.shopify = shopify_service
        self.sync_config = sync_config
    
    def sync_stock(self):
        # 1. Fetch products from Mergado (source of truth)
        products = self.mergado.get_project_products(...)
        
        # 2. For each product:
        for product in products:
            # - Extract SKU and stock quantity
            # - Look up Shopify IDs in database
            # - Fetch product from Shopify to get inventory_item_id
            # - Update inventory level
            # - Mark mapping as synced
        
        # 3. Log results
        return {'items_synced': X, 'items_failed': Y}
```

### Scheduler Pattern
```python
class SyncScheduler:
    def _check_and_run_due_syncs(self):
        # Runs every minute
        configs = SyncConfig.query.filter_by(enabled=True).all()
        
        for config in configs:
            if self._is_sync_due(config):
                # Execute sync in background using stored OAuth tokens
                self._execute_sync(config)
    
    def _is_sync_due(self, config):
        next_sync = config.last_sync_at + timedelta(minutes=config.interval_minutes)
        return datetime.utcnow() >= next_sync
```

## Testing Checklist

### Manual Sync
- [ ] Create import (at least 1 product)
- [ ] Verify ShopifyIDMapping records exist
- [ ] Click "Run now" for stock sync
- [ ] Verify > 0 synced products
- [ ] Check Shopify admin - stock levels updated

### Automatic Sync
- [ ] Enable automatic sync
- [ ] Set interval (e.g., 5 minutes)
- [ ] Re-authenticate (populate OAuth tokens)
- [ ] Wait for next scheduled run
- [ ] Check logs: "Scheduled stock sync completed"
- [ ] Verify sync logs table shows automatic runs

### Edge Cases
- [ ] Simple products (no variants) - should sync
- [ ] Multi-variant products - should sync correct variant
- [ ] Products with inventory tracking disabled - should auto-enable
- [ ] Products deleted in Shopify - should delete stale mapping
- [ ] Invalid stock values - should skip with warning

## References

- Mergado API: https://api-docs.mergado.com/
- Shopify Admin API: https://shopify.dev/docs/api/admin-rest
- APScheduler Docs: https://apscheduler.readthedocs.io/
- Related: `app/services/CLAUDE.md` - Service patterns
- Related: `docs/adr/001-batch-rewriting-for-shopify-ids.md` - ID mapping approach

---

**Last Updated:** 2026-03-17
**Tested On:** Render.com deployment with 375 Mergado products, 12 imported to Shopify
