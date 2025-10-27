"""Test configuration and fixtures for Mahnwesen agents.

Diese Tests benötigen den agents-Code und eine passende Umgebung. In CI ohne
die Agents-Komponente werden sie komplett übersprungen.
"""

import os
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

RUN_AGENTS_TESTS = os.getenv("RUN_AGENTS_TESTS") == "1"

try:
    from agents.mahnwesen.config import DunningConfig
    from agents.mahnwesen.playbooks import TemplateEngine
    from agents.mahnwesen.dto import DunningNotice, DunningStage, DunningChannel
except ModuleNotFoundError as exc:
    if not RUN_AGENTS_TESTS:
        pytest.skip("requires RUN_AGENTS_TESTS=1 and agents package", allow_module_level=True)
    raise


@pytest.fixture
def temp_template_dir(tmp_path):
    """Create isolated template directory for tests."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    
    # Copy default templates to temp directory
    default_templates = Path("agents/mahnwesen/templates/default")
    if default_templates.exists():
        shutil.copytree(default_templates, template_dir / "default")
    
    return template_dir


@pytest.fixture
def isolated_template_engine(temp_template_dir):
    """Create template engine with isolated template directory."""
    def _create_engine(config):
        # Patch the FileSystemLoader to use temp directory
        with patch('agents.mahnwesen.playbooks.FileSystemLoader') as mock_loader:
            mock_loader.return_value = None
            
            # Create engine with patched loader
            engine = TemplateEngine(config)
            
            # Manually set up the environment with temp directory
            from jinja2 import Environment, FileSystemLoader
            engine.env = Environment(
                loader=FileSystemLoader([
                    str(temp_template_dir / config.tenant_id),
                    str(temp_template_dir / "default")
                ]),
                undefined=engine.env.undefined,
                autoescape=engine.env.autoescape,
                trim_blocks=engine.env.trim_blocks,
                lstrip_blocks=engine.env.lstrip_blocks,
                cache_size=0
            )
            
            # Copy filters and globals
            engine.env.filters = engine.env.filters
            engine.env.globals = engine.env.globals
            
            return engine
    
    return _create_engine


@pytest.fixture
def test_config():
    """Test configuration with company_name set."""
    return DunningConfig(
        tenant_id="test-tenant",
        company_name="Test Company",
        company_address="Test Street 123, 12345 Test City",
        support_email="support@test.com"
    )


@pytest.fixture
def test_config_no_company():
    """Test configuration without company_name (tenant_name fallback)."""
    return DunningConfig(
        tenant_id="test-tenant",
        company_address="Test Street 123, 12345 Test City",
        support_email="support@test.com"
    )


@pytest.fixture
def sample_notice():
    """Create sample dunning notice."""
    return DunningNotice(
        notice_id="NOTICE-001",
        tenant_id="test-tenant",
        invoice_id="INV-001",
        stage=DunningStage.STAGE_1,
        channel=DunningChannel.EMAIL,
        amount_cents=5000,
        dunning_fee_cents=0,
        total_amount_cents=5000,
        customer_name="Test Customer",
        invoice_number="INV-001",
        due_date=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        recipient_email="customer@example.com",
        recipient_name="Test Customer"
    )
