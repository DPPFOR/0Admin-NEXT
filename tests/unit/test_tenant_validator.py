import json

from backend.core.tenant.validator import TenantAllowlistLoader


def test_env_allowlist(tmp_path, monkeypatch):
    t1 = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setenv("TENANT_ALLOWLIST", t1)
    loader = TenantAllowlistLoader()
    assert loader.validate(t1).ok
    assert not loader.validate("bad-uuid").ok
    assert loader.validate(None).reason == "missing"


def test_file_allowlist_json(tmp_path, monkeypatch):
    t1 = "22222222-2222-2222-2222-222222222222"
    p = tmp_path / "tenants.json"
    p.write_text(json.dumps([t1]))
    monkeypatch.setenv("TENANT_ALLOWLIST_PATH", str(p))
    loader = TenantAllowlistLoader()
    assert loader.validate(t1).ok


def test_reload_env(monkeypatch):
    t1 = "33333333-3333-3333-3333-333333333333"
    monkeypatch.setenv("TENANT_ALLOWLIST", t1)
    monkeypatch.setenv("TENANT_ALLOWLIST_REFRESH_SEC", "0")
    loader = TenantAllowlistLoader()
    assert loader.validate(t1).ok
