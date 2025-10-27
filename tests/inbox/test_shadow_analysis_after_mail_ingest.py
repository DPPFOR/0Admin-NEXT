from __future__ import annotations

import importlib.util as _iu
import os


def test_shadow_analysis_mail_path_guards(monkeypatch):
    os.environ["TEST_FREEZE"] = "1"
    spec = _iu.spec_from_file_location(
        "run_shadow_analysis", "backend/apps/inbox/orchestration/run_shadow_analysis.py"
    )
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    # invalid path: absolute
    try:
        mod.run_shadow_analysis(
            tenant_id="t", trace_id="x", source_uri_or_path="/abs/path.pdf", content_sha256=""
        )
        assert False, "expected ValueError"
    except ValueError:
        pass
    # invalid traversal
    try:
        mod.run_shadow_analysis(
            tenant_id="t",
            trace_id="x",
            source_uri_or_path="artifacts/inbox/../../etc/passwd",
            content_sha256="",
        )
        assert False, "expected ValueError"
    except ValueError:
        pass
    # valid
    out = mod.run_shadow_analysis(
        tenant_id="t",
        trace_id="x",
        source_uri_or_path="artifacts/inbox/samples/images/sample.png",
        content_sha256="",
    )
    assert out.startswith("artifacts/inbox_local/")
