from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.apps.inbox.importer.worker import run_importer
from backend.apps.inbox.read_model.query import (
    fetch_items_needing_review,
    fetch_payments_latest,
    fetch_tenant_summary,
)
from backend.core.config import settings

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = os.getenv("INBOX_DB_URL") or os.getenv("DATABASE_URL")
TENANT = "00000000-0000-0000-0000-000000000001"
SAMPLES = Path("artifacts/inbox_local/samples")

pytestmark = pytest.mark.skipif(
    not RUN_DB_TESTS or not DB_URL,
    reason="Set RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL for payment DB tests.",
)


def _ensure_inbox_ready(engine: Engine) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "ops/alembic")
    cfg.set_main_option("sqlalchemy.url", DB_URL)
    command.upgrade(cfg, "head")


def _truncate_inbox(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE inbox_parsed.parsed_item_chunks CASCADE"))
        conn.execute(text("TRUNCATE inbox_parsed.parsed_items CASCADE"))


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    engine = sa.create_engine(DB_URL, future=True)
    try:
        _ensure_inbox_ready(engine)
        settings.database_url = DB_URL
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _cleanup(engine: Engine) -> Iterator[None]:
    _truncate_inbox(engine)
    yield
    _truncate_inbox(engine)


def _sample(name: str) -> str:
    path = SAMPLES / name
    assert path.exists(), f"Sample artifact missing: {path}"
    return str(path)


def _fetch_item(engine: Engine, content_hash: str) -> dict:
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    """
                SELECT id, doctype, quality_status, confidence, payload, flags, mvr_preview, mvr_score
                FROM inbox_parsed.parsed_items
                WHERE tenant_id = :tenant AND content_hash = :content_hash
                """
                ),
                {"tenant": TENANT, "content_hash": content_hash},
            )
            .mappings()
            .first()
        )
        assert row, f"parsed item missing for {content_hash}"
        return dict(row)


def test_payment_import_and_read_model(engine: Engine) -> None:
    good_path = _sample("payment_good.json")
    bad_path = _sample("payment_bad.json")

    good_id = run_importer(
        tenant_id=TENANT,
        artifact_path=good_path,
        engine=engine,
        enforce_invoice=False,
        enforce_payment=True,
        enforce_other=True,
        replace_chunks=True,
    )

    # Idempotent re-run yields same ID
    second_id = run_importer(
        tenant_id=TENANT,
        artifact_path=good_path,
        engine=engine,
        enforce_invoice=False,
        enforce_payment=True,
        enforce_other=True,
        replace_chunks=True,
    )
    assert second_id == good_id

    good_row = _fetch_item(engine, "payment-good-0001")
    assert good_row["doctype"] == "payment"
    assert good_row["quality_status"] == "accepted"
    assert float(good_row["confidence"]) >= 80.0
    assert good_row["flags"].get("mvr_preview") is True
    assert good_row["mvr_preview"] is True
    assert str(good_row["mvr_score"]) in {"0", "0.00"}
    payment_payload = good_row["payload"]["extracted"]["payment"]
    assert payment_payload["currency"] == "EUR"

    payments = fetch_payments_latest(TENANT, limit=10, offset=0)
    assert any(
        p.content_hash == "payment-good-0001"
        and p.quality_status == "accepted"
        and p.flags.get("mvr_preview")
        and p.mvr_preview
        for p in payments
    )

    review_before = fetch_items_needing_review(TENANT, limit=10, offset=0)
    assert all(item.content_hash != "payment-good-0001" for item in review_before)

    bad_id = run_importer(
        tenant_id=TENANT,
        artifact_path=bad_path,
        engine=engine,
        enforce_invoice=False,
        enforce_payment=True,
        enforce_other=True,
        replace_chunks=True,
    )
    assert bad_id != good_id

    bad_row = _fetch_item(engine, "payment-bad-0001")
    assert bad_row["doctype"] == "payment"
    assert bad_row["quality_status"] == "rejected"
    assert bad_row["flags"].get("mvr_preview") is False

    payments_after = fetch_payments_latest(TENANT, limit=10, offset=0)
    assert any(
        p.content_hash == "payment-bad-0001" and p.quality_status == "rejected"
        for p in payments_after
    )

    review_after = fetch_items_needing_review(TENANT, limit=10, offset=0)
    assert any(item.content_hash == "payment-bad-0001" for item in review_after)

    summary = fetch_tenant_summary(TENANT)
    assert summary is not None
    assert summary.cnt_mvr_preview >= 1
    assert summary.avg_mvr_score is not None
