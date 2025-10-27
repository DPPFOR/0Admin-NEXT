from __future__ import annotations

import importlib.util

import pytest


def _load_mapping():
    spec_dto = importlib.util.spec_from_file_location("dto", "backend/apps/inbox/mapping/dto.py")
    dto_mod = importlib.util.module_from_spec(spec_dto)
    assert spec_dto and spec_dto.loader
    import sys as _sys

    _sys.modules[spec_dto.name] = dto_mod  # ensure visible to dataclasses
    spec_dto.loader.exec_module(dto_mod)  # type: ignore[union-attr]

    spec_map = importlib.util.spec_from_file_location(
        "report_to_dto", "backend/apps/inbox/mapping/report_to_dto.py"
    )
    map_mod = importlib.util.module_from_spec(spec_map)
    assert spec_map and spec_map.loader
    _sys.modules[spec_map.name] = map_mod
    spec_map.loader.exec_module(map_mod)  # type: ignore[union-attr]
    return dto_mod, map_mod


def test_report_to_dto_minimal():
    # create minimal flow result matching orchestrator output
    flow = {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "pipeline": ["pdf.text_extract", "data_quality.tables.validate", "security.pii.redact"],
        "extracted": {"tables": []},
        "quality": {"valid": True, "issues": []},
        "pii": {"steps": []},
        "fingerprints": {"content_hash": "0" * 64},
    }
    dto_mod, map_mod = _load_mapping()
    dto = map_mod.report_to_dto(flow)
    dto.validate()
    assert dto.tenant_id.endswith("1")
    assert dto.content_hash == "0" * 64
    assert dto.doc_type in {"unknown"}


def test_report_to_dto_negative():
    dto_mod, _ = _load_mapping()
    bad = dto_mod.InboxLocalFlowResultDTO(
        tenant_id="",
        content_hash="deadbeef",
        doc_type="invalid",
    )
    with pytest.raises(dto_mod.ValidationError):
        bad.validate()
