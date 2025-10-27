from __future__ import annotations

import importlib
import os


def test_shadow_analysis_run_and_logs(monkeypatch, tmp_path):
    os.environ["TEST_FREEZE"] = "1"

    # Capture logs from MCP observability
    logs = []

    class _Logger:
        def info(self, name, extra=None):
            logs.append((name, dict(extra or {})))

        def warning(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

    def _fake_get_logger(name: str = "mcp"):
        return _Logger()

    monkeypatch.setenv("TEST_FREEZE", "1")
    mod_obs = importlib.import_module("backend.mcp.server.observability")
    monkeypatch.setattr(mod_obs, "get_logger", _fake_get_logger)

    import importlib.util as _iu

    spec = _iu.spec_from_file_location(
        "run_shadow_analysis", "backend/apps/inbox/orchestration/run_shadow_analysis.py"
    )
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    out = mod.run_shadow_analysis(
        tenant_id="00000000-0000-0000-0000-000000000001",
        trace_id="trace-x",
        source_uri_or_path="artifacts/inbox/samples/pdf/sample.pdf",
        content_sha256="",
        inbox_item_id="inbox-1",
    )
    assert out.startswith("artifacts/inbox_local/") and out.endswith("_result.json")
    names = [n for n, _ in logs]
    assert "mcp_shadow_analysis_start" in names and "mcp_shadow_analysis_done" in names
    done = [e for n, e in logs if n == "mcp_shadow_analysis_done"][0]
    assert done.get("tenant_id")
    assert done.get("mcp_artifact_path", "").startswith("artifacts/inbox_local/")
