# Upload Products to Shopify (CSV) — Variants, Metafields, Inventory, Images, Progress

This file is a **comprehensive “skill” reference** for the current product upload implementation and the hard-won lessons captured in `summary.md` (lines 429–460), plus **repo-backed code examples** (primarily `app.js`).

---

## What this upload pipeline guarantees

### Default variant creation (always at least one variant)
- **Every product always has at least one variant**, even when there are no option columns/values.
- This ensures **inventory, price, SKU, and other variant fields** exist and are visible in Shopify (Shopify tracks these on variants, not on product).
- **No “Default” option is shown to customers** when there are no options (option fields are omitted for single-variant products).

### Robust variant ↔ CSV row matching (order-independent)
- Variant metafields and variant-specific updates are **matched using option values** (e.g., color/size/etc.), not variant array index.
- This stays correct even if Shopify reorders variants or if some variants are filtered/skipped.

### Inventory tracking on variants (never on product)
- **Inventory quantity, price, SKU** and related fields are **set on variants only**, as Shopify requires.
- Single-variant products still get variant-level inventory fields through the default-variant rule.

### Image assignment to variants (requires `Image Src` + `Variant Image`)
- For a variant to receive an image, that image must exist in the product’s image list.
- Therefore, the same URL must be present in **both**:
  - `Image Src` (so Shopify creates the image on the product), and
  - `Variant Image` (to associate the image with a specific variant).
- The backend normalizes image URLs by **removing query params** for matching.
- If Shopify does not create all requested images (duplicates/invalid URLs), **variant-image assignment is skipped** for missing images and warnings are logged.

### Real-time progress updates
- Backend updates progress **after each product**.
- Frontend should poll the progress endpoint and render “\(processed / total\)” as it uploads.

---

## Lessons & best practices (from `summary.md` 429–460)

- **Shopify requires at least one variant per product** for inventory/price tracking and display.
- **Do not set option name/value to “Default”** for single-variant products; instead omit option fields entirely to avoid showing a variant selector.
- **Metafields only import for variant rows that contain values**; if you want all variants to have those metafields, fill every row’s metafield columns.
- **Variant image assignment only works if the image exists in the product’s images array** (i.e., is present in `Image Src`).
- **Progress bars work only if progress is updated per product**, not only once at the end.
- **Matching variants by option values is robust and order-independent.**

---

## Common errors & fixes (from `summary.md` 455–460)

- **“Default” variant shown to customers**
  - **Cause**: Setting option fields to `Default`.
  - **Fix**: For single-variant products, **omit option fields** (no options array; no `option1/2/3` on variant).

- **Inventory not shown**
  - **Cause**: No variant created for single-variant product.
  - **Fix**: Always create at least one variant (default variant).

- **Metafields missing on some variants**
  - **Cause**: Variant-to-row mismatch (index-based) or missing values per row.
  - **Fix**: Match by option values; ensure each variant row has metafield values.

- **Variant image assignment fails**
  - **Cause**: Image is missing from `Image Src` or Shopify skipped image creation.
  - **Fix**: Ensure URLs are valid and present in both `Image Src` and `Variant Image`.

- **Progress bar not updating**
  - **Cause**: Backend updates progress only at the end.
  - **Fix**: Update after each product.

---

## Code-backed implementation patterns (examples from this repo)

### 1) Options + variants derived from CSV, with default-variant fallback

Source: `app.js` (inside `POST /api/upload-products-csv`)

Key behaviors:
- Choose up to 3 option columns that actually have values in any row.
- Build variants by mapping row → `option1/2/3` + variant fields.
- If no options/variants are present, create **one default variant** from the “main” row.
- If product has **no options**, keep only a single variant and **delete option fields** (so the storefront doesn’t show a selector).

