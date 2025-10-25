"""Tests for MVR Approval System (4-Augen-Prinzip)."""

import pytest
from datetime import datetime, timezone

from agents.mahnwesen.mvr_approval import (
    MVRApprovalEngine,
    ApprovalRequest,
    ApprovalStatus
)
from agents.mahnwesen.dto import DunningStage


class TestMVRApprovalEngine:
    """Test MVR approval engine for 4-Augen-Prinzip."""
    
    def test_requires_approval_stage_1_optional(self):
        """Test that Stage 1 approval is optional by default."""
        engine = MVRApprovalEngine(require_approval_s1=False)
        
        assert not engine.requires_approval(DunningStage.STAGE_1)
        assert engine.requires_approval(DunningStage.STAGE_2)
        assert engine.requires_approval(DunningStage.STAGE_3)
    
    def test_requires_approval_stage_1_mandatory(self):
        """Test that Stage 1 can be made mandatory."""
        engine = MVRApprovalEngine(require_approval_s1=True)
        
        assert engine.requires_approval(DunningStage.STAGE_1)
        assert engine.requires_approval(DunningStage.STAGE_2)
        assert engine.requires_approval(DunningStage.STAGE_3)
    
    def test_create_approval_request(self):
        """Test creating an approval request."""
        engine = MVRApprovalEngine()
        
        request = engine.create_approval_request(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_2,
            requester="user1"
        )
        
        assert request.tenant_id == "tenant-1"
        assert request.notice_id == "NOTICE-001"
        assert request.invoice_id == "INV-001"
        assert request.stage == DunningStage.STAGE_2
        assert request.status == ApprovalStatus.PENDING
        assert request.requester == "user1"
        assert request.approver is None
        assert request.created_at is not None
    
    def test_approve_success(self):
        """Test successful approval with 4-Augen-Prinzip."""
        engine = MVRApprovalEngine()
        
        # Create request
        request = engine.create_approval_request(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_2,
            requester="user1"
        )
        
        # Approve with different user
        approved = engine.approve(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            stage=DunningStage.STAGE_2,
            approver="user2",
            comment="Approved for sending"
        )
        
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.approver == "user2"
        assert approved.comment == "Approved for sending"
        assert approved.approved_at is not None
        assert engine.is_approved("tenant-1", "NOTICE-001", DunningStage.STAGE_2)
    
    def test_approve_same_user_fails(self):
        """Test that approval fails when approver = requester (4-Augen violation)."""
        engine = MVRApprovalEngine()
        
        # Create request
        engine.create_approval_request(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_2,
            requester="user1"
        )
        
        # Try to approve with same user
        with pytest.raises(ValueError) as exc_info:
            engine.approve(
                tenant_id="tenant-1",
                notice_id="NOTICE-001",
                stage=DunningStage.STAGE_2,
                approver="user1",  # Same as requester
                comment="Self-approval attempt"
            )
        
        assert "4-Augen-Prinzip verletzt" in str(exc_info.value)
        assert not engine.is_approved("tenant-1", "NOTICE-001", DunningStage.STAGE_2)
    
    def test_reject(self):
        """Test rejection of approval request."""
        engine = MVRApprovalEngine()
        
        # Create request
        engine.create_approval_request(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_2,
            requester="user1"
        )
        
        # Reject
        rejected = engine.reject(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            stage=DunningStage.STAGE_2,
            approver="user2",
            comment="Customer already paid"
        )
        
        assert rejected.status == ApprovalStatus.REJECTED
        assert rejected.approver == "user2"
        assert rejected.comment == "Customer already paid"
        assert not engine.is_approved("tenant-1", "NOTICE-001", DunningStage.STAGE_2)
    
    def test_can_send_stage_1_no_approval_required(self):
        """Test that Stage 1 can send without approval by default."""
        engine = MVRApprovalEngine(require_approval_s1=False)
        
        can_send, reason = engine.can_send("tenant-1", "NOTICE-001", DunningStage.STAGE_1)
        
        assert can_send
        assert reason is None
    
    def test_can_send_stage_2_without_approval_blocked(self):
        """Test that Stage 2 is blocked without approval."""
        engine = MVRApprovalEngine()
        
        can_send, reason = engine.can_send("tenant-1", "NOTICE-001", DunningStage.STAGE_2)
        
        assert not can_send
        assert "requires approval" in reason
        assert "4-Augen-Prinzip" in reason
    
    def test_can_send_stage_2_with_approval_allowed(self):
        """Test that Stage 2 can send after approval."""
        engine = MVRApprovalEngine()
        
        # Create and approve
        engine.create_approval_request(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_2,
            requester="user1"
        )
        engine.approve(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            stage=DunningStage.STAGE_2,
            approver="user2",
            comment="OK"
        )
        
        can_send, reason = engine.can_send("tenant-1", "NOTICE-001", DunningStage.STAGE_2)
        
        assert can_send
        assert reason is None
    
    def test_get_pending_approvals(self):
        """Test retrieving pending approvals for a tenant."""
        engine = MVRApprovalEngine()
        
        # Create multiple requests
        engine.create_approval_request(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            invoice_id="INV-001",
            stage=DunningStage.STAGE_2,
            requester="user1"
        )
        engine.create_approval_request(
            tenant_id="tenant-1",
            notice_id="NOTICE-002",
            invoice_id="INV-002",
            stage=DunningStage.STAGE_3,
            requester="user1"
        )
        engine.create_approval_request(
            tenant_id="tenant-2",
            notice_id="NOTICE-003",
            invoice_id="INV-003",
            stage=DunningStage.STAGE_2,
            requester="user1"
        )
        
        # Approve one
        engine.approve(
            tenant_id="tenant-1",
            notice_id="NOTICE-001",
            stage=DunningStage.STAGE_2,
            approver="user2",
            comment="OK"
        )
        
        # Get pending for tenant-1
        pending = engine.get_pending_approvals("tenant-1")
        
        assert len(pending) == 1
        assert pending[0].notice_id == "NOTICE-002"
        assert pending[0].status == ApprovalStatus.PENDING

