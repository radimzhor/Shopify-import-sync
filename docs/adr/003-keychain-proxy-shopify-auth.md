# ADR-003: Shopify API Access via Keychain Proxy

## Status
**Accepted** - 2026-03-04

## Context
The Shopify Import & Sync needs to interact with the Shopify API to:
- Create and update products
- Set inventory levels
- Update prices
- Fetch existing products for matching

Shopify API requires authentication, typically via OAuth or API keys. We need to decide how to handle Shopify authentication and API access.

### Shopify Authentication Options
1. **Direct OAuth**: App registers as Shopify app, implements OAuth flow
2. **API Keys**: Users provide private app API keys
3. **Mergado Keychain Proxy**: Use Mergado's proxy that handles auth

## Decision
We will access the Shopify API **exclusively through the Mergado Keychain Proxy**.

**Endpoint Pattern**: `POST /shops/{shop_id}/shopify/proxy/{shopify_api_path}`

All Shopify API calls are proxied through Mergado's API at `/shops/{id}/shopify/proxy/{path}`, where Mergado's Keychain service handles the authentication with Shopify on behalf of the user.

### Implementation Approach
- Never make direct calls to Shopify's API endpoints
- All Shopify operations go through `MergadoClient.shopify_proxy_*()` methods
- Use the user's Mergado OAuth token to authenticate with the proxy
- The proxy forwards requests to Shopify with proper Shopify credentials
- Responses from Shopify are returned unchanged through the proxy

### Example Usage
```python
# DON'T DO THIS (direct Shopify API call):
# response = requests.post(
#     "https://shop.myshopify.com/admin/api/2024-01/products.json",
#     headers={"X-Shopify-Access-Token": "..."}
# )

# DO THIS (via Mergado Keychain Proxy):
response = mergado_client.shopify_proxy_post(
    shop_id="123",
    path="admin/api/2024-01/products.json",
    data={"product": {...}}
)
```

### Proxy Capabilities
The Mergado Keychain Proxy supports:
- **REST Admin API**: Legacy Shopify REST endpoints
- **GraphQL Admin API**: Modern Shopify GraphQL API
- **All HTTP Methods**: GET, POST, PUT, DELETE
- **Full Request/Response**: Headers and body forwarded unchanged

### Required OAuth Scopes
To use the Shopify proxy, our app needs these Mergado OAuth scopes:
- `shop.proxy.read` - For GET requests to Shopify
- `shop.proxy.write` - For POST/PUT/DELETE requests to Shopify

## Alternatives Considered

### 1. Direct Shopify OAuth Implementation
**Approach**: Register as a Shopify app, implement full OAuth flow ourselves.

**Pros**:
- Direct control over API calls
- No intermediary proxy
- Could support public Shopify apps

**Cons**:
- Users would need to authenticate twice (Mergado + Shopify)
- We'd need to store and manage Shopify credentials
- Requires Shopify Partner account and app registration
- Shopify OAuth is separate from Mergado auth
- **Rejected**: Duplicates existing Mergado Keychain functionality

### 2. User-Provided API Keys
**Approach**: Ask users to generate Shopify private app API keys and paste them into our UI.

**Pros**:
- Simple for developers
- No OAuth complexity

**Cons**:
- Terrible UX for users
- Private apps deprecated by Shopify
- Users must manually create and copy credentials
- Security risk if keys are leaked
- We'd need secure credential storage
- **Rejected**: Poor user experience

### 3. Shopify App Bridge (Embedded App)
**Approach**: Build as a Shopify embedded app that runs inside Shopify admin.

**Pros**:
- Native Shopify integration
- No separate authentication

**Cons**:
- Doesn't integrate with Mergado ecosystem
- Users manage products in Shopify, not Mergado
- Defeats the purpose of the connector
- **Rejected**: Wrong integration point

## Consequences

### Positive
- **Single Sign-On**: Users only authenticate with Mergado
- **No Credential Management**: Mergado Keychain handles Shopify tokens
- **Security**: Shopify credentials never touch our app
- **Simplicity**: No OAuth implementation needed
- **Consistent**: Matches Mergado's architecture for other integrations
- **Validated Connection**: Users set up Shopify connection in Mergado Keychain first
- **Permission Management**: Shopify scopes managed by Mergado

### Negative
- **Dependency**: Relies on Mergado Keychain service availability
- **Proxy Overhead**: Small latency added by proxy layer
- **Debugging**: Harder to inspect raw Shopify API responses
- **Rate Limiting**: Subject to any rate limits Mergado applies
- **API Coverage**: Can only use endpoints Mergado proxy supports (all major ones)

### Mitigations
- **Connection Validation**: Check Shopify connection before operations using `GET /shops/{id}/shopify/validate`
- **Error Handling**: Distinguish between proxy errors and Shopify API errors
- **Logging**: Log proxy responses for debugging
- **Fallback**: If proxy is down, show user clear error message with Mergado support link

## Implementation Details

### ShopifyProxyService Structure
```python
class ShopifyProxyService:
    def __init__(self, mergado_client: MergadoClient, shop_id: str):
        self.mergado_client = mergado_client
        self.shop_id = shop_id
    
    def _proxy_request(self, method: str, path: str, data: Optional[Dict] = None):
        """Make proxied request to Shopify via Mergado Keychain."""
        if method == "GET":
            return self.mergado_client.shopify_proxy_get(self.shop_id, path)
        elif method == "POST":
            return self.mergado_client.shopify_proxy_post(self.shop_id, path, data)
        elif method == "PUT":
            return self.mergado_client.shopify_proxy_put(self.shop_id, path, data)
        elif method == "DELETE":
            return self.mergado_client.shopify_proxy_delete(self.shop_id, path)
    
    def create_product(self, product_data: Dict) -> Dict:
        """Create a product in Shopify."""
        return self._proxy_request("POST", "admin/api/2024-01/products.json", 
                                    data={"product": product_data})
    
    def set_inventory_level(self, inventory_item_id: int, location_id: int, available: int):
        """Set inventory level for a variant."""
        return self._proxy_request("POST", "admin/api/2024-01/inventory_levels/set.json",
                                    data={
                                        "inventory_item_id": inventory_item_id,
                                        "location_id": location_id,
                                        "available": available
                                    })
```

### Error Handling
```python
try:
    result = shopify_proxy.create_product(product_data)
except MergadoAPIError as e:
    if "shopify" in e.message.lower():
        # Shopify rejected the request
        logger.error(f"Shopify API error: {e.details}")
    else:
        # Proxy/Mergado error
        logger.error(f"Proxy error: {e.message}")
    raise
```

### Connection Validation
Before any Shopify operations, validate the connection:
```python
validation = mergado_client.validate_connection(shop_id, "shopify.com")
if not validation.get("is_valid"):
    errors = validation.get("errors", [])
    raise ShopifyConnectionError(f"Shopify not connected: {errors}")
```

## References
- [Mergado API Blueprint](../mergado.apib) - Lines 7138-7199 (Shopify proxy endpoints)
- [Mergado Keychain Documentation](https://api-docs.mergado.com/?specs=mergado-api#/Shopify)
- Business Plan: "Propojení s Shopify storem - bude přes Keychain Proxy"

## Notes
The Mergado Keychain Proxy supports both the Shopify REST Admin API and the GraphQL Admin API. For the MVP, we'll use REST API as it's simpler and well-documented. GraphQL can be added later for more efficient queries.

Shopify API versioning is handled in the `path` parameter (e.g., `admin/api/2024-01/products.json`). We'll use the latest stable version available at the time of implementation.
