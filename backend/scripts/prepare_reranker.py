"""Prepare a pinned snapshot during deployment; runtime uses only local files."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.ai.local_reranker import (  # noqa: E402
    MODEL_ID,
    MODEL_REVISION,
    snapshot_sha256,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    from huggingface_hub import snapshot_download

    directory = Path(args.directory).resolve()
    snapshot_download(
        MODEL_ID,
        revision=MODEL_REVISION,
        local_dir=directory,
        allow_patterns=["*.json", "*.txt", "*.model", "*.safetensors"],
    )
    checksum = snapshot_sha256(directory)
    if args.expected_sha256 and checksum != args.expected_sha256:
        raise SystemExit("Prepared snapshot checksum mismatch")
    print(
        json.dumps(
            {
                "model_id": MODEL_ID,
                "revision": MODEL_REVISION,
                "RAG_RERANKER_SNAPSHOT_PATH": str(directory),
                "RAG_RERANKER_EXPECTED_SHA256": checksum,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
