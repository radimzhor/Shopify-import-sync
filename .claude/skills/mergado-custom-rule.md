# Mergado Custom App Rule Skill

## Overview

A custom app rule lets Mergado call your endpoint whenever it applies rules to a project.
You receive a batch of products and return only the ones you want to modify, with new element values.
This is the correct mechanism for writing element values back to Mergado.

**When to use this pattern**: Any time you need to write computed/external values into a Mergado
element on a per-product basis (e.g., Shopify IDs, external prices, stock levels).

**Critical Success Factors** (learned from production debugging):
1. ✅ Callback URL hostname must match deployed service exactly
2. ✅ All rules (including app rules) must have at least one query
3. ✅ Query IDs are project-specific and must be looked up dynamically
4. ✅ Verify stored rule IDs still exist before reusing
5. ✅ Extract SKU dynamically from any element (names vary per project)
6. ✅ Format response values correctly (no trailing separators)

## How It Works

```
Import completes
    → upsert mappings into DB lookup table
    → ensure element exists on project (once)
    → ensure app rule exists on project (once, idempotent)

Mergado applies rules (on its own schedule)
    → POST /api/rules/<your-rule>  ← Mergado calls us
    → we bulk-query our DB for the batch of SKUs
    → return only products that have a mapping, with new element values
```

## Registering the Rule in Mergado Developers Center

1. Go to **Developers → Rules → New rule**
2. Fill in:
   - **Rule name**: human-readable label
   - **ID**: short identifier, no spaces (becomes part of `app_rule_type`)
   - **PRODUCTION URL**: `https://<your-render-app>.onrender.com/api/rules/<endpoint>`
     - ⚠️ **CRITICAL**: Hostname must match your deployed service exactly
     - If your Render service is `shopify-import-and-sync.onrender.com`, use that exact hostname
     - OAuth redirect URIs and rule callback URLs must all use the same hostname
     - Mismatch causes silent failures (Mergado calls wrong URL, your app never receives callback)
   - **DEV URL**: same URL works for both (Mergado just calls whichever you configure)
   - **API version**: today's date (e.g., `2026-03-13`) — use the latest supported format
   - **Element sending policy**: `Advanced settings` → Select the element(s) that identify products
     - Send the element that contains your product identifier (SKU, ITEM_ID, CODE, etc.)
     - This element name varies per Mergado project configuration
     - Do NOT include the element you're writing back (shopify_id) — you're the writer, not the reader
     - Your endpoint receives only the elements you select here
3. Save → note the generated `app_rule_type` values (prod and dev differ by `.dev.` infix)

### app_rule_type format

```
Production: apps.<extension-slug>.<rule-id>
Dev:        apps.<extension-slug>.dev.<rule-id>
```

The slug and ID use **no underscores** — e.g., `apps.shopifyimportsync.shopifyidwriteback`.
This must match exactly what you pass as `app_rule_type` when creating the rule on the project.

## Adding a New Custom Rule Endpoint

### 1. Create the endpoint in `app/routes/rule_routes.py`

```python
@rule_bp.route('/<your-rule-name>', methods=['POST'])
def your_rule():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({'data': []}), 200

    mergado_project_id = str(payload.get('project_id', ''))
    products = payload.get('data', [])

    project = Project.query.filter_by(mergado_project_id=mergado_project_id).first()
    if not project:
        return jsonify({'data': []}), 200

    # Bulk-query your DB for all SKUs in the batch
    skus = [_extract_sku(p) for p in products if _extract_sku(p)]
    mappings = YourMapping.query.filter(
        YourMapping.project_id == project.id,
        YourMapping.sku.in_(skus)
    ).all()
    lookup = {m.sku: m.value for m in mappings}

    result = []
    for product in products:
        sku = _extract_sku(product)
        value = lookup.get(sku)
        if not value:
            continue
        result.append({
            'id': product['id'],
            'data': {
                'elements': {
                    'your_element_name': [{'value': value}]
                }
            }
        })

    return jsonify({'data': result}), 200
```

**Key rules for rule endpoints:**
- Always return `200` (even on errors) — Mergado treats non-200 as a rule failure
- Only return products you want to modify; omitted products are left unchanged
- Do a **single bulk DB query** for all SKUs in the batch — never query per-product
- Endpoint is public (no OAuth) — Mergado calls it server-to-server

### 2. Extract SKU from product payload (DYNAMIC approach)

**Critical lesson**: Element names vary per project (ITEM_ID, CODE, SKU, etc.). 
Don't hardcode the element name — extract from whatever element Mergado sends.

Mergado's "Element sending policy" in the Developers Center determines which elements are sent.
If you configure it to send only the identifier element, your endpoint receives exactly one element per product.

**Best practice**: Extract the value from the first (or only) element sent:

