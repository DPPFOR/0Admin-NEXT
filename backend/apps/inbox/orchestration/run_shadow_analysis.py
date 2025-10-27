from __future__ import annotations

import os

from backend.mcp.server.observability import get_logger


def _valid_relative_path(p: str) -> bool:
    return (
        isinstance(p, str)
        and p.startswith("artifacts/inbox/")
        and not p.startswith("/")
        and ".." not in p
    )


def run_shadow_analysis(
    *,
    tenant_id: str,
    trace_id: str,
    source_uri_or_path: str,
    content_sha256: str,
    inbox_item_id: str | None = None,
) -> str:
    """Validate path, run local inbox flow deterministically and return artifact path.

    Path guards:
    - must be relative
    - must start with artifacts/inbox/
    - must not contain '..'
    - must not be absolute
    Determinism toggle via TEST_FREEZE=1.
    """
    logger = get_logger("mcp")

    if not _valid_relative_path(source_uri_or_path):
        raise ValueError("invalid source path")

    # Determinism toggle for tests
    frozen = os.getenv("TEST_FREEZE") == "1"
    if frozen and not content_sha256:
        content_sha256 = "0" * 64

    logger.info(
        "mcp_shadow_analysis_start",
        extra={
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "inbox_item_id": inbox_item_id or "",
        },
    )

    # Lazy import by file path to avoid package import side-effects
    import importlib.util as _iu
    import pathlib as _pl

    _p = _pl.Path(__file__).parent / "inbox_local_flow.py"
    _spec = _iu.spec_from_file_location("inbox_local_flow", str(_p))
    _mod = _iu.module_from_spec(_spec)  # type: ignore[arg-type]
    assert _spec and _spec.loader
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    _run = _mod.run_inbox_local_flow

    # Delegate to the local flow; flags are markers only
    artifact_path = _run(
        tenant_id=tenant_id,
        path=source_uri_or_path,
        trace_id=trace_id,
        enable_ocr=False,
        enable_browser=False,
    )

    logger.info(
        "mcp_shadow_analysis_done",
        extra={
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "inbox_item_id": inbox_item_id or "",
            "mcp_artifact_path": artifact_path,
        },
    )
    return artifact_path
