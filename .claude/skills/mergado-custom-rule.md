# Mergado Custom App Rule Skill

## Overview

A custom app rule lets Mergado call your endpoint whenever it applies rules to a project.
You receive a batch of products and return only the ones you want to modify, with new element values.
This is the correct mechanism for writing element values back to Mergado.

**When to use this pattern**: Any time you need to write computed/external values into a Mergado
element on a per-product basis (e.g., Shopify IDs, external prices, stock levels).

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
   - **DEV URL**: same URL works for both (Mergado just calls whichever you configure)
   - **API version**: today's date (e.g., `2026-03-13`) — use the latest supported format
   - **Element sending policy**: `Advanced settings` → Mergado XML equivalent → `ITEM_ID` only
     - Only send elements your endpoint actually reads (ITEM_ID for SKU lookup)
     - Do NOT include the element you're writing back (shopify_id) — you're the writer, not the reader
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

### 2. Extract SKU from product payload

Mergado sends products in two formats depending on API version:

```python
def _extract_sku(product: dict) -> Optional[str]:
    data = product.get('data', {})
    # New format (>= 2022-09-10): nested elements dict
    elements = data.get('elements')
    if elements:
        item_id_list = elements.get('ITEM_ID', [])
        if item_id_list and isinstance(item_id_list, list):
            return item_id_list[0].get('value')
    # Old flat format
    return data.get('ITEM_ID') or None
```

### 3. Add the rule type to settings

In `settings.py`:
```python
your_rule_type: str = "apps.shopifyimportsync.dev.yourruleid"
```

In `render.yaml`:
```yaml
- key: YOUR_RULE_TYPE
  value: apps.shopifyimportsync.yourruleid
```

### 4. Create the rule instance on the project (once per project)

Store the rule ID on the `Project` model so it's only created once:

```python
def ensure_app_rule(self) -> str:
    if self.project.your_rule_id:
        return self.project.your_rule_id

    rule = self.client.create_rule(
        project_id=self.project.mergado_project_id,
        rule_type='app',
        element_path=None,   # app rules have no element_path
        data={'app_rule_type': settings.your_rule_type},
        queries=[],          # app rules have no queries
        name='Your Rule Name',
        applies=True,
        priority='1',
    )
    rule_id = str(rule.get('id', ''))
    self.project.your_rule_id = rule_id
    db.session.commit()
    return rule_id
```

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

## Gotchas

- **`app_rule_type` must match exactly** what is registered in Developers Center — no underscores in the rule ID part, `.dev.` infix for dev environment
- **`get_project_elements` returns a name-keyed dict** — `{"element_name": {"id": "42", ...}}`, not a `{data: [...]}` envelope
- **`create_rule` for app rules** — omit `element_path` and `queries` entirely (pass `None`/`[]`, the client conditionally excludes them)
- **Element sending policy** — set to `Advanced settings → ITEM_ID` only; do not include the element you are writing (you don't need to read your own output)
- **One rule per project** — store the Mergado rule ID on the `Project` model and reuse it; duplicate rules cause double-writes