```python
def _extract_sku(product: dict) -> Optional[str]:
    """
    Extract SKU dynamically from any element sent by Mergado.
    Works regardless of element name (ITEM_ID, CODE, SKU, etc.).
    """
    data = product.get('data', {})
    elements = data.get('elements', {})
    
    # Mergado sends only the configured identifier element(s)
    # Extract value from the first element available
    for element_name, element_values in elements.items():
        if element_values and isinstance(element_values, list) and len(element_values) > 0:
            value = element_values[0].get('value')
            if value:
                return str(value).strip()
    
    return None
```

**Why this works**:
- Mergado's "Element sending policy" is configured to send ONLY the identifier element
- Element names are project-specific configuration (one project uses "CODE", another uses "ITEM_ID")
- By extracting from the first available element, we handle all naming conventions
- This makes the endpoint truly project-agnostic

### 3. Add required MergadoClient methods

Your `MergadoClient` service needs these methods for rule management:

```python
def get_queries(self, project_id: str) -> dict:
    """List all queries for a project."""
    return self._request('GET', f'/projects/{project_id}/queries/')

def get_rule(self, project_id: str, rule_id: str) -> Optional[dict]:
    """
    Get a specific rule by ID.
    Returns None if rule doesn't exist (404 response).
    """
    try:
        return self._request('GET', f'/projects/{project_id}/rules/{rule_id}/')
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise
```

### 4. Add the rule type to settings

In `settings.py`:
```python
your_rule_type: str = "apps.shopifyimportsync.dev.yourruleid"
```

In `render.yaml`:
```yaml
- key: YOUR_RULE_TYPE
  value: apps.shopifyimportsync.yourruleid
```

### 5. Create the rule instance on the project (once per project)

Store the rule ID on the `Project` model so it's only created once.

**CRITICAL**: All rules (including app rules) MUST have at least one query.
Use the project's "all products" query (exists by default, but ID varies per project).

```python
def ensure_app_rule(self) -> str:
    """
    Ensure app rule exists on the Mergado project.
    Creates rule if it doesn't exist or if stored rule ID is stale.
    """
    # Verify stored rule still exists in Mergado
    if self.project.your_rule_id:
        existing_rule = self.client.get_rule(
            self.project.mergado_project_id,
            self.project.your_rule_id
        )
        if existing_rule:
            return self.project.your_rule_id
        else:
            logger.warning(
                f"Stored rule {self.project.your_rule_id} no longer exists "
                f"in Mergado project {self.project.mergado_project_id}, creating new one"
            )
            self.project.your_rule_id = None
            db.session.commit()

    # Look up the "all products" query ID (varies per project)
    all_products_query_id = self._get_all_products_query_id()
    if not all_products_query_id:
        raise ValueError(
            f"Could not find 'all products' query for project {self.project.mergado_project_id}"
        )

    # Create new rule with required query
    rule = self.client.create_rule(
        project_id=self.project.mergado_project_id,
        rule_type='app',
        element_path=None,
        data={'app_rule_type': settings.your_rule_type},
        queries=[all_products_query_id],  # REQUIRED: at least one query
        name='Your Rule Name',
        applies=True,
        priority='1',
    )
    rule_id = str(rule.get('id', ''))
    self.project.your_rule_id = rule_id
    db.session.commit()
    logger.info(
        f"Created app rule {rule_id} for project {self.project.mergado_project_id}"
    )
    return rule_id

def _get_all_products_query_id(self) -> Optional[str]:
    """
    Find the 'all products' query ID for this project.
    The query exists by default but its numeric ID varies per project.
    """
    queries = self.client.get_queries(self.project.mergado_project_id)
    
    # Look for query with "all" and "product" in name (case-insensitive)
    for query in queries.get('data', []):
        name = query.get('name', '').lower()
        if 'all' in name and 'product' in name:
            return str(query.get('id'))
    
    return None
```

**Why these safeguards matter**:
1. **Query requirement**: Mergado API returns 400 error if `queries` is empty
2. **Dynamic lookup**: "All products" query ID is project-specific (e.g., 7975344, 8012456)
3. **Existence check**: Users can delete rules in Mergado UI; stale IDs cause silent failures
4. **Idempotency**: Check-then-create pattern prevents duplicate rules

## Response Format Reference

Mergado API v2022-09-10+ response:

```json
{
  "data": [
    {
      "id": "1001",
      "data": {
        "elements": {
          "your_element_name": [{"value": "the-value"}]
        }
      }
    }
  ]
}
```

## Production Gotchas (Learned from Real Debugging Sessions)

### 🔴 CRITICAL: Hostname Consistency
**Symptom**: Rule application stuck at 0%, no callbacks received, no errors in logs.

**Root cause**: Callback URL registered in Mergado Developers Center has wrong hostname.

**Example failure**:
- Registered URL: `https://mergado-shopify-connector.onrender.com/api/rules/shopify-id-writeback`
- Actual service: `https://shopify-import-and-sync.onrender.com/api/rules/shopify-id-writeback`
- Mergado calls wrong host → your app never receives callback → silent failure

**Fix**: Verify all URLs use the same hostname:
1. OAuth redirect URIs in Mergado App Center
2. Custom rule callback URLs in Mergado Developers Center
3. Render service hostname

