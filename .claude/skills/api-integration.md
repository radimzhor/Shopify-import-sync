# API Integration Skill

## Pattern for Adding New Mergado API Calls

### 1. Check the API Blueprint
- Reference: `docs/mergado.apib` or https://api-docs.mergado.com/?specs=mergado-api
- Identify: endpoint path, method, required parameters, OAuth scope, response format

### 2. Add Method to MergadoClient (app/services/mergado_client.py)

```python
def method_name(self, param1: str, param2: Optional[int] = None) -> Dict[str, Any]:
    """
    Brief description of what this does.
    
    Args:
        param1: Description
        param2: Description (optional)
        
    Returns:
        Response data from API
        
    Raises:
        APIError: If request fails
    """
    url = f"{self.base_url}/endpoint/{param1}"
    params = {"limit": 100}
    if param2:
        params["param2"] = param2
        
    response = self._request("GET", url, params=params)
    return response.json()
```

### 3. Use the _request Helper
The `_request` method handles:
- Bearer token authentication
- Retry logic (exponential backoff for 429, 502, 503, 504)
- Error response parsing
- Logging

**Never** make raw `requests.get/post` calls outside of `_request`.

### 4. Handle Pagination
For list endpoints with `limit`/`offset`:

```python
def get_all_items(self, shop_id: str) -> List[Dict]:
    """Get all items with automatic pagination."""
    all_items = []
    offset = 0
    limit = 100
    
    while True:
        response = self._request(
            "GET",
            f"{self.base_url}/shops/{shop_id}/items/",
            params={"limit": limit, "offset": offset}
        )
        data = response.json()
        items = data.get("data", [])
        all_items.extend(items)
        
        if len(items) < limit:
            break
        offset += limit
        
    return all_items
```

### 5. Add Type Hints
Use TypedDict or Pydantic models for complex responses:

```python
from typing import TypedDict

class ProjectResponse(TypedDict):
    id: str
    name: str
    url: str
    output_format: str
```

### 6. Write Tests
Create test in `tests/test_services.py`:

```python
def test_method_name(mocker):
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"data": [...]}
    mocker.patch.object(MergadoClient, "_request", return_value=mock_response)
    
    client = MergadoClient(access_token="test_token")
    result = client.method_name("param_value")
    
    assert result["data"] is not None
```

## Pattern for Shopify Proxy Calls

### Use ShopifyProxyService (app/services/shopify_proxy.py)

All Shopify calls go through `/shops/{shop_id}/shopify/proxy/{path}`:

```python
def shopify_method(self, path: str, data: Optional[Dict] = None) -> Dict:
    """
    Call Shopify API via Mergado proxy.
    
    Args:
        path: Shopify API path (e.g., "products.json")
        data: Request body for POST/PUT
        
    Returns:
        Shopify API response
    """
    response = self.mergado_client.shopify_proxy_post(
        self.shop_id,
        path,
        data=data
    )
    return response
```

### Rate Limiting
- Shopify REST API: 2 requests/second
- Use `time.sleep()` or throttling queue
- Respect `Retry-After` header on 429 responses

## Error Handling Pattern

```python
from app.services.exceptions import APIError, AuthenticationError

try:
    result = client.method_name(param)
except AuthenticationError:
    # OAuth token expired or invalid
    flash("Please log in again", "error")
    return redirect(url_for("auth.login"))
except APIError as e:
    # API returned error response
    logger.error(f"API error: {e}")
    flash(f"Operation failed: {e.message}", "error")
    return render_template("error.html", error=e)
```

## Common Gotchas

- **Token expiry**: Always check token before long operations
- **Rate limits**: Batch operations should include delays
- **Pagination**: Don't assume all data fits in one page
- **Nulls**: Mergado API may return null for optional fields
- **Shopify IDs**: Shopify returns both product_id and variant_id - store both
