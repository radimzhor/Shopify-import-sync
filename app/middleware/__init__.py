"""
Middleware package for the Mergado Flask application.

Contains logging, error handling, and other middleware components.
"""

from .logging import init_request_logging

__all__ = ['init_request_logging']