### 🔴 CRITICAL: Rules MUST Have Queries
**Symptom**: `400 Bad Request: {"message": "Rule must have at least one query."}`

**Root cause**: Passing `queries=[]` when creating app rule.

**Fix**: Look up the project's "all products" query ID and include it:
```python
queries = client.get_queries(project_id)
all_products_id = next(q['id'] for q in queries['data'] 
                       if 'all' in q['name'].lower() and 'product' in q['name'].lower())
# Then: queries=[all_products_id] in create_rule()
```

**Why**: Even app rules need at least one query; the "all products" query exists by default.

### 🔴 CRITICAL: Query IDs Are Project-Specific
**Symptom**: `400 Bad Request: {"message": "Query does not exist in the rule's project."}`

**Root cause**: Hardcoding a query ID from one project (e.g., `7975344`).

**Fix**: Look up the query ID dynamically for each project (see section 5 above).

**Why**: The "all products" query exists in every project, but its numeric ID varies.

### 🟡 WARNING: Verify Stored Rule IDs Still Exist
**Symptom**: Rule writeback silently skipped, no errors, but mappings exist.

**Root cause**: Rule was deleted in Mergado UI, but your DB still references the old rule ID.

**Fix**: Before reusing `project.your_rule_id`, call `get_rule()` to verify it exists:
```python
if project.your_rule_id:
    existing = client.get_rule(project_id, project.your_rule_id)
    if not existing:
        project.your_rule_id = None  # Force recreation
```

### 🟡 WARNING: Dynamic SKU Extraction
**Symptom**: "Writeback rule: found 0/X mappings" despite products in payload.

**Root cause**: Hardcoding element name (e.g., `ITEM_ID`) when project uses different name (e.g., `CODE`).

**Fix**: Extract from first available element (see section 2 above).

**Why**: Element names are project-specific configuration in Mergado.

### 🟡 WARNING: Response Value Formatting
**Symptom**: Shopify ID written as `15924628947324:` (trailing colon).

**Root cause**: String concatenation includes separator even when variant ID is None:
```python
# BAD:
return f"{product_id}:{variant_id or ''}"  # → "123:"

# GOOD:
return f"{product_id}:{variant_id}" if variant_id else product_id  # → "123"
```

**Fix**: Conditionally include separators only when needed.

### Other Important Details

- **`app_rule_type` must match exactly** — no underscores in rule ID, `.dev.` infix for dev
- **`get_project_elements` returns name-keyed dict** — `{"element_name": {"id": "42", ...}}`
- **`create_rule` for app rules** — `element_path=None`, `queries=[query_id]` (required)
- **Element sending policy** — send only identifier element (ITEM_ID/CODE/SKU), NOT the output element
- **One rule per project** — store rule ID, reuse with existence check
- **Always return 200** — Mergado treats non-200 as rule failure
- **Bulk DB queries** — single query for all SKUs in batch, never per-product queries

## Troubleshooting Checklist

When custom app rules aren't working, check these in order:

### 1. Rule Registration (Mergado Developers Center)
- [ ] Callback URL hostname matches deployed service exactly
- [ ] Callback URL path is correct (`/api/rules/<endpoint>`)
- [ ] HTTPS is used (not HTTP)
- [ ] Element sending policy is configured (sends identifier element only)
- [ ] API version is current (e.g., `2026-03-13`)

### 2. Rule Creation (Your Code)
- [ ] `app_rule_type` matches registration exactly (check `.dev.` infix)
- [ ] At least one query is included in `queries=[]` parameter
- [ ] Query ID is looked up dynamically (not hardcoded)
- [ ] Rule ID is stored on `Project` model after creation
- [ ] Existence check before reusing stored rule ID

### 3. Endpoint Implementation
- [ ] Route is registered in Flask blueprint
- [ ] Endpoint is public (no auth required)
- [ ] Returns 200 status even on errors
- [ ] Extracts SKU dynamically from any element
- [ ] Single bulk DB query for all SKUs in batch
- [ ] Returns only products with mappings
- [ ] Response format matches API version (elements dict)

### 4. Debugging Runtime Issues
Check Render logs for:
```
"Writeback rule called: project=X products=Y"  → callback received
"Writeback rule: extracted N SKUs from M products"  → SKU extraction working
"Writeback rule: ... found K mappings"  → DB lookup working
```

If callback never received:
1. Check hostname in Developers Center matches Render service name
2. Verify rule is marked as "applies=True" in Mergado
3. Check Mergado rule application UI for error messages
4. Verify project has products (rules only fire on rule application)

If SKUs not extracted (N=0):
1. Log the full product payload structure
2. Check element sending policy in Developers Center
3. Verify `_extract_sku()` iterates all elements dynamically

If mappings not found (K=0):
1. Check `ShopifyIDMapping` records exist in DB for this project
2. Verify SKU format matches between import and lookup
3. Check project_id foreign key matches
