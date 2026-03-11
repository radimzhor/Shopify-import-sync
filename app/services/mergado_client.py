"""
Mergado API Client - wrapper around the Mergado REST API.

Handles authentication, pagination, retries, and error handling for all Mergado API calls.
"""
import time
import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import requests
from requests import Response

from app.services.exceptions import APIError, AuthenticationError, RateLimitError
from settings import settings


logger = logging.getLogger(__name__)


class MergadoClient:
    """
    Client for Mergado REST API.
    
    Handles OAuth bearer token authentication and provides typed methods
    for common API operations.
    """
    
    def __init__(self, access_token: str, base_url: Optional[str] = None):
        """
        Initialize Mergado API client.
        
        Args:
            access_token: OAuth access token
            base_url: Mergado API base URL (defaults to settings)
        """
        self.access_token = access_token
        self.base_url = base_url or settings.mergado_api_base_url
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
    
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
        **kwargs
    ) -> Response:
        """
        Make authenticated request to Mergado API with retry logic.
        
        Args:
            method: HTTP method
            path: API path (will be joined with base_url)
            params: Query parameters
            json: JSON request body
            **kwargs: Additional requests arguments
            
        Returns:
            Response object
            
        Raises:
            AuthenticationError: If 401 Unauthorized
            RateLimitError: If 429 Too Many Requests
            APIError: For other API errors
        """
        url = urljoin(self.base_url, path.lstrip('/'))
        
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {self.access_token}'
        headers['Content-Type'] = 'application/json'
        
        # Retry logic for transient errors
        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=headers,
                    timeout=30,
                    **kwargs
                )
                
                # Check for HTTP errors
                if response.status_code == 401:
                    raise AuthenticationError("Access token expired or invalid")
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', self.retry_delay * (2 ** attempt)))
                    raise RateLimitError(retry_after=retry_after)
                
                response.raise_for_status()
                return response
                
            except requests.HTTPError as e:
                # Retry on transient errors
                if e.response.status_code in [502, 503, 504, 429]:
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        if e.response.status_code == 429:
                            delay = int(e.response.headers.get('Retry-After', delay))
                        
                        logger.warning(
                            f"Retrying request after {delay}s (attempt {attempt + 1}/{self.max_retries})",
                            extra={'status_code': e.response.status_code, 'url': url}
                        )
                        time.sleep(delay)
                        continue
                
                # Non-retryable error or max retries reached
                error_detail = e.response.text if e.response else str(e)
                raise APIError(
                    f"Mergado API error: {error_detail}",
                    status_code=e.response.status_code if e.response else None
                )
            
            except requests.RequestException as e:
                # Network errors
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Network error, retrying after {delay}s: {e}")
                    time.sleep(delay)
                    continue
                raise APIError(f"Network error: {str(e)}")
        
        raise APIError("Max retries exceeded")
    
    # ============================================================================
    # SHOPS API
    # ============================================================================
    
    def get_shop(self, shop_id: str) -> Dict[str, Any]:
        """
        Get eshop details.
        
        OAuth Scope: shop.read
        
        Args:
            shop_id: Mergado eshop ID
            
        Returns:
            Shop data dict
        """
        response = self._request('GET', f'/shops/{shop_id}/')
        return response.json()
    
    def get_shop_info(self, shop_id: str) -> Dict[str, Any]:
        """
        Get eshop info including keychain connections and stats.
        
        OAuth Scope: shop.read
        
        Args:
            shop_id: Mergado eshop ID
            
        Returns:
            Shop info dict with connections, stats, etc.
        """
        response = self._request('GET', f'/shops/{shop_id}/info/')
        return response.json()
    
    def validate_connection(self, shop_id: str, connection: str) -> Dict[str, Any]:
        """
        Validate a keychain connection (e.g., shopify.com).
        
        OAuth Scope: shop.read
        
        Args:
            shop_id: Mergado eshop ID
            connection: Connection name (e.g., 'shopify.com')
            
        Returns:
            Validation result: {'is_valid': bool, 'errors': [...]}
        """
        response = self._request('GET', f'/shops/{shop_id}/{connection}/validate')
        return response.json()
    
    # ============================================================================
    # PROJECTS API
    # ============================================================================
    
    def get_projects(self, shop_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List all projects for an eshop with automatic pagination.
        
        OAuth Scope: shop.projects.read
        
        Args:
            shop_id: Mergado eshop ID
            limit: Results per page
            
        Returns:
            List of project dicts
        """
        all_projects = []
        offset = 0
        
        while True:
            response = self._request(
                'GET',
                f'/shops/{shop_id}/projects/',
                params={'limit': limit, 'offset': offset}
            )
            data = response.json()
            projects = data.get('data', [])
            all_projects.extend(projects)
            
            # Check if we got all data
            total = data.get('total_results', 0)
            if offset + len(projects) >= total:
                break
            
            offset += limit
        
        return all_projects
    
    def get_project(self, project_id: str) -> Dict[str, Any]:
        """
        Get project details including output URL.
        
        OAuth Scope: project.read
        
        Args:
            project_id: Mergado project ID
            
        Returns:
            Project data dict
        """
        response = self._request('GET', f'/projects/{project_id}/')
        return response.json()
    
    # ============================================================================
    # ELEMENTS API
    # ============================================================================
    
    def get_project_elements(self, project_id: str) -> List[Dict[str, Any]]:
        """
        List project elements in tree structure.
        
        OAuth Scope: project.elements.read
        
        Args:
            project_id: Mergado project ID
            
        Returns:
            Tree of elements
        """
        response = self._request('GET', f'/projects/{project_id}/elements/')
        return response.json().get('data', [])
    
    def create_element(
        self,
        project_id: str,
        name: str,
        hidden: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new element in a project.
        
        OAuth Scope: project.elements.write
        
        Args:
            project_id: Mergado project ID
            name: Element name (e.g., 'shopify_id')
            hidden: Whether element is hidden in UI
            
        Returns:
            Created element data
        """
        response = self._request(
            'POST',
            f'/projects/{project_id}/elements/',
            json={'name': name, 'hidden': hidden}
        )
        return response.json()
    
    # ============================================================================
    # PRODUCTS API
    # ============================================================================
    
    def get_project_products(
        self,
        project_id: str,
        limit: int = 100,
        values_to_extract: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        List products in a project with automatic pagination.
        
        OAuth Scope: project.products.read
        
        Args:
            project_id: Mergado project ID
            limit: Results per page
            values_to_extract: Element paths to extract values for
            
        Returns:
            List of product dicts
        """
        all_products = []
        offset = 0
        
        params = {'limit': limit}
        if values_to_extract:
            params['values_to_extract'] = values_to_extract
        
        while True:
            params['offset'] = offset
            response = self._request(
                'GET',
                f'/projects/{project_id}/products/',
                params=params
            )
            data = response.json()
            products = data.get('data', [])
            all_products.extend(products)
            
            # Check if we got all data
            total = data.get('total_results', 0)
            if offset + len(products) >= total:
                break
            
            offset += limit
        
        return all_products
    
    # ============================================================================
    # RULES & QUERIES API
    # ============================================================================
    
    def create_query(
        self,
        project_id: str,
        query: str,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a query (product filter) in a project.
        
        OAuth Scope: project.queries.write
        
        Args:
            project_id: Mergado project ID
            query: MQL query string (e.g., "ITEM_ID = 'SKU123'")
            name: Query name (optional)
            
        Returns:
            Created query data with query_id
        """
        payload = {'query': query}
        if name:
            payload['name'] = name
        
        response = self._request(
            'POST',
            f'/projects/{project_id}/queries/',
            json=payload
        )
        return response.json()
    
    def create_rule(
        self,
        project_id: str,
        rule_type: str,
        element_path: str,
        data: Any,
        queries: List[Dict[str, str]],
        name: Optional[str] = None,
        applies: bool = True,
        priority: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a rule in a project.
        
        OAuth Scope: project.rules.write
        
        Args:
            project_id: Mergado project ID
            rule_type: Rule type (e.g., 'rewriting', 'batch_rewriting')
            element_path: Target element path
            data: Rule-specific data (dict for rewriting, list for batch_rewriting)
            queries: List of query dicts with 'id' field
            name: Rule name
            applies: Whether rule is enabled
            priority: Rule priority (optional)
            
        Returns:
            Created rule data
        """
        payload = {
            'type': rule_type,
            'element_path': element_path,
            'data': data,
            'queries': queries,
            'applies': applies
        }
        
        if name:
            payload['name'] = name
        if priority:
            payload['priority'] = priority
        
        response = self._request(
            'POST',
            f'/projects/{project_id}/rules/',
            json=payload
        )
        return response.json()
    
    def mark_project_dirty(self, project_id: str) -> Dict[str, Any]:
        """
        Mark project as dirty to trigger rule application.
        
        OAuth Scope: project.write
        
        Args:
            project_id: Mergado project ID
            
        Returns:
            Updated project data
        """
        response = self._request(
            'PATCH',
            f'/projects/{project_id}/',
            json={'is_dirty': True}
        )
        return response.json()
    
    def get_apply_logs(self, project_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get rule application logs for a project.
        
        OAuth Scope: project.logs.read
        
        Args:
            project_id: Mergado project ID
            limit: Number of logs to retrieve
            
        Returns:
            List of apply log dicts
        """
        response = self._request(
            'GET',
            f'/projects/{project_id}/applylogs/',
            params={'limit': limit}
        )
        return response.json().get('data', [])
    
    # ============================================================================
    # SHOPIFY PROXY API
    # ============================================================================
    
    def shopify_proxy_get(
        self,
        shop_id: str,
        path: str,
        params: Optional[Dict] = None
    ) -> Response:
        """
        Make GET request to Shopify via Keychain Proxy.
        
        OAuth Scope: shop.proxy.read
        
        Args:
            shop_id: Mergado eshop ID
            path: Shopify API path (e.g., 'admin/api/2024-01/products.json')
            params: Query parameters
            
        Returns:
            Response object (call .json() to get data)
        """
        return self._request(
            'GET',
            f'/shops/{shop_id}/shopify/proxy/{path}',
            params=params
        )
    
    def shopify_proxy_post(
        self,
        shop_id: str,
        path: str,
        data: Optional[Dict] = None
    ) -> Response:
        """
        Make POST request to Shopify via Keychain Proxy.
        
        OAuth Scope: shop.proxy.write
        
        Args:
            shop_id: Mergado eshop ID
            path: Shopify API path
            data: Request body
            
        Returns:
            Response object
        """
        return self._request(
            'POST',
            f'/shops/{shop_id}/shopify/proxy/{path}',
            json=data
        )
    
    def shopify_proxy_put(
        self,
        shop_id: str,
        path: str,
        data: Optional[Dict] = None
    ) -> Response:
        """
        Make PUT request to Shopify via Keychain Proxy.
        
        OAuth Scope: shop.proxy.write
        
        Args:
            shop_id: Mergado eshop ID
            path: Shopify API path
            data: Request body
            
        Returns:
            Response object
        """
        return self._request(
            'PUT',
            f'/shops/{shop_id}/shopify/proxy/{path}',
            json=data
        )
    
    def shopify_proxy_delete(
        self,
        shop_id: str,
        path: str
    ) -> Response:
        """
        Make DELETE request to Shopify via Keychain Proxy.
        
        OAuth Scope: shop.proxy.write
        
        Args:
            shop_id: Mergado eshop ID
            path: Shopify API path
            
        Returns:
            Response object
        """
        return self._request(
            'DELETE',
            f'/shops/{shop_id}/shopify/proxy/{path}'
        )
