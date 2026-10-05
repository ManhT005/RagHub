"""Export the deterministic runtime OpenAPI artifact.

FastAPI runtime schema is the single source of truth; this file only
serializes it with sorted keys so CI can diff for drift.

Usage (from backend/):
    python scripts/export_openapi.py --out ../docs/api/openapi.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    schema = app.openapi()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    paths = len(schema["paths"])
    ops = sum(len(v) for v in schema["paths"].values())
    print(f"paths={paths} operations={ops} -> {out}")


if __name__ == "__main__":
    main()