```js
// app.js (excerpt)
// Determine which metafield-derived columns will act as options
const metafieldOptionColumns = [
  'Barva (product.metafields.custom.barva)',
  'Velikost (product.metafields.custom.velikost)',
  'Provedení (product.metafields.custom.provedeni)',
  'Hodnota (product.metafields.custom.hodnota)',
  'Pevnost (product.metafields.custom.pevnost)',
  'Značka (product.metafields.custom.znacka)',
  'Šířka (product.metafields.custom.sirka)',
  'Velikost balení (product.metafields.custom.velikost_baleni)'
];

// Use first 3 columns that contain at least one non-empty value
const usedOptionColumns = [];
for (const col of metafieldOptionColumns) {
  if (usedOptionColumns.length >= 3) break;
  if (rows.some(row => row[col] && row[col].trim() !== '')) usedOptionColumns.push(col);
}

let options = usedOptionColumns.map(col => col.split(' (')[0]);

let variants = rows.map(row => {
  const hasAnyOptionValue = usedOptionColumns.some(col => row[col] && row[col].trim() !== '');
  if (!hasAnyOptionValue) return null;

  let variant = {};
  usedOptionColumns.forEach((col, idx) => {
    if (row[col] && row[col].trim() !== '') variant[`option${idx + 1}`] = row[col];
  });

  variant.sku = row['Variant SKU'] || '';
  variant.price = row['Variant Price'] || '';
  variant.inventory_quantity = row['Variant Inventory Qty'] || '';
  variant.grams = row['Variant Grams'] || '';
  variant.requires_shipping = row['Variant Requires Shipping'] === 'TRUE' || row['Variant Requires Shipping'] === true;
  variant.taxable = row['Variant Taxable'] === 'TRUE' || row['Variant Taxable'] === true;

  // Enable inventory tracking if CSV says 'shopify'
  const tracker = (row['Variant Inventory Tracker'] || '').toLowerCase();
  variant.inventory_management = tracker === 'shopify' ? 'shopify' : '';

  return variant;
}).filter(Boolean);

// Default variant if no options/variants
if (usedOptionColumns.length === 0 && variants.length === 0) {
  variants = [{
    sku: main['Variant SKU'] || '',
    price: main['Variant Price'] || '',
    inventory_quantity: main['Variant Inventory Qty'] || '',
    grams: main['Variant Grams'] || '',
    requires_shipping: main['Variant Requires Shipping'] === 'TRUE' || main['Variant Requires Shipping'] === true,
    taxable: main['Variant Taxable'] === 'TRUE' || main['Variant Taxable'] === true,
    inventory_management: (main['Variant Inventory Tracker'] || '').toLowerCase() === 'shopify' ? 'shopify' : ''
  }];
}

// If no options: keep single variant and remove option fields
if (options.length === 0 && variants.length > 0) {
  variants = [variants[0]];
  delete variants[0].option1;
  delete variants[0].option2;
  delete variants[0].option3;
}
```

---

### 2) Variant metafields assigned by option-value matching (not index)

Source: `app.js` (inside `POST /api/upload-products-csv`)

Key behavior:
- For each generated variant, find its CSV row by ensuring every used option column matches the variant’s `option1/2/3`.
- Then attach `custom` namespace metafields at the variant level.

```js
// app.js (excerpt)
const metafieldColumns = Object.keys(main).filter(col =>
  /\(product\.metafields\.[^.]+\.[^)]+\)/.test(col)
);
const customMetafieldColumns = metafieldColumns.filter(col =>
  /\(product\.metafields\.custom\.[^)]+\)/.test(col)
);

for (const variant of variants) {
  const matchingRow = rows.find(row => {
    return usedOptionColumns.every((col, idx) => {
      const optionKey = `option${idx + 1}`;
      const csvOptionValue = row[col] || 'Default';
      const variantOptionValue = variant[optionKey] || 'Default';
      return csvOptionValue === variantOptionValue;
    });
  });
  if (!matchingRow) continue;

  const variantMetafields = [];
  for (const col of customMetafieldColumns) {
    const match = col.match(/\(product\.metafields\.([^.]+)\.([^)]+)\)/);
    if (!match) continue;
    const [_, namespace, key] = match;
    const value = matchingRow[col];
    if (value && value !== '') {
      const metafieldType = metafieldTypeOverrides[`${namespace}.${key}`] || 'single_line_text_field';
      variantMetafields.push({ namespace, key, value: String(value), type: metafieldType });
    }
  }

  if (variantMetafields.length > 0) variant.metafields = variantMetafields;
}
```

Operational note:
- If a variant row has empty metafield cells, those metafields **won’t be created** for that variant. Populate all variant rows when you want uniform metafields.

---

### 3) Inventory and “extra” variant fields are updated on variants

Source: `app.js` (existing product path, variant update logic)

Key behavior:
- Compare existing Shopify variant vs CSV variant and update variant fields via the variants endpoint.
- Match variants via a normalized option-key so the update isn’t index-based.

