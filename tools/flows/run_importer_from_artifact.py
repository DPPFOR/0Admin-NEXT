#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util as _iu
import os
import sys
from pathlib import Path as _Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

_spec = _iu.spec_from_file_location(
    "importer_worker", str(_Path("backend/apps/inbox/importer/worker.py"))
)
_mod = _iu.module_from_spec(_spec)  # type: ignore[arg-type]
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run_importer = _mod.run_importer


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Import parsed_items from MCP artifact (local-only)")
    p.add_argument("--tenant", required=True)
    p.add_argument("--artifact", required=True)
    p.add_argument("--trace-id", default=None)
    p.add_argument("--dry-run", action="store_true", default=False)
    p.add_argument("--upsert", dest="upsert", action="store_true")
    p.add_argument("--no-upsert", dest="upsert", action="store_false")
    p.add_argument("--replace-chunks", action="store_true", default=False)
    p.add_argument("--enforce-invoice", dest="enforce_invoice", action="store_true")
    p.add_argument("--no-enforce-invoice", dest="enforce_invoice", action="store_false")
    p.add_argument("--enforce-payment", dest="enforce_payment", action="store_true")
    p.add_argument("--no-enforce-payment", dest="enforce_payment", action="store_false")
    p.add_argument("--enforce-other", dest="enforce_other", action="store_true")
    p.add_argument("--no-enforce-other", dest="enforce_other", action="store_false")
    p.add_argument("--strict", action="store_true", default=False)
    p.set_defaults(upsert=True)
    p.set_defaults(enforce_invoice=True)
    p.set_defaults(enforce_payment=True)
    p.set_defaults(enforce_other=True)
    args = p.parse_args(argv)
    try:
        res = run_importer(
            tenant_id=args.tenant,
            artifact_path=args.artifact,
            trace_id=args.trace_id,
            dry_run=args.dry_run,
            upsert=args.upsert,
            replace_chunks=args.replace_chunks,
            enforce_invoice=args.enforce_invoice,
            enforce_payment=args.enforce_payment,
            enforce_other=args.enforce_other,
            strict=args.strict,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 3
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
