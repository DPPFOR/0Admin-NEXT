"""MVR Approval System - 4-Augen-Prinzip für Mahnwesen.

Implementiert die 4-Augen-Kontrolle (Dual Authorization) für Mahnstufen 2 und 3.
Stufe 1 ist optional freigabepflichtig.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from .dto import DunningStage


class ApprovalStatus(Enum):
    """Status einer Freigabe."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ApprovalRequest:
    """Freigabeanfrage für eine Mahnung."""

    tenant_id: str
    notice_id: str
    invoice_id: str
    stage: DunningStage
    status: ApprovalStatus
    requester: str
    approver: str | None = None
    comment: str | None = None
    created_at: datetime | None = None
    approved_at: datetime | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)


class MVRApprovalEngine:
    """Engine für 4-Augen-Freigabe von Mahnungen.

    Regeln:
    - Stage 1: Optional (konfigurierbar)
    - Stage 2: Pflicht
    - Stage 3: Pflicht
    """

    def __init__(self, require_approval_s1: bool = False):
        """Initialize approval engine.

        Args:
            require_approval_s1: Wenn True, erfordert auch S1 eine Freigabe
        """
        self.logger = logging.getLogger(__name__)
        self.require_approval_s1 = require_approval_s1

        # In-memory approval state (in production: Redis/DB)
        self._approvals: dict[str, ApprovalRequest] = {}

    def requires_approval(self, stage: DunningStage) -> bool:
        """Prüft, ob eine Stufe eine Freigabe erfordert.

        Args:
            stage: Mahnstufe

        Returns:
            True wenn Freigabe erforderlich
        """
        if stage == DunningStage.STAGE_1:
            return self.require_approval_s1
        elif stage in (DunningStage.STAGE_2, DunningStage.STAGE_3):
            return True
        return False

    def create_approval_request(
        self, tenant_id: str, notice_id: str, invoice_id: str, stage: DunningStage, requester: str
    ) -> ApprovalRequest:
        """Erstellt eine neue Freigabeanfrage.

        Args:
            tenant_id: Tenant-ID
            notice_id: Notice-ID
            invoice_id: Rechnungs-ID
            stage: Mahnstufe
            requester: Anfordernder Benutzer

        Returns:
            Neue Freigabeanfrage
        """
        request = ApprovalRequest(
            tenant_id=tenant_id,
            notice_id=notice_id,
            invoice_id=invoice_id,
            stage=stage,
            status=ApprovalStatus.PENDING,
            requester=requester,
        )

        # Speichern
        key = self._get_approval_key(tenant_id, notice_id, stage)
        self._approvals[key] = request

        self.logger.info(
            "Approval request created",
            extra={
                "tenant_id": tenant_id,
                "notice_id": notice_id,
                "stage": stage.value,
                "requester": requester,
            },
        )

        return request

    def approve(
        self, tenant_id: str, notice_id: str, stage: DunningStage, approver: str, comment: str
    ) -> ApprovalRequest:
        """Genehmigt eine Freigabeanfrage.

        Args:
            tenant_id: Tenant-ID
            notice_id: Notice-ID
            stage: Mahnstufe
            approver: Genehmigender Benutzer
            comment: Pflichtkommentar

        Returns:
            Aktualisierte Freigabeanfrage

        Raises:
            ValueError: Wenn keine Anfrage existiert oder Approver = Requester
        """
        key = self._get_approval_key(tenant_id, notice_id, stage)

        if key not in self._approvals:
            raise ValueError(f"No approval request found for {notice_id}")

        request = self._approvals[key]

        # 4-Augen-Prinzip: Approver != Requester
        if approver == request.requester:
            raise ValueError(
                f"4-Augen-Prinzip verletzt: Approver ({approver}) darf nicht "
                f"gleich Requester ({request.requester}) sein"
            )

        # Aktualisieren
        request.status = ApprovalStatus.APPROVED
        request.approver = approver
        request.comment = comment
        request.approved_at = datetime.now(UTC)

        self.logger.info(
            "Approval granted",
            extra={
                "tenant_id": tenant_id,
                "notice_id": notice_id,
                "stage": stage.value,
                "approver": approver,
            },
        )

        return request

    def reject(
        self, tenant_id: str, notice_id: str, stage: DunningStage, approver: str, comment: str
    ) -> ApprovalRequest:
        """Lehnt eine Freigabeanfrage ab.

        Args:
            tenant_id: Tenant-ID
            notice_id: Notice-ID
            stage: Mahnstufe
            approver: Ablehnender Benutzer
            comment: Pflichtkommentar

        Returns:
            Aktualisierte Freigabeanfrage

        Raises:
            ValueError: Wenn keine Anfrage existiert
        """
        key = self._get_approval_key(tenant_id, notice_id, stage)

        if key not in self._approvals:
            raise ValueError(f"No approval request found for {notice_id}")

        request = self._approvals[key]

        # Aktualisieren
        request.status = ApprovalStatus.REJECTED
        request.approver = approver
        request.comment = comment
        request.approved_at = datetime.now(UTC)

        self.logger.info(
            "Approval rejected",
            extra={
                "tenant_id": tenant_id,
                "notice_id": notice_id,
                "stage": stage.value,
                "approver": approver,
                "reason": comment,
            },
        )

        return request

    def is_approved(self, tenant_id: str, notice_id: str, stage: DunningStage) -> bool:
        """Prüft, ob eine Notice genehmigt wurde.

        Args:
            tenant_id: Tenant-ID
            notice_id: Notice-ID
            stage: Mahnstufe

        Returns:
            True wenn genehmigt
        """
        key = self._get_approval_key(tenant_id, notice_id, stage)

        if key not in self._approvals:
            return False

        return self._approvals[key].status == ApprovalStatus.APPROVED

    def can_send(
        self, tenant_id: str, notice_id: str, stage: DunningStage
    ) -> tuple[bool, str | None]:
        """Prüft, ob eine Notice versendet werden darf.

        Args:
            tenant_id: Tenant-ID
            notice_id: Notice-ID
            stage: Mahnstufe

        Returns:
            Tuple (erlaubt, Fehlergrund)
        """
        # Stage 1: Immer erlaubt wenn keine Freigabe erforderlich
        if not self.requires_approval(stage):
            return True, None

        # Stage 2/3: Freigabe erforderlich
        if not self.is_approved(tenant_id, notice_id, stage):
            return False, (
                f"Notice {notice_id} (Stage {stage.value}) requires approval "
                f"(4-Augen-Prinzip). Use --approve before --live."
            )

        return True, None

    def _get_approval_key(self, tenant_id: str, notice_id: str, stage: DunningStage) -> str:
        """Erzeugt eindeutigen Schlüssel für Approval.

        Args:
            tenant_id: Tenant-ID
            notice_id: Notice-ID
            stage: Mahnstufe

        Returns:
            Approval-Key
        """
        key_data = f"{tenant_id}|{notice_id}|{stage.value}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def get_pending_approvals(self, tenant_id: str) -> list[ApprovalRequest]:
        """Holt alle ausstehenden Freigabeanfragen für einen Tenant.

        Args:
            tenant_id: Tenant-ID

        Returns:
            Liste der ausstehenden Anfragen
        """
        return [
            req
            for req in self._approvals.values()
            if req.tenant_id == tenant_id and req.status == ApprovalStatus.PENDING
        ]
