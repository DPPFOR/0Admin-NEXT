"""MCP Fabric server package (read-only, local-only).

This package exposes side-effect-free modules for:
- registry: static list of tools and versions
- policy: YAML policy loader with safe defaults
- security: strict bearer token parsing
- observability: try/except import of backend.core.observability with no-op fallback

No HTTP/ASGI servers, threads, or event loops are started here.
"""

