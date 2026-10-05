"""One-off: collect fused scores for calibration/holdout splits via search API.

Usage (from backend/):
    python scripts/collect_calibration_scores.py --mint-email you@example.com
Writes artifacts/calib_scores.json with rows per split.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_production_eval import GOLDEN, api, ensure_org, mint_token  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mint-email", required=True)
    ap.add_argument("--out", default="../artifacts/calib_scores.json")
    args = ap.parse_args()
    token = mint_token(args.mint_email)
    org = ensure_org(token)
    _, items = api("GET", "/workspaces", token, org)
    ws = next(w["id"] for w in items if w.get("slug") == "golden-test")
    qa = json.loads((GOLDEN / "qa.json").read_text(encoding="utf-8"))
    rows = {"calibration": [], "holdout": []}
    for case in qa:
        split = case.get("split", "calibration")
        q = case["question"]
        s, search = api(
            "GET", f"/workspaces/{ws}/search?q={urllib.parse.quote(q)}&limit=5", token, org
        )
        scores = [h.get("score", 0.0) for h in search.get("hits", [])] if s == 200 else []
        rows.setdefault(split, []).append(
            {"id": case.get("id"), "fused_scores": scores, "answerable": bool(case.get("answerable"))}
        )
        print(f"{case.get('id')} n={len(scores)}", flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
