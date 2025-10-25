"""Tests for template composition - offline.

Tests the Jinja2 template rendering for dunning notices
without external dependencies.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from agents.mahnwesen.config import DunningConfig
from agents.mahnwesen.dto import DunningNotice, DunningStage, DunningChannel
from agents.mahnwesen.playbooks import TemplateEngine


class TestTemplateComposition:
    """Test template composition for dunning notices."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return DunningConfig(
            tenant_id="00000000-0000-0000-0000-000000000001",
            company_name="Test Company",
            company_address="Test Street 123, 12345 Test City",
            support_email="support@test.com"
        )
    
    @pytest.fixture
    def template_engine(self, config):
        """Create template engine."""
        return TemplateEngine(config)
    
    @pytest.fixture
    def sample_notice(self):
        """Create sample dunning notice."""
        return DunningNotice(
            notice_id="NOTICE-001",
            tenant_id="00000000-0000-0000-0000-000000000001",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            recipient_email="customer@example.com",
            recipient_name="Test Customer",
            due_date=datetime.now(timezone.utc) - timedelta(days=5),
            amount_cents=15000,  # 150.00 EUR
            dunning_fee_cents=250,  # 2.50 EUR
            total_amount_cents=15250,  # 152.50 EUR
            template_version="v1",
            locale="de-DE"
        )
    
    def test_stage_1_template_rendering(self, template_engine, sample_notice):
        """Test stage 1 template rendering."""
        notice = sample_notice
        notice.stage = DunningStage.STAGE_1
        
        rendered = template_engine.render_notice(notice, DunningStage.STAGE_1)
        
        # Check that content was rendered
        assert rendered.content
        assert rendered.subject
        
        # Check for key content elements
        assert "Zahlungserinnerung" in rendered.content
        assert notice.invoice_id in rendered.content
        assert "150.00" in rendered.content  # Amount
        assert "Test Company" in rendered.content  # Company name
        assert "support@test.com" in rendered.content  # Support email
    
    def test_stage_2_template_rendering(self, template_engine, sample_notice):
        """Test stage 2 template rendering."""
        notice = sample_notice
        notice.stage = DunningStage.STAGE_2
        notice.dunning_fee_cents = 500  # 5.00 EUR
        notice.total_amount_cents = 15500  # 155.00 EUR
        
        rendered = template_engine.render_notice(notice, DunningStage.STAGE_2)
        
        # Check that content was rendered
        assert rendered.content
        assert rendered.subject
        
        # Check for key content elements
        assert "2. Mahnung" in rendered.content
        assert notice.invoice_id in rendered.content
        assert "150.00" in rendered.content  # Original amount
        assert "5.00" in rendered.content  # Dunning fee
        assert "155.00" in rendered.content  # Total amount
        assert "7 Tagen" in rendered.content  # Payment deadline
    
    def test_stage_3_template_rendering(self, template_engine, sample_notice):
        """Test stage 3 template rendering."""
        notice = sample_notice
        notice.stage = DunningStage.STAGE_3
        notice.dunning_fee_cents = 1000  # 10.00 EUR
        notice.total_amount_cents = 16000  # 160.00 EUR
        
        rendered = template_engine.render_notice(notice, DunningStage.STAGE_3)
        
        # Check that content was rendered
        assert rendered.content
        assert rendered.subject
        
        # Check for key content elements
        assert "Letzte Mahnung" in rendered.content
        assert notice.invoice_id in rendered.content
        assert "150.00" in rendered.content  # Original amount
        assert "10.00" in rendered.content  # Dunning fee
        assert "160.00" in rendered.content  # Total amount
        assert "rechtliche Schritte" in rendered.content  # Legal notice
    
    def test_subject_extraction(self, template_engine, sample_notice):
        """Test subject line extraction."""
        notice = sample_notice
        
        rendered = template_engine.render_notice(notice, DunningStage.STAGE_1)
        
        # Check subject extraction
        assert rendered.subject
        assert "Zahlungserinnerung" in rendered.subject
        assert notice.invoice_id in rendered.subject
    
    def test_fallback_content(self, template_engine, sample_notice):
        """Test fallback content when template fails."""
        # Mock template failure by providing invalid template
        template_engine.templates = {"stage_1": "{{ invalid_template" }
        
        rendered = template_engine.render_notice(sample_notice, DunningStage.STAGE_1)
        
        # Should have fallback content
        assert rendered.content
        assert rendered.subject
        assert "Zahlungserinnerung" in rendered.content
        assert sample_notice.invoice_id in rendered.content
    
    def test_amount_formatting(self, template_engine, sample_notice):
        """Test amount formatting in templates."""
        notice = sample_notice
        notice.amount_cents = 123456  # 1234.56 EUR
        notice.dunning_fee_cents = 250  # 2.50 EUR
        notice.total_amount_cents = 123706  # 1237.06 EUR
        
        rendered = template_engine.render_notice(notice, DunningStage.STAGE_1)
        
        # Check amount formatting
        assert "1234.56" in rendered.content  # Original amount
        assert "2.50" in rendered.content  # Dunning fee
        assert "1237.06" in rendered.content  # Total amount
    
    def test_date_formatting(self, template_engine, sample_notice):
        """Test date formatting in templates."""
        notice = sample_notice
        notice.due_date = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        
        rendered = template_engine.render_notice(notice, DunningStage.STAGE_1)
        
        # Check date formatting (DD.MM.YYYY)
        assert "15.01.2024" in rendered.content
    
    def test_company_information(self, template_engine, sample_notice):
        """Test company information in templates."""
        rendered = template_engine.render_notice(sample_notice, DunningStage.STAGE_1)
        
        # Check company information
        assert "Test Company" in rendered.content
        assert "Test Street 123, 12345 Test City" in rendered.content
        assert "support@test.com" in rendered.content
    
    def test_recipient_information(self, template_engine, sample_notice):
        """Test recipient information in templates."""
        rendered = template_engine.render_notice(sample_notice, DunningStage.STAGE_1)
        
        # Check recipient information
        assert "customer@example.com" in rendered.content
        assert "Test Customer" in rendered.content
    
    def test_template_variables(self, template_engine, sample_notice):
        """Test template variable substitution."""
        # Test with specific values
        notice = sample_notice
        notice.invoice_id = "INV-TEST-123"
        notice.amount_cents = 50000  # 500.00 EUR
        notice.dunning_fee_cents = 750  # 7.50 EUR
        notice.total_amount_cents = 50750  # 507.50 EUR
        notice.due_date = datetime(2024, 3, 10, 0, 0, 0, tzinfo=timezone.utc)
        
        rendered = template_engine.render_notice(notice, DunningStage.STAGE_2)
        
        # Check variable substitution
        assert "INV-TEST-123" in rendered.content
        assert "500.00" in rendered.content
        assert "7.50" in rendered.content
        assert "507.50" in rendered.content
        assert "10.03.2024" in rendered.content
    
    def test_multiple_stages(self, template_engine, sample_notice):
        """Test template rendering for multiple stages."""
        stages = [
            (DunningStage.STAGE_1, "Zahlungserinnerung"),
            (DunningStage.STAGE_2, "2. Mahnung"),
            (DunningStage.STAGE_3, "Letzte Mahnung")
        ]
        
        for stage, expected_text in stages:
            notice = sample_notice
            notice.stage = stage
            
            rendered = template_engine.render_notice(notice, stage)
            
            # Check stage-specific content
            assert expected_text in rendered.content
            assert rendered.subject
            assert rendered.content
    
    def test_empty_optional_fields(self, template_engine):
        """Test template rendering with empty optional fields."""
        notice = DunningNotice(
            notice_id="NOTICE-002",
            tenant_id="00000000-0000-0000-0000-000000000001",
            invoice_id="INV-002",
            stage=DunningStage.STAGE_1,
            channel=DunningChannel.EMAIL,
            recipient_email=None,
            recipient_name=None,
            due_date=None,
            amount_cents=10000,
            dunning_fee_cents=250,
            total_amount_cents=10250
        )
        
        rendered = template_engine.render_notice(notice, DunningStage.STAGE_1)
        
        # Should still render successfully
        assert rendered.content
        assert rendered.subject
        assert notice.invoice_id in rendered.content
    
    def test_template_engine_initialization(self, config):
        """Test template engine initialization."""
        engine = TemplateEngine(config)
        
        # Check that templates are loaded
        assert hasattr(engine, 'templates')
        assert isinstance(engine.templates, dict)
        
        # Check for expected template keys
        expected_keys = ['stage_1', 'stage_2', 'stage_3']
        for key in expected_keys:
            assert key in engine.templates
    
    def test_config_integration(self, template_engine, sample_notice):
        """Test integration with configuration."""
        # Test with different config values
        template_engine.config.company_name = "Custom Company"
        template_engine.config.support_email = "custom@company.com"
        template_engine.config.company_address = "Custom Address"
        
        rendered = template_engine.render_notice(sample_notice, DunningStage.STAGE_1)
        
        # Check custom config values
        assert "Custom Company" in rendered.content
        assert "custom@company.com" in rendered.content
        assert "Custom Address" in rendered.content
    
    @pytest.mark.parametrize("stage,expected_keywords", [
        (DunningStage.STAGE_1, ["Zahlungserinnerung", "freundlich"]),
        (DunningStage.STAGE_2, ["2. Mahnung", "7 Tagen", "weitere Maßnahmen"]),
        (DunningStage.STAGE_3, ["Letzte Mahnung", "rechtliche Schritte", "7 Tagen"])
    ])
    def test_stage_specific_content(self, template_engine, sample_notice, stage, expected_keywords):
        """Test stage-specific content in templates."""
        notice = sample_notice
        notice.stage = stage
        
        rendered = template_engine.render_notice(notice, stage)
        
        # Check for stage-specific keywords
        for keyword in expected_keywords:
            assert keyword in rendered.content
