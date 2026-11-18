"""CLI: python -m engine run --batch X.csv --policy P.json [--pin V] [--as-of D] [--out out.csv]
        python -m engine validate P.json"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from . import load_batch, load_master, load_policy, rows_to_csv, run_batch, validate
from .paths import BACKEND_DIR, kit_root


def _cmd_run(args) -> int:
    master = load_master(args.data_root, args.pdf_contracts)
    policies = [load_policy(p) for p in args.policy]
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    result = run_batch(load_batch(Path(args.batch)), master, policies, pin=args.pin, as_of=as_of)
    text = rows_to_csv(result.rows)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="")
    else:
        sys.stdout.write(text)
    summary = {
        "rows": len(result.rows),
        "requirements": len(result.requirements),
        "pos": len({r.po_id for r in result.rows if r.po_id}),
        "rows_by_route": dict(sorted(result.counts.items())),
        "requirements_by_route": dict(sorted(result.requirement_counts.items())),
        "versions_used": result.versions_used,
    }
    print(json.dumps(summary, indent=2), file=sys.stderr)
    return 0


def _cmd_validate(args) -> int:
    doc = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    base = json.loads(Path(args.base).read_text(encoding="utf-8")) if args.base else None
    res = validate(doc, base)
    for e in res.errors:
        print(f"ERROR   {e}")
    for w in res.warnings:
        print(f"WARNING {w}")
    print(f"{len(res.errors)} errors, {len(res.warnings)} warnings")
    return 1 if res.errors else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="process a PR batch CSV")
    r.add_argument("--batch", required=True)
    r.add_argument("--policy", action="append", required=True, help="policy JSON (repeatable)")
    r.add_argument("--pin")
    r.add_argument("--as-of")
    r.add_argument("--out")
    r.add_argument("--data-root", default=str(kit_root()))
    r.add_argument("--pdf-contracts", default=str(BACKEND_DIR / "seed" / "pdf_contracts.json"))
    r.set_defaults(fn=_cmd_run)
    v = sub.add_parser("validate", help="validate a policy JSON")
    v.add_argument("policy")
    v.add_argument("--base")
    v.set_defaults(fn=_cmd_validate)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
