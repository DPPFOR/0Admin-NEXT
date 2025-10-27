from __future__ import annotations

import importlib.util as _iu
import json


def _load_mapper():
    spec = _iu.spec_from_file_location("mapper", "backend/apps/inbox/importer/mapper.py")
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _load_validators():
    spec = _iu.spec_from_file_location("validators", "backend/apps/inbox/importer/validators.py")
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_mapping_from_sample_artifact():
    data = json.loads(
        open("artifacts/inbox_local/samples/sample_result.json", encoding="utf-8").read()
    )
    mapper = _load_mapper()
    validators = _load_validators()
    item, chunks = mapper.artifact_to_dtos(data)
    assert item.tenant_id.endswith("1")
    assert isinstance(item.payload, dict)
    assert item.content_hash != ""
    assert item.doc_type == "pdf"
    assert item.quality_flags == []
    assert item.amount is None
    assert item.due_date is None
    assert all(c.kind == "table" for c in chunks)
    # Validate table shapes
    validators.validate_tables_shape(data.get("extracted", {}).get("tables", []))