```js
// app.js (excerpt)
function variantKey(v) {
  const opt1 = (v.option1 === 'Default Title') ? '' : (v.option1 || '').trim();
  const opt2 = (v.option2 === 'Default Title') ? '' : (v.option2 || '').trim();
  const opt3 = (v.option3 === 'Default Title') ? '' : (v.option3 || '').trim();
  return [opt1, opt2, opt3].join('||');
}

const csvVariantMap = new Map(csvVariants.map(v => [variantKey(v), v]));
const shopifyVariantMap = new Map(shopifyVariants.map(v => [variantKey(v), v]));

for (const [key, csvVar] of csvVariantMap.entries()) {
  if (!shopifyVariantMap.has(key)) continue;
  const shopVar = shopifyVariantMap.get(key);

  const updatePayload = { id: shopVar.id };
  let needsUpdate = false;

  if (String(shopVar.price) !== String(csvVar.price)) { updatePayload.price = csvVar.price; needsUpdate = true; }
  if (String(shopVar.inventory_quantity) !== String(csvVar.inventory_quantity)) { updatePayload.inventory_quantity = csvVar.inventory_quantity; needsUpdate = true; }
  if (String(shopVar.sku) !== String(csvVar.sku)) { updatePayload.sku = csvVar.sku; needsUpdate = true; }

  if (Boolean(shopVar.requires_shipping) !== Boolean(csvVar.requires_shipping)) { updatePayload.requires_shipping = csvVar.requires_shipping; needsUpdate = true; }
  if (Boolean(shopVar.taxable) !== Boolean(csvVar.taxable)) { updatePayload.taxable = csvVar.taxable; needsUpdate = true; }
  if (String(shopVar.grams) !== String(csvVar.grams)) { updatePayload.grams = csvVar.grams; needsUpdate = true; }

  if (needsUpdate) {
    await safeShopifyPut(
      `https://${SHOPIFY_STORE}/admin/api/2023-10/variants/${shopVar.id}.json`,
      { variant: updatePayload },
      { 'X-Shopify-Access-Token': SHOPIFY_ACCESS_TOKEN, 'Content-Type': 'application/json' },
      5,
      400
    );
  }
}
```

---

### 4) Images: ensure product images include variant images; normalize URLs; skip on mismatches

Source: `app.js` (create path) and `summary.md` rules

Key behaviors:
- Collect image URLs from **both** `Image Src` and `Variant Image` into the product’s `images[]`.
- Normalize by stripping query params (`split('?')[0]`) before mapping.
- If Shopify returns a different number of images than requested, **image assignment to variants is not safe** and is skipped with an error/warn.

```js
// app.js (excerpt) — include both columns in product images
let imageSources = new Set();
for (const row of rows) {
  if (row['Image Src']) imageSources.add(row['Image Src']);
  if (row['Variant Image']) imageSources.add(row['Variant Image']);
}
const images = Array.from(imageSources).map(src => ({ src }));
```

```js
// app.js (excerpt) — variant image assignment after product creation
const originalSrcToIdMap = new Map();
if (newProduct.images && newProduct.images.length > 0 && newProduct.images.length === images.length) {
  for (let i = 0; i < images.length; i++) {
    const normalizedOriginalSrc = images[i].src.split('?')[0];
    originalSrcToIdMap.set(normalizedOriginalSrc, newProduct.images[i].id);
  }
} else {
  console.error(`Mismatch in image count (sent ${images.length}, got ${newProduct.images?.length || 0}). Cannot assign variant images.`);
}

for (const row of rows) {
  const variantImageSrc = row['Variant Image'];
  if (!variantImageSrc) continue;

  const normalizedVariantImageSrc = variantImageSrc.split('?')[0];
  const imageId = originalSrcToIdMap.get(normalizedVariantImageSrc);
  // ... locate variant (SKU first, then option1) and set variant.image_id ...
}
```

Practical rule-of-thumb:
- If you want a variant image to work reliably, the same URL should appear in `Image Src` and `Variant Image` (and should be stable aside from query params).

---

### 5) Progress tracking: update after each product + polling endpoint

Source: `app.js`

Key behaviors:
- Backend stores progress in `uploadProgress[uploadId]`.
- During uploads, it updates `{ processed, total, created, updated, skipped, failed }` **per product**.
- Frontend polls `/api/upload-progress?id=<uploadId>` while uploading.

```js
// app.js (excerpt)
// In-memory progress tracker for uploads
const uploadProgress = {};

// ... inside /api/upload-products-csv loop ...
if (uploadId) {
  uploadProgress[uploadId] = {
    processed: productIndex,
    total: handles.length,
    created: created.length,
    updated: updated.length,
    skipped: skipped.length,
    failed: failed.length
  };
}

// Progress polling endpoint
app.get('/api/upload-progress', (req, res) => {
  const uploadId = req.query.id;
  if (!uploadId || !uploadProgress[uploadId]) return res.status(404).json({ error: 'Upload not found' });
  res.json(uploadProgress[uploadId]);
});
```

---

## CSV requirements checklist (for successful, predictable uploads)

- **Handle**
  - Every row must contain `Handle` (grouping key).

- **Variants**
  - For multi-variant products: populate the option/metafield columns that are used to build options.
  - For single-variant products: do not force option columns; let upload create a single variant with no option fields.

- **Metafields**
  - If you want metafields on every variant, fill the metafield cells on every variant row.

- **Images**
  - If a variant should have an image:
    - Put the URL in **`Variant Image`** on the variant’s row, and
    - Ensure that URL is also present in **some row’s `Image Src`** for the same product (so Shopify creates it).

- **Progress**
  - Provide an `uploadId` (query `uploadId=` or header `x-upload-id`) and poll `/api/upload-progress`.

---

## Related helper: URL normalization (tracking-param stripping)

While variant image matching in `app.js` currently strips query params via `split('?')[0]`, the repo also contains a more general URL normalizer used elsewhere:

Source: `migrator/src/utils/url_normalize.js`

```js
// migrator/src/utils/url_normalize.js (excerpt)
function stripTrackingParams(urlObj) {
  const toRemove = ['utm_source','utm_medium','utm_campaign','utm_term','utm_content','gclid','fbclid'];
  toRemove.forEach(k => urlObj.searchParams.delete(k));
}
```

If you ever want to make image normalization more consistent across the project, consider consolidating image-URL normalization around a single helper (while keeping the “no trailing slash for assets” constraint in mind).

