"""Tests for template contract and rendering."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from agents.mahnwesen.config import DunningConfig
from agents.mahnwesen.dto import DunningNotice, DunningStage
from agents.mahnwesen.playbooks import TemplateEngine


@pytest.fixture
def test_config():
    """Test configuration."""
    return DunningConfig(
        tenant_id="test-tenant",
        company_name="Test Company",
        company_address="Test Street 123, 12345 Test City",
        support_email="support@test.com",
    )


@pytest.fixture
def sample_notice():
    """Sample dunning notice."""
    return DunningNotice(
        notice_id="NOTICE-001",
        tenant_id="test-tenant",
        invoice_id="INV-001",
        stage=DunningStage.STAGE_1,
        channel="email",
        recipient_email="customer@example.com",
        recipient_name="Test Customer",
        due_date="2025-01-15",
        amount_cents=5000,
        dunning_fee_cents=0,
        total_amount_cents=5000,
        customer_name="Test Customer",
        invoice_number="INV-001",
        content="",
        subject="",
    )


class TestTemplateContract:
    """Test template contract and rendering."""

    def test_template_engine_initialization(self, test_config):
        """Test template engine initialization."""
        engine = TemplateEngine(test_config)

        assert engine.config == test_config
        assert engine.env is not None
        assert engine.templates is not None

    def test_template_loading_fallback(self, test_config):
        """Test template loading with fallback templates."""
        engine = TemplateEngine(test_config)

        # Should have fallback templates
        assert "stage_1" in engine.templates
        assert "stage_2" in engine.templates
        assert "stage_3" in engine.templates

        # Templates should contain basic content
        assert (
            "Zahlungserinnerung" in engine.templates["stage_1"]
            or "Test Template" in engine.templates["stage_1"]
        )
        assert (
            "2. Mahnung" in engine.templates["stage_2"]
            or "Test Template" in engine.templates["stage_2"]
        )
        assert (
            "Letzte Mahnung" in engine.templates["stage_3"]
            or "Test Template" in engine.templates["stage_3"]
        )

    def test_render_notice_stage_1(self, test_config, sample_notice):
        """Test rendering stage 1 notice."""
        engine = TemplateEngine(test_config)

        rendered = engine.render_notice(sample_notice, DunningStage.STAGE_1)

        # Verify required fields are present
        assert rendered.content is not None
        assert rendered.subject is not None

        # Verify content contains expected elements
        content = rendered.content
        assert "Test Customer" in content
        assert "INV-001" in content
        assert "50.00" in content  # amount_str
        assert "2025-01-15" in content  # due_date_iso
        assert "Test Company" in content  # company_name (from config)

    def test_render_notice_stage_2(self, test_config, sample_notice):
        """Test rendering stage 2 notice."""
        engine = TemplateEngine(test_config)

        rendered = engine.render_notice(sample_notice, DunningStage.STAGE_2)

        # Verify content contains stage 2 specific text
        assert "2. Mahnung" in rendered.content
        assert "rechtliche Schritte" in rendered.content

    def test_render_notice_stage_3(self, test_config, sample_notice):
        """Test rendering stage 3 notice."""
        engine = TemplateEngine(test_config)

        rendered = engine.render_notice(sample_notice, DunningStage.STAGE_3)

        # Verify content contains stage 3 specific text
        assert "Letzte Mahnung" in rendered.content
        assert "Inkassobüro" in rendered.content
        assert "7 Tagen" in rendered.content

    def test_render_notice_with_dunning_fee(self, test_config, sample_notice):
        """Test rendering notice with dunning fee."""
        sample_notice.dunning_fee_cents = 500  # 5 EUR fee

        engine = TemplateEngine(test_config)
        rendered = engine.render_notice(sample_notice, DunningStage.STAGE_1)

        # Verify fee is included in context
        assert "5.00" in rendered.content  # fee amount

    def test_render_notice_missing_fields(self, test_config):
        """Test rendering with missing fields."""
        # Create notice with minimal data
        notice = DunningNotice(
            notice_id="NOTICE-002",
            tenant_id="test-tenant",
            invoice_id="INV-002",
            stage=DunningStage.STAGE_1,
            channel="email",
            recipient_email="customer@example.com",
            recipient_name="Test Customer",
            due_date=None,
            amount_cents=3000,
            dunning_fee_cents=0,
            total_amount_cents=3000,
            customer_name="Test Customer",
            invoice_number="INV-002",
            content="",
            subject="",
        )

        engine = TemplateEngine(test_config)
        rendered = engine.render_notice(notice, DunningStage.STAGE_1)

        # Should handle missing fields gracefully
        assert rendered.content is not None
        assert rendered.subject is not None
        assert "INV-002" in rendered.content

    def test_subject_extraction(self, test_config, sample_notice):
        """Test subject extraction from content."""
        engine = TemplateEngine(test_config)
        rendered = engine.render_notice(sample_notice, DunningStage.STAGE_1)

        # Should extract subject from Betreff: line
        assert rendered.subject is not None
        assert "Zahlungserinnerung" in rendered.subject
        assert "INV-001" in rendered.subject

    def test_template_context_variables(self, test_config, sample_notice):
        """Test that all required context variables are available."""
        engine = TemplateEngine(test_config)

        # Mock template to capture context
        with patch.object(engine.env, "get_template") as mock_template:
            mock_template.return_value.render = Mock(return_value="Test Content")

            engine.render_notice(sample_notice, DunningStage.STAGE_1)

            # Verify template was called with correct context
            mock_template.assert_called_once()
            render_call = mock_template.return_value.render.call_args[1]

            # Check required variables are present
            assert "config" in render_call
            assert "notice" in render_call
            assert "stage" in render_call
            assert "tenant_name" in render_call
            assert "customer_name" in render_call
            assert "invoice_number" in render_call
            assert "due_date_iso" in render_call
            assert "amount_str" in render_call
            assert "fee" in render_call

    def test_template_error_handling(self, test_config, sample_notice):
        """Test template error handling - should fail hard, no fallback."""
        engine = TemplateEngine(test_config)

        # Mock template to raise exception
        with patch.object(engine.env, "get_template") as mock_template:
            mock_template.side_effect = Exception("Template Error")

            # Should raise FileNotFoundError, NO fallback content
            with pytest.raises(FileNotFoundError) as exc_info:
                engine.render_notice(sample_notice, DunningStage.STAGE_1)

            # Error message should mention template name and paths
            error_msg = str(exc_info.value)
            assert "stage_1.jinja.txt" in error_msg
            assert "test-tenant" in error_msg
            assert "agents/mahnwesen/templates" in error_msg

    def test_template_file_loading(self, test_config, isolated_template_engine):
        """Test template loading from files with isolation."""
        # Create isolated template engine
        engine = isolated_template_engine(test_config)

        # Write test template to isolated directory
        temp_dir = Path(engine.env.loader.searchpath[1])  # default directory
        temp_dir.mkdir(parents=True, exist_ok=True)
        stage_1_template = temp_dir / "stage_1.jinja.txt"
        stage_1_template.write_text("Test Template: {{ customer_name }} - {{ invoice_number }}")

        # Should load from isolated file
        template = engine.env.get_template("stage_1.jinja.txt")
        assert template.filename == str(stage_1_template)

    def test_template_rendering_with_unicode(self, test_config, sample_notice):
        """Test template rendering with Unicode characters."""
        sample_notice.customer_name = "Müller & Söhne GmbH"
        sample_notice.invoice_number = "R-2025-001"

        engine = TemplateEngine(test_config)
        rendered = engine.render_notice(sample_notice, DunningStage.STAGE_1)

        # Should handle Unicode correctly
        assert "Müller & Söhne GmbH" in rendered.content
        assert "R-2025-001" in rendered.content
        assert rendered.content is not None
        assert rendered.subject is not None
