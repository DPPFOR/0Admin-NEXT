"""Shared Flock client for agent communication.

Provides common functionality for Flock-based agent communication
with proper error handling and observability.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timezone
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class FlockRequest:
    """Represents a Flock request."""
    
    method: str
    url: str
    headers: Dict[str, str]
    data: Optional[Dict[str, Any]] = None
    timeout: int = 10
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "method": self.method,
            "url": self.url,
            "headers": {k: v for k, v in self.headers.items() if k.lower() != 'authorization'},
            "data": self.data,
            "timeout": self.timeout,
            "correlation_id": self.correlation_id,
        }


@dataclass
class FlockResponse:
    """Represents a Flock response."""
    
    status_code: int
    headers: Dict[str, str]
    data: Dict[str, Any]
    request_time: float
    correlation_id: Optional[str] = None
    
    @property
    def is_success(self) -> bool:
        """Check if response indicates success."""
        return 200 <= self.status_code < 300
    
    @property
    def is_rate_limited(self) -> bool:
        """Check if response indicates rate limiting."""
        return self.status_code == 429
    
    @property
    def is_server_error(self) -> bool:
        """Check if response indicates server error."""
        return 500 <= self.status_code < 600
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "status_code": self.status_code,
            "headers": self.headers,
            "data": self.data,
            "request_time": self.request_time,
            "correlation_id": self.correlation_id,
        }


class FlockClient:
    """HTTP client for Flock agent communication.
    
    Provides retry logic, rate limiting, and observability
    for agent-to-agent communication.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: int = 10,
        max_retries: int = 3,
        backoff_factor: float = 0.3,
        rate_limit_retry: bool = True
    ):
        """Initialize Flock client.
        
        Args:
            base_url: Base URL for Flock API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            backoff_factor: Backoff factor for retries
            rate_limit_retry: Whether to retry on rate limiting
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.rate_limit_retry = rate_limit_retry
        
        # Setup session with retry strategy
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> FlockResponse:
        """Make HTTP request with error handling.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            headers: Request headers
            data: Request data
            timeout: Request timeout
            correlation_id: Correlation ID for tracing
            
        Returns:
            Flock response object
            
        Raises:
            requests.RequestException: On request failure
        """
        if headers is None:
            headers = {}
        
        if timeout is None:
            timeout = self.timeout
        
        # Add correlation ID to headers
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        
        # Add Flock-specific headers
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("User-Agent", "Flock-Agent/1.0")
        
        # Prepare request
        url = f"{self.base_url}{endpoint}"
        request_data = json.dumps(data) if data else None
        
        request = FlockRequest(
            method=method,
            url=url,
            headers=headers,
            data=data,
            timeout=timeout,
            correlation_id=correlation_id
        )
        
        # Log request (without sensitive data)
        self.logger.debug("Flock request", extra={
            "request": request.to_dict(),
            "correlation_id": correlation_id
        })
        
        start_time = time.time()
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                data=request_data,
                timeout=timeout
            )
            
            request_time = time.time() - start_time
            
            # Parse response
            try:
                response_data = response.json()
            except ValueError:
                response_data = {"error": "Invalid JSON response"}
            
            flock_response = FlockResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                data=response_data,
                request_time=request_time,
                correlation_id=correlation_id
            )
            
            # Log response
            self.logger.debug("Flock response", extra={
                "response": flock_response.to_dict(),
                "correlation_id": correlation_id
            })
            
            return flock_response
            
        except requests.RequestException as e:
            request_time = time.time() - start_time
            self.logger.error("Flock request failed", extra={
                "error": str(e),
                "request": request.to_dict(),
                "request_time": request_time,
                "correlation_id": correlation_id
            })
            raise
    
    def get(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> FlockResponse:
        """Make GET request."""
        return self._make_request(
            method="GET",
            endpoint=endpoint,
            headers=headers,
            timeout=timeout,
            correlation_id=correlation_id
        )
    
    def post(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> FlockResponse:
        """Make POST request."""
        return self._make_request(
            method="POST",
            endpoint=endpoint,
            headers=headers,
            data=data,
            timeout=timeout,
            correlation_id=correlation_id
        )
    
    def put(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> FlockResponse:
        """Make PUT request."""
        return self._make_request(
            method="PUT",
            endpoint=endpoint,
            headers=headers,
            data=data,
            timeout=timeout,
            correlation_id=correlation_id
        )
    
    def delete(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> FlockResponse:
        """Make DELETE request."""
        return self._make_request(
            method="DELETE",
            endpoint=endpoint,
            headers=headers,
            timeout=timeout,
            correlation_id=correlation_id
        )
    
    def health_check(self) -> bool:
        """Check if Flock service is healthy.
        
        Returns:
            True if service is healthy
        """
        try:
            response = self.get("/healthz", timeout=5)
            return response.is_success
        except Exception:
            return False
    
    def get_metrics(self) -> Optional[Dict[str, Any]]:
        """Get Flock service metrics.
        
        Returns:
            Metrics data or None if unavailable
        """
        try:
            response = self.get("/metrics", timeout=5)
            if response.is_success:
                return response.data
            return None
        except Exception:
            return None
    
    def close(self):
        """Close the client session."""
        self.session.close()
