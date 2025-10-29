"""Local overdue invoice providers for Mahnwesen Operate-Flows.

This module exposes an in-process provider that can be used to hydrate
the Mahnwesen playbook without relying on HTTP endpoints. The provider
creates deterministic `OverdueInvoice` instances based on local fixture
metadata so that Operate runs (Preview, Dry-Run, Live) remain stable and
repeatable during Canary executions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .dto import OverdueInvoice


@dataclass(frozen=True)
class FixtureInvoice:
    """Configuration describing how to synthesise an overdue invoice."""

    invoice_id: str
    invoice_number: str
    customer_email: str
    customer_name: str
    amount_cents: int
    due_date: datetime
    dunning_stage: int
    stage_hint: str
    source_path: Path


class LocalOverdueProvider:
    """In-process overdue provider backed by local fixture metadata.

    The provider loads fixture descriptors and converts them into
    `OverdueInvoice` DTOs that the Mahnwesen playbook can consume. This
    avoids the need for a running Read-API during Operate runs while
    still exercising the real rendering, approval and dispatch paths.
    """

    def __init__(self, fixtures: Iterable[FixtureInvoice] | None = None):
        self._fixtures = list(fixtures or _default_fixtures())

    def load_overdue_invoices(self, tenant_id: str, limit: int | None = None) -> list[OverdueInvoice]:
        """Return deterministic overdue invoices for the requested tenant."""

        invoices: list[OverdueInvoice] = []
        sent_keys = _load_sent_keys(tenant_id)

        for fx in self._fixtures:
            if limit is not None and len(invoices) >= limit:
                break

            idempotency_key = _compute_idempotency_key(tenant_id, fx.invoice_id, fx.dunning_stage)
            if idempotency_key in sent_keys:
                continue

            invoices.append(
                OverdueInvoice(
                    invoice_id=fx.invoice_id,
                    tenant_id=tenant_id,
                    invoice_number=fx.invoice_number,
                    due_date=fx.due_date,
                    amount_cents=fx.amount_cents,
                    customer_email=_mask_email(fx.customer_email),
                    customer_name=fx.customer_name,
                    customer_address=None,
                    created_at=datetime.now(UTC),
                    last_dunning_date=None,
                    dunning_stage=fx.dunning_stage,
                    metadata={
                        "source": str(fx.source_path),
                        "stage_hint": fx.stage_hint,
                        "fixture_version": "v1",
                    },
                )
            )

        return invoices


def _mask_email(email: str) -> str:
    """Mask the local part of an email while retaining determinism."""

    local, _, domain = email.partition("@")
    if not local or not domain:
        return "redacted@example.com"

    if len(local) <= 2:
        masked = "*" * len(local)
    else:
        masked = f"{local[0]}***{local[-1]}"

    return f"{masked}@{domain}"


def _default_fixtures() -> list[FixtureInvoice]:
    """Provide the canonical set of overdue fixtures for Operate runs."""

    base = Path("artifacts/inbox_local/samples")

    return [
        FixtureInvoice(
            invoice_id="INV-S1-001",
            invoice_number="INV-S1-001",
            customer_email="stage1-primary@example.com",
            customer_name="MVR Stage1 Primary",
            amount_cents=19990,
            due_date=datetime(2025, 10, 20, tzinfo=UTC),
            dunning_stage=1,
            stage_hint="stage_1",
            source_path=base / "invoice_good.json",
        ),
        FixtureInvoice(
            invoice_id="INV-S1-002",
            invoice_number="INV-S1-002",
            customer_email="stage1-secondary@example.com",
            customer_name="MVR Stage1 Secondary",
            amount_cents=25900,
            due_date=datetime(2025, 10, 22, tzinfo=UTC),
            dunning_stage=1,
            stage_hint="stage_1",
            source_path=base / "other_min.json",
        ),
        FixtureInvoice(
            invoice_id="INV-S2-001",
            invoice_number="INV-S2-001",
            customer_email="stage2@example.com",
            customer_name="MVR Stage2 Approval",
            amount_cents=54800,
            due_date=datetime(2025, 8, 31, tzinfo=UTC),
            dunning_stage=2,
            stage_hint="stage_2",
            source_path=base / "payment_good.json",
        ),
        FixtureInvoice(
            invoice_id="INV-S3-001",
            invoice_number="INV-S3-001",
            customer_email="stage3@example.com",
            customer_name="MVR Stage3 Escalation",
            amount_cents=129900,
            due_date=datetime(2025, 5, 30, tzinfo=UTC),
            dunning_stage=3,
            stage_hint="stage_3",
            source_path=base / "sample_result.json",
        ),
    ]


def _compute_idempotency_key(tenant_id: str, invoice_id: str, stage: int) -> str:
    normalized_tenant = tenant_id.strip().lower()
    normalized_invoice = invoice_id.strip().lower()
    canonical_key = f"{normalized_tenant}|{normalized_invoice}|{stage}"
    return hashlib.sha256(canonical_key.encode("utf-8")).hexdigest()


def _load_sent_keys(tenant_id: str) -> set[str]:
    path = Path("artifacts/reports/mahnwesen") / tenant_id / "outbox" / "sent.json"
    if not path.exists():
        return set()

    try:
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        return set(data.get("keys", []))
    except Exception:
        return set()


