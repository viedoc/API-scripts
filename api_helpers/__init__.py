"""Shared helpers for resolving Viedoc API endpoints."""

from .viedoc_endpoints import (
    DEFAULT_ENDPOINTS_FILE,
    EndpointConfig,
    EndpointResolver,
    EndpointSelection,
    load_endpoint_resolver,
)

__all__ = [
    "DEFAULT_ENDPOINTS_FILE",
    "EndpointConfig",
    "EndpointResolver",
    "EndpointSelection",
    "load_endpoint_resolver",
]
