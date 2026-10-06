"""Generate source-preserving QA review drafts; never promote them to release labels."""

import argparse
import json
import unicodedata
from pathlib import Path

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "tests/fixtures/rag_golden/qa.json"


def without_diacritics(text):
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def generate(cases):
    result = []
    for case in cases:
        question = case["question"]
        variants = [
            ("original", question),
            ("polite", "Bạn giúp tôi giải đáp: " + question),
            ("document-scope", "Theo tài liệu trong workspace, " + question),
            ("short-answer", question + " Vui lòng trả lời ngắn gọn."),
            ("source-request", question + " Cho tôi biết nguồn hỗ trợ câu trả lời."),
            ("vi-without-diacritics", without_diacritics(question)),
            ("vi-en-mixed", question + " Please answer using the provided documents."),
        ]
        for variant, text in variants:
            result.append(
                {
                    **case,
                    "id": case["id"] + "-draft-" + variant,
                    "corpus_revision": "golden-v2-draft",
                    "family_id": case["id"],
                    "origin_case_id": case["id"],
                    "question": text,
                    "review_status": "draft",
                    "tags": [*case["tags"], variant],
                    # Per-fact source allocation must be reviewed; no inferred support is approved.
                    "expected_facts": [
                        {"fact": fact, "supporting_chunk_ids": case["expected_chunk_ids"]}
                        for fact in case.get("reference_facts", [])
                    ],
                }
            )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    draft = generate(json.loads(args.source.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"draft_cases": len(draft), "reviewed_cases": 0}))


if __name__ == "__main__":
    main()
