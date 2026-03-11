# app/services/ - Business Logic Services

This module contains all business logic and external API integrations. Services are the bridge between routes (HTTP layer) and models (data layer).

## What's Here

- `mergado_client.py` - Mergado REST API wrapper
- `shopify_proxy.py` - Shopify API via Keychain Proxy
- `import_service.py` - Product import orchestration
- `sync_service.py` - Stock/price synchronization
- `rule_manager.py` - Mergado rule creation for Shopify ID writeback
- `csv_parser.py` - Shopify CSV format parsing
- `exceptions.py` - Custom exception classes

## Architecture Pattern

All services follow this structure:

```python
class ServiceName:
    def __init__(self, dependency1, dependency2):
        self.dependency1 = dependency1
        self.dependency2 = dependency2
    
    def public_method(self, param: Type) -> ReturnType:
        """Public API with full error handling."""
        try:
            result = self._internal_method(param)
            self._log_success(result)
            return result
        except ExternalAPIError as e:
            self._log_error(e)
            raise ServiceError(f"Operation failed: {e.message}")
    
    def _internal_method(self, param: Type) -> ReturnType:
        """Private implementation."""
        # Core logic here
        pass
```

## API Client Pattern (MergadoClient, ShopifyProxyService)

### Structure
```python
class MergadoClient:
    def __init__(self, access_token: str, base_url: str = "https://api.mergado.com"):
        self.access_token = access_token
        self.base_url = base_url
    
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Central request method with retry logic."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        # Add retry logic here
        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response
    
    def get_project(self, project_id: str) -> Dict[str, Any]:
        """Get project details."""
        response = self._request("GET", f"{self.base_url}/projects/{project_id}/")
        return response.json()
```

### Retry Logic
For transient errors (429, 502, 503, 504), retry with exponential backoff:

```python
import time
from requests.exceptions import HTTPError

MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

for attempt in range(MAX_RETRIES):
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except HTTPError as e:
        if e.response.status_code in [429, 502, 503, 504]:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                if e.response.status_code == 429:
                    # Respect Retry-After header
                    delay = int(e.response.headers.get('Retry-After', delay))
                logger.warning(f"Retrying after {delay}s (attempt {attempt + 1})")
                time.sleep(delay)
            else:
                raise
        else:
            raise
```

## Error Handling

### Exception Hierarchy
```python
class ServiceError(Exception):
    """Base service exception."""
    pass

class APIError(ServiceError):
    """External API returned an error."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.details = details

class AuthenticationError(APIError):
    """OAuth token is invalid or expired."""
    pass

class ValidationError(ServiceError):
    """Input validation failed."""
    pass
```

### Usage in Services
```python
def get_project(self, project_id: str) -> Dict:
    try:
        response = self._request("GET", f"/projects/{project_id}/")
        return response.json()
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            raise AuthenticationError("Access token expired or invalid")
        elif e.response.status_code == 404:
            raise APIError(f"Project {project_id} not found", status_code=404)
        else:
            raise APIError(f"Mergado API error: {e.response.text}", 
                          status_code=e.response.status_code)
```

## Pagination Pattern

For Mergado API endpoints that return lists:

```python
def get_all_projects(self, shop_id: str) -> List[Dict]:
    """Fetch all projects with automatic pagination."""
    all_projects = []
    offset = 0
    limit = 100  # Mergado default max
    
    while True:
        response = self._request(
            "GET",
            f"{self.base_url}/shops/{shop_id}/projects/",
            params={"limit": limit, "offset": offset}
        )
        data = response.json()
        projects = data.get("data", [])
        all_projects.extend(projects)
        
        # Check if we got all data
        total = data.get("total_results", 0)
        if offset + len(projects) >= total:
            break
        
        offset += limit
    
    return all_projects
```

## Rate Limiting

### Shopify Rate Limits
- REST API: 2 requests/second
- Bucket size: 40 requests
- Strategy: Throttle or use leaky bucket

```python
import time

class RateLimiter:
    def __init__(self, requests_per_second: float):
        self.min_interval = 1.0 / requests_per_second
        self.last_request = 0
    
    def wait(self):
        """Wait if necessary to respect rate limit."""
        elapsed = time.time() - self.last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request = time.time()

# Usage:
shopify_limiter = RateLimiter(2.0)  # 2 req/sec

def create_product(self, product_data):
    shopify_limiter.wait()
    return self._proxy_request("POST", "products.json", data=product_data)
```

## Logging

Use structured logging with context:

```python
import logging

logger = logging.getLogger(__name__)

def import_products(self, project_id: str, product_data: List[Dict]):
    logger.info(f"Starting product import", extra={
        "project_id": project_id,
        "product_count": len(product_data)
    })
    
    try:
        results = self._process_import(product_data)
        logger.info(f"Import completed", extra={
            "project_id": project_id,
            "success": results["success"],
            "failed": results["failed"]
        })
        return results
    except Exception as e:
        logger.error(f"Import failed", extra={
            "project_id": project_id,
            "error": str(e)
        }, exc_info=True)
        raise
```

## Testing Services

### Mock External APIs
```python
def test_get_project(mocker):
    # Mock the _request method
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "id": "123",
        "name": "Test Project",
        "url": "https://example.com/feed.xml"
    }
    mocker.patch.object(MergadoClient, "_request", return_value=mock_response)
    
    client = MergadoClient(access_token="test_token")
    project = client.get_project("123")
    
    assert project["id"] == "123"
    assert project["name"] == "Test Project"
```

### Test Error Handling
```python
def test_get_project_not_found(mocker):
    mock_error = requests.HTTPError()
    mock_error.response = mocker.Mock(status_code=404, text="Not found")
    mocker.patch.object(MergadoClient, "_request", side_effect=mock_error)
    
    client = MergadoClient(access_token="test_token")
    
    with pytest.raises(APIError) as exc_info:
        client.get_project("999")
    
    assert "not found" in str(exc_info.value).lower()
```

## Common Gotchas

### 1. Don't Retry Non-Idempotent Operations Blindly
```python
# BAD: Retrying POST might create duplicate resources
def create_product(self, data):
    for attempt in range(3):
        try:
            return self._request("POST", "/products", json=data)
        except HTTPError:
            # Might have succeeded but returned error
            pass

# GOOD: Check if resource exists before retry
def create_product(self, data):
    try:
        return self._request("POST", "/products", json=data)
    except HTTPError as e:
        if e.response.status_code == 409:  # Conflict
            # Product already exists, fetch and return it
            return self.get_product_by_sku(data["sku"])
        raise
```

### 2. Handle Null Values from API
```python
# Mergado API may return null for optional fields
project = client.get_project("123")
output_url = project.get("url")  # Might be None
if output_url:
    feed_data = download_feed(output_url)
```

### 3. Validate Data Before API Calls
```python
def create_product(self, product_data: Dict):
    # Validate required fields
    required = ["sku", "title", "price"]
    missing = [f for f in required if f not in product_data]
    if missing:
        raise ValidationError(f"Missing required fields: {missing}")
    
    # Proceed with API call
    return self._proxy_request("POST", "products.json", data=product_data)
```

## Performance Tips

- **Batch operations**: Process 50-100 items per API call when possible
- **Parallel requests**: Use `concurrent.futures` for independent API calls
- **Cache responses**: Cache rarely-changing data (e.g., project metadata)
- **Async processing**: Use background jobs for long-running operations

## References

- [API Integration Skill](../../.claude/skills/api-integration.md)
- [Mergado API Blueprint](../../docs/mergado.apib)
- [ADR-003: Keychain Proxy](../../docs/adr/003-keychain-proxy-shopify-auth.md)
