"""
Rule application endpoints - called by Mergado when applying custom app rules.

These endpoints are public (no OAuth) because Mergado calls them server-to-server
during rule application. They must respond within Mergado's timeout window.
"""
import logging
from typing import Optional

from flask import Blueprint, jsonify, request

from app import db
from app.models.project import Project
from app.models.shopify_id_mapping import ShopifyIDMapping


logger = logging.getLogger(__name__)

rule_bp = Blueprint('rules', __name__, url_prefix='/api/rules')


def _extract_sku(product: dict) -> Optional[str]:
    """
    Extract ITEM_ID (SKU) from a Mergado product payload.

    Supports both API versions:
    - v2022-09-10+: data.elements.ITEM_ID[0].value  (nested structure)
    - pre-2022-09-10: data.ITEM_ID                  (flat key-value)
    """
    data = product.get('data', {})

    # New format (version >= 2022-09-10): nested elements dict
    elements = data.get('elements')
    if elements:
        item_id_list = elements.get('ITEM_ID', [])
        if item_id_list and isinstance(item_id_list, list):
            return item_id_list[0].get('value')

    # Old flat format
    return data.get('ITEM_ID') or None


@rule_bp.route('/shopify-id-writeback', methods=['POST'])
def shopify_id_writeback():
    """
    Custom app rule endpoint called by Mergado during rule application.

    Mergado sends a batch of products; we look up each product's Shopify ID
    by (project, SKU) and return only the products that have a mapping,
    with the shopify_id element value set.

    Request body (Mergado API v2022-09-10+):
        {
            "project_id": "123",
            "rule_id": "456",
            "apply_log_id": "789",
            "request_id": "ABC",
            "data": [
                {
                    "id": "1001",
                    "data": {
                        "elements": {"ITEM_ID": [{"value": "SKU001"}], ...}
                    }
                },
                ...
            ]
        }

    Response:
        {
            "data": [
                {
                    "id": "1001",
                    "data": {
                        "elements": {"shopify_id": [{"value": "9876543:1234567"}]}
                    }
                }
            ]
        }
    """
    payload = request.get_json(silent=True)
    if not payload:
        logger.warning("Writeback rule called with empty/invalid JSON body")
        return jsonify({'data': []}), 200

    mergado_project_id = str(payload.get('project_id', ''))
    products = payload.get('data', [])
    request_id = payload.get('request_id', '')

    logger.info(
        f"Writeback rule called: project={mergado_project_id} "
        f"products={len(products)} request_id={request_id}"
    )

    # Look up our internal project by Mergado project ID
    project = Project.query.filter_by(mergado_project_id=mergado_project_id).first()
    if not project:
        logger.warning(f"Writeback rule: unknown project {mergado_project_id}")
        return jsonify({'data': []}), 200

    # Build SKU list from the batch for a single bulk DB query
    sku_map: dict[str, str] = {}  # sku -> "product_id:variant_id"
    skus_in_batch = []
    product_sku_index: dict[str, str] = {}  # product internal id -> sku

    for product in products:
        sku = _extract_sku(product)
        if sku:
            product_sku_index[product['id']] = sku
            skus_in_batch.append(sku)

    # Single query for all SKUs in this batch
    if skus_in_batch:
        mappings = ShopifyIDMapping.query.filter(
            ShopifyIDMapping.project_id == project.id,
            ShopifyIDMapping.sku.in_(skus_in_batch)
        ).all()
        sku_map = {m.sku: m.combined_id for m in mappings}

    logger.info(
        f"Writeback rule: found {len(sku_map)}/{len(skus_in_batch)} mappings "
        f"for project {mergado_project_id}"
    )

    # Build response — only include products that have a mapping
    result = []
    for product in products:
        sku = product_sku_index.get(product['id'])
        if not sku:
            continue
        shopify_id = sku_map.get(sku)
        if not shopify_id:
            continue
        result.append({
            'id': product['id'],
            'data': {
                'elements': {
                    'shopify_id': [{'value': shopify_id}]
                }
            }
        })

    return jsonify({'data': result}), 200
