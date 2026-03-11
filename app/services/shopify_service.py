"""
Shopify Service - high-level Shopify operations via Mergado Keychain Proxy.

Provides typed methods for common Shopify operations using the Mergado proxy.
"""
import logging
from typing import Dict, List, Optional, Any

from app.services.mergado_client import MergadoClient
from app.services.exceptions import ShopifyConnectionError, APIError


logger = logging.getLogger(__name__)


class ShopifyService:
    """
    Service for Shopify API operations via Mergado Keychain Proxy.
    
    Uses the Mergado /shops/{id}/shopify/proxy/{path} endpoint to make
    authenticated requests to Shopify without managing separate credentials.
    """
    
    # Shopify API version
    SHOPIFY_API_VERSION = '2024-01'
    
    def __init__(self, mergado_client: MergadoClient, shop_id: str):
        """
        Initialize Shopify service.
        
        Args:
            mergado_client: Initialized MergadoClient instance
            shop_id: Mergado eshop ID with Shopify connected
        """
        self.client = mergado_client
        self.shop_id = shop_id
    
    def _validate_connection(self) -> None:
        """
        Validate Shopify connection via Keychain.
        
        Raises:
            ShopifyConnectionError: If Shopify is not connected
        """
        try:
            validation = self.client.validate_connection(self.shop_id, 'shopify.com')
            if not validation.get('is_valid'):
                errors = validation.get('errors', [])
                raise ShopifyConnectionError(f"Shopify validation failed: {errors}")
        except APIError as e:
            raise ShopifyConnectionError(f"Failed to validate Shopify connection: {str(e)}")
    
    def _api_path(self, endpoint: str) -> str:
        """
        Build Shopify API path with version.
        
        Args:
            endpoint: Shopify endpoint (e.g., 'products.json')
            
        Returns:
            Full path (e.g., 'admin/api/2024-01/products.json')
        """
        endpoint = endpoint.lstrip('/')
        return f'admin/api/{self.SHOPIFY_API_VERSION}/{endpoint}'
    
    # ============================================================================
    # PRODUCTS API
    # ============================================================================
    
    def create_product(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a product in Shopify.
        
        Args:
            product_data: Product data dict (should include 'product' wrapper)
            
        Returns:
            Created product data
        """
        response = self.client.shopify_proxy_post(
            self.shop_id,
            self._api_path('products.json'),
            data=product_data
        )
        return response.json()
    
    def get_product(self, product_id: str) -> Dict[str, Any]:
        """
        Get product by ID.
        
        Args:
            product_id: Shopify product ID
            
        Returns:
            Product data
        """
        response = self.client.shopify_proxy_get(
            self.shop_id,
            self._api_path(f'products/{product_id}.json')
        )
        return response.json()
    
    def update_product(
        self,
        product_id: str,
        product_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a product in Shopify.
        
        Args:
            product_id: Shopify product ID
            product_data: Product data dict (should include 'product' wrapper)
            
        Returns:
            Updated product data
        """
        response = self.client.shopify_proxy_put(
            self.shop_id,
            self._api_path(f'products/{product_id}.json'),
            data=product_data
        )
        return response.json()
    
    def get_product_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Find product by SKU (searches variants).
        
        Args:
            sku: Product SKU
            
        Returns:
            Product data if found, None otherwise
        """
        try:
            response = self.client.shopify_proxy_get(
                self.shop_id,
                self._api_path('products.json'),
                params={'limit': 1, 'fields': 'id,variants', 'sku': sku}
            )
            products = response.json().get('products', [])
            
            # Search through variants for matching SKU
            for product in products:
                for variant in product.get('variants', []):
                    if variant.get('sku') == sku:
                        return self.get_product(product['id'])
            
            return None
        except APIError:
            return None
    
    def list_products(
        self,
        limit: int = 50,
        page_info: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List products with cursor-based pagination.
        
        Args:
            limit: Number of products per page
            page_info: Cursor for pagination (from Link header)
            
        Returns:
            Dict with 'products' list and 'next_page_info' cursor
        """
        params = {'limit': limit}
        if page_info:
            params['page_info'] = page_info
        
        response = self.client.shopify_proxy_get(
            self.shop_id,
            self._api_path('products.json'),
            params=params
        )
        
        # Extract next page cursor from Link header
        link_header = response.headers.get('Link', '')
        next_page_info = None
        if 'rel="next"' in link_header:
            # Parse page_info from Link header
            for part in link_header.split(','):
                if 'rel="next"' in part:
                    url_part = part.split(';')[0].strip('<> ')
                    if 'page_info=' in url_part:
                        next_page_info = url_part.split('page_info=')[1]
                    break
        
        return {
            'products': response.json().get('products', []),
            'next_page_info': next_page_info
        }
    
    # ============================================================================
    # VARIANTS API
    # ============================================================================
    
    def update_variant(
        self,
        variant_id: str,
        variant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a product variant (useful for stock/price sync).
        
        Args:
            variant_id: Shopify variant ID
            variant_data: Variant data dict (should include 'variant' wrapper)
            
        Returns:
            Updated variant data
        """
        response = self.client.shopify_proxy_put(
            self.shop_id,
            self._api_path(f'variants/{variant_id}.json'),
            data=variant_data
        )
        return response.json()
    
    def get_variant(self, variant_id: str) -> Dict[str, Any]:
        """
        Get variant by ID.
        
        Args:
            variant_id: Shopify variant ID
            
        Returns:
            Variant data
        """
        response = self.client.shopify_proxy_get(
            self.shop_id,
            self._api_path(f'variants/{variant_id}.json')
        )
        return response.json()
    
    # ============================================================================
    # INVENTORY API
    # ============================================================================
    
    def update_inventory_level(
        self,
        inventory_item_id: str,
        location_id: str,
        available: int
    ) -> Dict[str, Any]:
        """
        Update inventory level for a variant.
        
        Args:
            inventory_item_id: Shopify inventory item ID (from variant)
            location_id: Shopify location ID
            available: Available quantity
            
        Returns:
            Updated inventory level data
        """
        response = self.client.shopify_proxy_post(
            self.shop_id,
            self._api_path('inventory_levels/set.json'),
            data={
                'inventory_item_id': inventory_item_id,
                'location_id': location_id,
                'available': available
            }
        )
        return response.json()
    
    def get_locations(self) -> List[Dict[str, Any]]:
        """
        Get Shopify store locations.
        
        Returns:
            List of location dicts
        """
        response = self.client.shopify_proxy_get(
            self.shop_id,
            self._api_path('locations.json')
        )
        return response.json().get('locations', [])
