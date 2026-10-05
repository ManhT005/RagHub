"""One-off: delete duplicate eval docs, keep newest READY per filename.

Usage (from backend/):
    python scripts/dedup_eval_docs.py --mint-email you@example.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_production_eval import api, ensure_org, mint_token  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mint-email", required=True)
    args = ap.parse_args()
    token = mint_token(args.mint_email)
    org = ensure_org(token)
    _, items = api("GET", "/workspaces", token, org)
    ws = next(w["id"] for w in items if w.get("slug") == "golden-test")
    _, docs = api("GET", f"/workspaces/{ws}/documents", token, org)
    by_name: dict[str, list] = {}
    for d in docs or []:
        by_name.setdefault(d.get("name", ""), []).append(d)
    removed = 0
    for name, rows in sorted(by_name.items()):
        rows.sort(key=lambda d: d.get("created_at", ""), reverse=True)
        keep = next((r for r in rows if r.get("status") == "READY"), rows[0])
        for r in rows:
            if r["id"] == keep["id"]:
                continue
            st, _ = api("DELETE", f"/workspaces/{ws}/documents/{r['id']}", token, org, None)
            print(f"delete {name} {r['id'][:8]} ({r.get('status')}): {st}", flush=True)
            removed += 1
    print(f"removed {removed} duplicates")


if __name__ == "__main__":
    main()
