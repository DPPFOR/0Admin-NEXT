"""Configuration management for Mahnwesen agent.

Provides tenant-specific configuration with sensible defaults
and environment-based overrides.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from decimal import Decimal


@dataclass
class DunningConfig:
    """Configuration for dunning processes.
    
    Supports tenant-specific overrides via environment variables
    with pattern: MAHNWESEN_<TENANT_ID>_<SETTING>
    """
    
    # Tenant identification
    tenant_id: str
    tenant_name: Optional[str] = None
    
    # Dunning stage thresholds (days)
    stage_1_threshold: int = 3
    stage_2_threshold: int = 14  
    stage_3_threshold: int = 30
    
    # Minimum amount for dunning (in cents)
    min_amount_cents: int = 100  # 1.00 EUR
    
    # Grace period before dunning starts (days)
    grace_days: int = 0
    
    # Rate limiting (notices per hour per tenant)
    max_notices_per_hour: int = 200
    
    # Template settings
    default_locale: str = "de-DE"
    template_version: str = "v1"
    
    # Company information
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    support_email: Optional[str] = None
    
    # API settings
    read_api_timeout: int = 10  # seconds
    read_api_base_url: str = "http://localhost:8000"
    
    # Outbox settings
    outbox_retry_attempts: int = 10
    outbox_retry_backoff_base: int = 1  # seconds
    outbox_retry_backoff_max: int = 60  # seconds
    
    # Stop list patterns (regex patterns for invoice numbers)
    stop_list_patterns: list[str] = field(default_factory=list)
    
    # Branding settings
    company_name: str = "0Admin"
    company_address: str = ""
    support_email: str = "support@0admin.com"
    
    @classmethod
    def from_tenant(cls, tenant_id: str) -> "DunningConfig":
        """Create configuration for specific tenant.
        
        Args:
            tenant_id: UUID of the tenant
            
        Returns:
            Configured instance with tenant-specific overrides
        """
        # Base configuration
        config = cls(tenant_id=tenant_id)
        
        # Apply tenant-specific environment overrides
        prefix = f"MAHNWESEN_{tenant_id.upper().replace('-', '_')}"
        
        # Override from environment if present
        config.stage_1_threshold = int(
            os.getenv(f"{prefix}_STAGE_1_THRESHOLD", config.stage_1_threshold)
        )
        config.stage_2_threshold = int(
            os.getenv(f"{prefix}_STAGE_2_THRESHOLD", config.stage_2_threshold)
        )
        config.stage_3_threshold = int(
            os.getenv(f"{prefix}_STAGE_3_THRESHOLD", config.stage_3_threshold)
        )
        config.min_amount_cents = int(
            os.getenv(f"{prefix}_MIN_AMOUNT_CENTS", config.min_amount_cents)
        )
        config.grace_days = int(
            os.getenv(f"{prefix}_GRACE_DAYS", config.grace_days)
        )
        config.max_notices_per_hour = int(
            os.getenv(f"{prefix}_MAX_NOTICES_PER_HOUR", config.max_notices_per_hour)
        )
        config.default_locale = os.getenv(
            f"{prefix}_LOCALE", config.default_locale
        )
        config.read_api_base_url = os.getenv(
            f"{prefix}_READ_API_URL", config.read_api_base_url
        )
        config.company_name = os.getenv(
            f"{prefix}_COMPANY_NAME", config.company_name
        )
        config.company_address = os.getenv(
            f"{prefix}_COMPANY_ADDRESS", config.company_address
        )
        config.support_email = os.getenv(
            f"{prefix}_SUPPORT_EMAIL", config.support_email
        )
        
        return config
    
    def get_stage_threshold(self, stage: int) -> int:
        """Get threshold for specific dunning stage.
        
        Args:
            stage: Dunning stage (1, 2, or 3)
            
        Returns:
            Threshold in days
            
        Raises:
            ValueError: If stage is not 1, 2, or 3
        """
        if stage == 1:
            return self.stage_1_threshold
        elif stage == 2:
            return self.stage_2_threshold
        elif stage == 3:
            return self.stage_3_threshold
        else:
            raise ValueError(f"Invalid dunning stage: {stage}")
    
    def get_min_amount_decimal(self) -> Decimal:
        """Get minimum amount as Decimal for calculations.
        
        Returns:
            Minimum amount in EUR
        """
        return Decimal(self.min_amount_cents) / 100
    
    def is_stop_listed(self, invoice_number: str) -> bool:
        """Check if invoice number matches stop list patterns.
        
        Args:
            invoice_number: Invoice number to check
            
        Returns:
            True if invoice should be excluded from dunning
        """
        import re
        
        for pattern in self.stop_list_patterns:
            if re.search(pattern, invoice_number, re.IGNORECASE):
                return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of configuration
        """
        return {
            "tenant_id": self.tenant_id,
            "stage_1_threshold": self.stage_1_threshold,
            "stage_2_threshold": self.stage_2_threshold,
            "stage_3_threshold": self.stage_3_threshold,
            "min_amount_cents": self.min_amount_cents,
            "grace_days": self.grace_days,
            "max_notices_per_hour": self.max_notices_per_hour,
            "default_locale": self.default_locale,
            "template_version": self.template_version,
            "read_api_timeout": self.read_api_timeout,
            "read_api_base_url": self.read_api_base_url,
            "outbox_retry_attempts": self.outbox_retry_attempts,
            "outbox_retry_backoff_base": self.outbox_retry_backoff_base,
            "outbox_retry_backoff_max": self.outbox_retry_backoff_max,
            "stop_list_patterns": self.stop_list_patterns,
            "company_name": self.company_name,
            "company_address": self.company_address,
            "support_email": self.support_email,
        }
