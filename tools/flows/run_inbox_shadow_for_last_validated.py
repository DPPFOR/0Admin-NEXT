#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import importlib.util as _iu
from pathlib import Path as _Path

_spec = _iu.spec_from_file_location(
    "run_shadow_analysis", str(_Path("backend/apps/inbox/orchestration/run_shadow_analysis.py"))
)
_mod = _iu.module_from_spec(_spec)  # type: ignore[arg-type]
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run_shadow_analysis = _mod.run_shadow_analysis


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run MCP shadow analysis (local-only)")
    p.add_argument("--tenant", required=True)
    p.add_argument("--path", default="artifacts/inbox/samples/pdf/sample_a.pdf")
    p.add_argument("--trace-id", default="00000000-0000-0000-0000-000000000000")
    args = p.parse_args(argv)
    try:
        out = run_shadow_analysis(
            tenant_id=args.tenant,
            trace_id=args.trace_id,
            source_uri_or_path=args.path,
            content_sha256="",
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
