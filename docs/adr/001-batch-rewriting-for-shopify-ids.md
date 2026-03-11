# ADR-001: Batch Rewriting Rule for Shopify ID Writeback

## Status
**Accepted** - 2026-03-04

## Context
After importing products from Mergado to Shopify, we need to write the Shopify product and variant IDs back to the Mergado project so that future sync operations (stock, price) can map between the two systems.

Mergado's API doesn't provide a direct endpoint to write element values to individual products. The only way to modify product data programmatically is through Mergado's rule system.

### Available Rule Types
- **`rewriting`**: Rewrites an element with a fixed value for all products matching a query (1:1 relationship)
- **`batch_rewriting`**: Rewrites an element with different values based on multiple queries (1:N relationship)
- **`replacing`**: Find-and-replace within element values
- **Custom app rules**: External service processes products and returns modifications

## Decision
We will use the **`batch_rewriting`** rule type to write Shopify IDs back to Mergado.

### Implementation Approach
1. Create a hidden element `shopify_id` in the Mergado project
2. For each imported product, create a query targeting it by SKU: `ITEM_ID = 'SKU123'`
3. Create a single `batch_rewriting` rule with:
   - `element_path`: `"shopify_id"`
   - `data`: Array of `{position, query_id, value: "shopify_product_id:shopify_variant_id"}` entries
   - One entry per SKU mapping
4. Marking the project as `is_dirty` triggers rule application
5. Poll `/projects/{id}/applylogs/` to confirm completion

### Example API Call
```json
POST /projects/{project_id}/rules/
{
  "name": "Shopify ID Writeback",
  "type": "batch_rewriting",
  "element_path": "shopify_id",
  "applies": true,
  "priority": "1",
  "data": [
    {"position": 1, "query_id": "query1", "value": "12345:67890"},
    {"position": 2, "query_id": "query2", "value": "12346:67891"},
    ...
  ],
  "queries": [
    {"id": "query1"},
    {"id": "query2"},
    ...
  ]
}
```

Where each query targets a specific SKU:
```json
POST /projects/{project_id}/queries/
{
  "query": "ITEM_ID = 'SKU123'",
  "name": "Shopify ID target: SKU123"
}
```

## Alternatives Considered

### 1. Individual `rewriting` Rules Per Product
**Approach**: Create one `rewriting` rule per product, each with its own query.

**Pros**:
- Simpler rule structure
- Easy to update individual products

**Cons**:
- Creates hundreds/thousands of rules for large catalogs
- Clutters Mergado UI for users
- Slower to create (one API call per rule)
- Rule priority management becomes complex
- **Rejected**: Not scalable

### 2. Custom App Rule
**Approach**: Create a custom rule that receives product data, processes it externally, and returns Shopify IDs.

**Pros**:
- Full control over processing logic
- Can handle complex mappings

**Cons**:
- Requires running a separate service to process rule applications
- More infrastructure to maintain
- Mergado would call our endpoint every time rules are applied
- Adds latency to product updates
- **Rejected**: Over-engineered for this use case

### 3. No Writeback (Store Mapping in Our Database Only)
**Approach**: Store SKU → Shopify ID mapping only in our PostgreSQL database, not in Mergado.

**Pros**:
- Simpler implementation
- No rule management needed

**Cons**:
- Creates a "source of truth" problem
- If our database is lost, mappings are gone
- Users can't see Shopify IDs in Mergado UI/exports
- Other Mergado extensions can't access the mapping
- **Rejected**: Doesn't align with Mergado's data model philosophy

## Consequences

### Positive
- **Scalable**: Single rule handles any number of products
- **Transparent**: Shopify IDs visible in Mergado (if element made non-hidden)
- **Persistent**: Data lives in Mergado, not just our database
- **Accessible**: Other extensions/exports can use shopify_id element
- **Efficient**: One API call to create rule (after query creation)

### Negative
- **Query Creation Overhead**: Must create one query per SKU (N API calls)
- **Rule Update Complexity**: Updating Shopify IDs requires updating the entire rule
- **API Pagination**: For large catalogs (>1000 products), may need to split into multiple rules
- **Asynchronous**: Rule application isn't instant, must poll applylogs

### Mitigations
- **Query Caching**: Store query IDs in our database to avoid re-creating for updates
- **Batch Query Creation**: Create queries in batches of 50 to parallelize API calls
- **Rule Splitting**: If data array exceeds reasonable size, create multiple batch_rewriting rules
- **Polling Strategy**: Exponential backoff when polling applylogs to reduce API load

## References
- [Mergado API Blueprint](../mergado.apib) - Lines 3256-3323 (batch_rewriting examples)
- [Mergado Rules Documentation](https://mergado.github.io/docs/apps/rules-and-queries.html)
- Business Plan requirement: "importovat shopify id přes api a zapsat do shopify_id elementu"

## Notes
The `shopify_id` element value format is: `"product_id:variant_id"` (e.g., `"12345:67890"`).

This allows us to store both IDs in one element. We parse them with:
```python
product_id, variant_id = shopify_id.split(":")
```

For products with multiple variants, we'll create one entry per variant, with the SKU of each variant as the query target.
