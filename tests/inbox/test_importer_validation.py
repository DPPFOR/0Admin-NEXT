from __future__ import annotations

import json
import importlib.util as _iu
import pytest


def _load_worker():
    spec = _iu.spec_from_file_location(
        "worker", "backend/apps/inbox/importer/worker.py"
    )
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_validation_errors(monkeypatch):
    mod = _load_worker()
    bad = {"tenant_id": "wrong", "fingerprints": {}, "pipeline": [], "extracted": {}}
    p = "artifacts/inbox_local/samples/sample_result.json"
    # Write temp bad payload via monkeypatch open? Here we call validators directly by injecting json load
    import builtins

    class _FH:
        def __init__(self, data): self.data=data
        def read(self): return json.dumps(self.data)
        def __enter__(self): return self
        def __exit__(self,*a): return False

    def _fake_open(path, mode='r', encoding=None):
        assert path == p
        return _FH(bad)

    import builtins as _bi
    monkeypatch.setattr(_bi, "open", _fake_open)
    with pytest.raises(ValueError):
        mod.run_importer(tenant_id="00000000-0000-0000-0000-000000000001", artifact_path=p)

def test_dry_run(monkeypatch):
    mod = _load_worker()
    p = "artifacts/inbox_local/samples/sample_result.json"
    res = mod.run_importer(
        tenant_id="00000000-0000-0000-0000-000000000001",
        artifact_path=p,
        dry_run=True,
    )
    assert res == "planned"
