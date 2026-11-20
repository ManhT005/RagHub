"""Known Space signatures, not guesses based on endpoint names."""

import json


def is_sict(url):
    return (url or "").rstrip("/") in {
        "https://huggingface.co/spaces/quyendzvaio/sict",
        "https://quyendzvaio-sict.hf.space",
    }


def sict_defaults(url, options):
    result = dict(options)
    if is_sict(url) and not any(
        result.get(key) for key in ("spaces_chat", "spaces_query", "spaces_document")
    ):
        for key, task in (("spaces_query", "query"), ("spaces_document", "document")):
            result[key] = json.dumps(
                {
                    "api": "embed_batch_text",
                    "inputs": ["$texts", task, "$dimension"],
                    "output": "0.embeddings",
                }
            )
    return result
