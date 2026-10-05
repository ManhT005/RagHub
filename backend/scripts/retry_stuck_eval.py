"""One-off: retry stuck FAILED versions in the eval workspace, then exit.

Usage (from backend/):
    python scripts/retry_stuck_eval.py --mint-email you@example.com
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
    n = 0
    for d in docs or []:
        if d.get("status") == "FAILED":
            vid = d.get("document_version_id")
            st, body = api(
                "POST", f"/workspaces/{ws}/document-versions/{vid}/retry", token, org, {}
            )
            print(f"retry {d.get('name')} ({d.get('error_code')}): {st}", flush=True)
            n += 1
    print(f"retried {n} versions")


if __name__ == "__main__":
    main()
