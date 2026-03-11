"""
Custom exception classes for services layer.
"""
from typing import Optional, Dict, Any


class ServiceError(Exception):
    """Base exception for service layer errors."""
    pass


class APIError(ServiceError):
    """External API returned an error."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(APIError):
    """OAuth token is invalid or expired."""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class ValidationError(ServiceError):
    """Input validation failed."""
    pass


class RateLimitError(APIError):
    """Rate limit exceeded."""
    
    def __init__(self, retry_after: Optional[int] = None):
        message = f"Rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after} seconds"
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class ShopifyConnectionError(APIError):
    """Shopify is not connected via Keychain."""
    
    def __init__(self, message: str = "Shopify not connected in Keychain"):
        super().__init__(message, status_code=400)
