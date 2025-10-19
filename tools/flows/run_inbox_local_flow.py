#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

# Ensure project root on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import importlib.util as _iu


def _load_runner():
    spec = _iu.spec_from_file_location(
        "inbox_local_flow",
        os.path.join("backend", "apps", "inbox", "orchestration", "inbox_local_flow.py"),
    )
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.run_inbox_local_flow


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run Inbox Local Flow (read-only)")
    p.add_argument("--tenant", required=True, help="Tenant UUID")
    p.add_argument("--path", required=True, help="Local file under artifacts/inbox/")
    p.add_argument("--enable-ocr", action="store_true", default=False)
    p.add_argument("--enable-browser", action="store_true", default=False)
    p.add_argument("--trace-id", default=None)
    args = p.parse_args(argv)

    try:
        run_flow = _load_runner()
        out_path = run_flow(
            tenant_id=args.tenant,
            path=args.path,
            trace_id=args.trace_id,
            enable_ocr=args.enable_ocr,
            enable_browser=args.enable_browser,
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
