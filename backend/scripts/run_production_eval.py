"""Production hybrid eval runner (Stage A of the benchmark plan).

Drives the REAL stack over HTTP: eval org/workspace/providers on the live
system, ingests the golden corpus, runs all 30 QA through the hybrid
retrieval API (BM25 + vector, RRF) and the chat SSE endpoint, then reports
the 7 spec metrics plus latency. Paid Gemini usage is limited to the 9
golden docs + 30 queries + 30 chats.

Usage (from backend/):
    python scripts/run_production_eval.py --out ../artifacts/rag_production_eval.json --token <JWT>
    python scripts/run_production_eval.py --out ../artifacts/x.json --mint-email you@example.com
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raghub_core.domain.evaluation.metrics import (
    hit_at_k,
    mrr_at_k,
    ndcg_at_k,
    rejection_scores,
)
from raghub_core.domain.rag.citation_validator import validate_citations  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "rag_golden"
BASE = "http://127.0.0.1:8080"
API = BASE + "/api/v1"

ORG_SLUG = "eval-golden"
WS_SLUG = "golden-test"
LOCAL_WS_SLUG = "golden-test-local"
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 3072
CHAT_MODEL = "gemini-3.5-flash-lite"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
LOCAL_EMBED_MODEL = "token-hash-v1"
LOCAL_EMBED_DIM = 384
LOCAL_CHAT_MODEL = "gemma3:1b"
LOCAL_OLLAMA_BASE = "http://ollama:11434"
TRANSIENT_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
PROVIDER_ERROR_CODES = {
    "PROVIDER_RATE_LIMITED",
    "PROVIDER_TIMEOUT",
    "PROVIDER_UNAVAILABLE",
    "CHAT_PROVIDER_TIMEOUT",
    "CHAT_RUNTIME_FAILED",
}
DEFAULT_GATE_THRESHOLDS = {
    "rejection_f1": 0.90,
    "citation_precision": 1.00,
    "answerable_direct_pass_rate": 0.90,
    "followup_resolution_rate": 0.85,
    "unnecessary_clarification_rate": 0.15,
    "citation_coverage_mean": 0.85,
    "facts_recall": 0.85,
    "provider_errors": 0,
}


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * pct) - 1))
    return float(ordered[index])


def error_code(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    value = payload.get("code") or payload.get("error_code")
    if value:
        return str(value)
    error = payload.get("error")
    if isinstance(error, dict):
        return error_code(error)
    if isinstance(error, str):
        return error
    return ""


def is_provider_error(payload) -> bool:
    code = error_code(payload).upper()
    return code in PROVIDER_ERROR_CODES or code.startswith("PROVIDER_") or "RATE_LIMIT" in code


def quality_cases(cases: list[dict]) -> list[dict]:
    return [c for c in cases if not c.get("provider_error")]


def summarize_cases(cases: list[dict]) -> dict:
    answerable_cases = [c for c in cases if c["answerable"]]
    chat_quality = quality_cases(cases)
    chat_answerable = [c for c in chat_quality if c["answerable"]]
    rej = rejection_scores(
        predicted_unanswerable=[not c["predicted_answerable"] for c in cases],
        actual_unanswerable=[not c["answerable"] for c in cases],
    )
    citation_used = sum(len(c.get("cited_ids", [])) for c in chat_quality)
    citation_invalid = sum(len(c.get("invalid_ids", [])) for c in chat_quality)
    citation_precision = (
        1.0 if citation_used == 0 else (citation_used - citation_invalid) / citation_used
    )
    return {
        "hit@5": sum(c["hit@5"] for c in cases) / max(1, len(cases)),
        "answerable_hit@5": sum(c["hit@5"] for c in answerable_cases)
        / max(1, len(answerable_cases)),
        "answerable_direct_pass_rate": sum(1 for c in answerable_cases if c["predicted_answerable"])
        / max(1, len(answerable_cases)),
        "mrr@5": sum(c["mrr@5"] for c in cases) / max(1, len(cases)),
        "ndcg@5": sum(c["ndcg@5"] for c in cases) / max(1, len(cases)),
        "rejection_f1": rej["f1"],
        "rejection_precision": rej["precision"],
        "rejection_recall": rej["recall"],
        "citation_precision": citation_precision,
        "citation_invalid_total": citation_invalid,
        "citation_coverage_mean": sum(c["coverage"] for c in chat_quality)
        / max(1, len(chat_quality)),
        "facts_recall": round(
            sum(c["facts_recalled"] for c in chat_answerable) / max(1, len(chat_answerable)), 3
        ),
        "forbidden_hits": sum(len(c["forbidden_hit"]) for c in chat_quality),
        "chat_errors": sum(1 for c in cases if c["chat_error"]),
        "provider_errors": sum(1 for c in cases if c.get("provider_error")),
        "quality_chat_cases": len(chat_quality),
        "retrieval_p50_ms": percentile([c["retrieval_ms"] for c in cases], 0.50),
        "retrieval_p95_ms": percentile([c["retrieval_ms"] for c in cases], 0.95),
        "chat_p50_ms": percentile([c["chat_ms"] for c in cases], 0.50),
        "chat_p95_ms": percentile([c["chat_ms"] for c in cases], 0.95),
    }


def evaluate_release_gate(summary: dict, thresholds: dict) -> tuple[bool, dict[str, dict]]:
    checks = {
        "rejection_f1": {
            "actual": summary.get("rejection_f1", 0.0),
            "op": ">=",
            "threshold": thresholds["rejection_f1"],
        },
        "citation_precision": {
            "actual": summary.get("citation_precision", 0.0),
            "op": ">=",
            "threshold": thresholds["citation_precision"],
        },
        "answerable_direct_pass_rate": {
            "actual": summary.get("answerable_direct_pass_rate", 0.0),
            "op": ">=",
            "threshold": thresholds["answerable_direct_pass_rate"],
        },
        "citation_coverage_mean": {
            "actual": summary.get("citation_coverage_mean", 0.0),
            "op": ">=",
            "threshold": thresholds["citation_coverage_mean"],
        },
        "facts_recall": {
            "actual": summary.get("facts_recall", 0.0),
            "op": ">=",
            "threshold": thresholds["facts_recall"],
        },
        "provider_errors": {
            "actual": summary.get("provider_errors", 0),
            "op": "<=",
            "threshold": thresholds["provider_errors"],
        },
    }
    for metric, op in {
        "mrr@5": ">=",
        "ndcg@5": ">=",
        "answerable_hit@5": ">=",
        "retrieval_p95_ms": "<=",
        "chat_p95_ms": "<=",
        "citation_support_precision": ">=",
        "fact_support_recall": ">=",
    }.items():
        if thresholds.get(metric) is not None:
            checks[metric] = {
                "actual": summary.get(metric),
                "op": op,
                "threshold": thresholds[metric],
            }
    for item in checks.values():
        if item["actual"] is None:
            item["passed"] = False
            continue
        if item["op"] == ">=":
            item["passed"] = item["actual"] >= item["threshold"]
        else:
            item["passed"] = item["actual"] <= item["threshold"]
    return all(item["passed"] for item in checks.values()), checks


def norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    return " ".join(text.split())


def fact_token_recall(fact: str, answer_norm_digits: str) -> float:
    """Share of fact content-tokens present in the answer (paraphrase-tolerant)."""
    import re

    toks = [t for t in re.findall(r"[a-z0-9\u00e0-\u1ef9]+", norm_digits(fact)) if len(t) >= 2]
    if not toks:
        return 1.0
    hit = sum(1 for t in toks if t in answer_norm_digits)
    return hit / len(toks)


def norm_digits(text: str) -> str:
    """Compare numbers regardless of thousand separators (8.300 = 8,300 = 8300)."""
    out = []
    for ch in norm(text):
        if ch.isdigit():
            out.append(ch)
        elif ch in ".,":
            continue
        else:
            out.append(ch)
    return "".join(out)


def api(method: str, path: str, token: str, org: str | None = None, body=None):
    headers = {"Authorization": f"Bearer {token}"}
    if org:
        headers["X-Organization-ID"] = org
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = resp.read().decode("utf-8", "replace")
            return resp.status, json.loads(payload) if payload else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


CONTENT_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".html": "text/html",
    ".htm": "text/html",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def upload_file(token: str, org: str, ws: str, path: Path):
    boundary = "----evalboundary1234"
    content = path.read_bytes()
    ctype = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{path.name}"\r\nContent-Type: {ctype}\r\n\r\n'
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{API}/workspaces/{ws}/documents",
        data=head + content + tail,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-ID": org,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"upload {path.name} failed: {e.code} {e.read().decode()[:500]}") from e


def _sse_chat_once(token: str, org: str, chatbot: str, message: str):
    req = urllib.request.Request(
        f"{API}/chatbots/{chatbot}/chat",
        data=json.dumps({"message": message}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-ID": org,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    events = []
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            event = None
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("event:"):
                    event = line[len("event:") :].strip()
                elif line.startswith("data:") and event:
                    events.append((event, json.loads(line[len("data:") :].strip())))
                    event = None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        payload = {"code": f"HTTP_{exc.code}", "message": body[:500], "http_status": exc.code}
        events.append(("error", payload))
    return events, (time.perf_counter() - t0) * 1000


def sse_chat(
    token: str,
    org: str,
    chatbot: str,
    message: str,
    *,
    retries: int = 2,
    backoff_s: float = 2.0,
):
    attempts = max(1, retries + 1)
    last_events, total_ms = [], 0.0
    for attempt in range(attempts):
        events, elapsed = _sse_chat_once(token, org, chatbot, message)
        total_ms += elapsed
        last_events = events
        err = next((payload for kind, payload in events if kind == "error"), None)
        status = err.get("http_status") if isinstance(err, dict) else None
        retryable = is_provider_error(err) or status in TRANSIENT_HTTP_CODES
        if not err or not retryable or attempt == attempts - 1:
            return events, total_ms, attempt + 1
        time.sleep(backoff_s * (2**attempt))
    return last_events, total_ms, attempts


def mint_token(email: str) -> str:
    import asyncio

    import asyncpg

    async def lookup():
        conn = await asyncpg.connect("postgresql://raghub:raghub-local-only@127.0.0.1:5434/raghub")
        try:
            row = await conn.fetchrow("SELECT id FROM users WHERE email=$1", email.strip().lower())
            return row["id"] if row else None
        finally:
            await conn.close()

    user_id = asyncio.run(lookup())
    if user_id is None:
        raise SystemExit(f"no user with email {email}")
    from uuid import UUID

    from app.core.config import get_settings
    from app.core.security import create_access_token

    return create_access_token(UUID(str(user_id)), get_settings())


def ensure_org(token: str):
    status, orgs = api("GET", "/organizations", token)
    for org in orgs or []:
        if org.get("slug") == ORG_SLUG:
            return org["id"]
    status, org = api(
        "POST", "/organizations", token, None, {"name": "Eval Golden", "slug": ORG_SLUG}
    )
    if status != 201:
        raise SystemExit(f"create org failed: {status} {org}")
    return org["id"]


def ensure_provider(
    token: str,
    org: str,
    name: str,
    ptype: str,
    cap: str,
    model: str,
    dim,
    secret: str | None,
    *,
    base_url: str | None = GEMINI_BASE,
    config_json: dict | None = None,
    test: bool = True,
):
    status, items = api("GET", f"/organizations/{org}/providers", token, org)
    for item in items or []:
        if (
            item.get("model") == model
            and item.get("capability") == cap
            and item.get("provider_type") == ptype
        ):
            return item["id"]
    payload = {
        "name": name,
        "provider_type": ptype,
        "capability": cap,
        "model": model,
        "config_json": config_json or {},
        "enabled": True,
    }
    if base_url is not None:
        payload["base_url"] = base_url
    if secret:
        payload["secret"] = secret
    if dim:
        payload["dimension"] = dim
    status, item = api("POST", f"/organizations/{org}/providers", token, org, payload)
    if status != 201:
        raise SystemExit(f"create provider {name} failed: {status} {item}")
    if test:
        status, result = api("POST", f"/providers/{item['id']}/test", token, org, {})
        print(f"provider {name} test: {status} {json.dumps(result)[:200]}", flush=True)
    return item["id"]


def ensure_workspace(
    token: str,
    org: str,
    emb_id: str,
    chat_id: str,
    *,
    slug: str = WS_SLUG,
    name: str = "Golden Test",
):
    status, items = api("GET", "/workspaces", token, org)
    for ws in items or []:
        if ws.get("slug") == slug:
            current_embedding = (ws.get("embedding_model") or {}).get("id")
            current_chat = ws.get("chat_provider_id")
            if current_embedding != emb_id or current_chat != chat_id:
                status, bound = api(
                    "PATCH",
                    f"/workspaces/{ws['id']}/providers",
                    token,
                    org,
                    {"embedding_provider_id": emb_id, "chat_provider_id": chat_id},
                )
                if status != 200:
                    raise SystemExit(f"bind workspace providers failed: {status} {bound}")
            return ws["id"]
    status, ws = api(
        "POST",
        "/workspaces",
        token,
        org,
        {"name": name, "slug": slug, "embedding_model_id": emb_id, "chat_model_id": chat_id},
    )
    if status != 201:
        raise SystemExit(f"create workspace failed: {status} {ws}")
    return ws["id"]


def ensure_chatbot(token: str, org: str, ws: str, *, model: str = CHAT_MODEL):
    status, items = api("GET", f"/workspaces/{ws}/chatbots", token, org)
    for bot in items or []:
        if bot.get("name") == "Golden Eval":
            return bot["id"]
    status, bot = api(
        "POST",
        f"/workspaces/{ws}/chatbots",
        token,
        org,
        {"name": "Golden Eval", "model": model, "retrieval_limit": 5},
    )
    if status != 201:
        raise SystemExit(f"create chatbot failed: {status} {bot}")
    status, pub = api(
        "POST",
        f"/chatbots/{bot['id']}/publish",
        token,
        org,
        {"allowed_origins": ["http://localhost:8081"]},
    )
    if status != 200:
        raise SystemExit(f"publish chatbot failed: {status} {pub}")
    return bot["id"]


def wait_ready(token: str, org: str, ws: str, needed: set[str], timeout_s: int = 1800):
    # Quota/rate-limit flaps pass through FAILED between patient retries; only
    # terminal parse/validation codes abort the wait. Golden .md files never hit those.
    terminal_codes = {
        "INVALID_PDF",
        "TEXT_DECODE_FAILED",
        "EMPTY_EXTRACTED_TEXT",
        "UNSUPPORTED_FILE_TYPE",
        "INVALID_FILE_SIGNATURE",
        "MACRO_BLOCKED",
        "DECOMPRESSION_BOMB",
        "DOCUMENT_LIMIT_EXCEEDED",
        "OCR_REQUIRED",
        "OCR_TIMEOUT",
        "CHUNKING_FAILED",
        "EMPTY_FILE",
        "STORAGE_UNAVAILABLE",
    }
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        status, docs = api("GET", f"/workspaces/{ws}/documents", token, org)
        if not isinstance(docs, list):
            print(f"documents listing HTTP {status}; retrying", flush=True)
            time.sleep(15)
            continue
        # The list may hold several rows per filename (retries/re-uploads) and
        # newest-first ordering; a file counts once ANY row is READY.
        ready_names = {d.get("name", "") for d in docs or [] if d.get("status") == "READY"}
        pending = {s for s in needed if s not in ready_names}
        failed = [
            d
            for d in docs or []
            if d.get("status") == "FAILED" and d.get("error_code") in terminal_codes
        ]
        if failed:
            raise SystemExit(f"ingestion failed: {failed[0]}")
        if not pending:
            return
        print(f"waiting READY ({len(needed) - len(pending)}/{len(needed)})", flush=True)
        time.sleep(15)
    raise SystemExit("timeout waiting for READY documents")


def chunk_key(source: str, page) -> str:
    # Markdown sources carry no page numbers (page is None); golden chunk IDs
    # (doc:p:c) only map reliably at document level, so match on filename.
    return source or ""


def expected_keys(doc_ids: list[str], chunk_ids: list[str], file_of: dict[str, str]) -> set[str]:
    keys = set()
    for cid in chunk_ids:
        doc = cid.split(":")[0]
        if doc in file_of:
            keys.add(file_of[doc])
    if not keys:
        for doc in doc_ids:
            if doc in file_of:
                keys.add(file_of[doc])
    return keys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--token", default=None)
    ap.add_argument("--mint-email", default=None)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--provider-mode", choices=["gemini", "local"], default="gemini")
    ap.add_argument("--local-embedding-model", default=LOCAL_EMBED_MODEL)
    ap.add_argument("--local-embedding-dim", type=int, default=LOCAL_EMBED_DIM)
    ap.add_argument("--local-chat-model", default=LOCAL_CHAT_MODEL)
    ap.add_argument("--local-ollama-base", default=LOCAL_OLLAMA_BASE)
    ap.add_argument(
        "--gate", action="store_true", help="Exit non-zero when release thresholds fail."
    )
    ap.add_argument("--chat-retries", type=int, default=2)
    ap.add_argument("--retry-backoff-seconds", type=float, default=2.0)
    ap.add_argument(
        "--min-rejection-f1", type=float, default=DEFAULT_GATE_THRESHOLDS["rejection_f1"]
    )
    ap.add_argument(
        "--min-citation-precision",
        type=float,
        default=DEFAULT_GATE_THRESHOLDS["citation_precision"],
    )
    ap.add_argument(
        "--min-answerable-direct-pass-rate",
        type=float,
        default=DEFAULT_GATE_THRESHOLDS["answerable_direct_pass_rate"],
    )
    ap.add_argument(
        "--min-citation-coverage",
        type=float,
        default=DEFAULT_GATE_THRESHOLDS["citation_coverage_mean"],
    )
    ap.add_argument(
        "--min-facts-recall", type=float, default=DEFAULT_GATE_THRESHOLDS["facts_recall"]
    )
    ap.add_argument(
        "--max-provider-errors", type=int, default=DEFAULT_GATE_THRESHOLDS["provider_errors"]
    )
    ap.add_argument("--min-mrr", type=float)
    ap.add_argument("--min-ndcg", type=float)
    ap.add_argument("--min-answerable-hit", type=float)
    ap.add_argument("--max-retrieval-p95-ms", type=float)
    ap.add_argument("--max-chat-p95-ms", type=float)
    args = ap.parse_args()

    token = args.token or (mint_token(args.mint_email) if args.mint_email else None)
    if not token:
        raise SystemExit("pass --token or --mint-email")

    manifest = json.loads((GOLDEN / "corpus_manifest.json").read_text(encoding="utf-8"))
    docs = manifest if isinstance(manifest, list) else manifest.get("documents", [])
    file_of = {}
    for d in docs:
        f = (d.get("file") or "").split("/")[-1]
        file_of[d["document_id"]] = f
    qa = json.loads((GOLDEN / "qa.json").read_text(encoding="utf-8"))

    import os

    org = ensure_org(token)
    if args.provider_mode == "gemini":
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            env_file = REPO / ".env"
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("GEMINI_API_KEY="):
                        gemini_key = line.split("=", 1)[1].strip()
                        break
        if not gemini_key:
            raise SystemExit("GEMINI_API_KEY env is required")
        embedding_model = EMBED_MODEL
        embedding_dim = EMBED_DIM
        chat_model = CHAT_MODEL
        workspace_slug = WS_SLUG
        workspace_name = "Golden Test"
        emb = ensure_provider(
            token,
            org,
            "Eval Embedding",
            "GOOGLE_GEMINI",
            "EMBEDDING",
            embedding_model,
            embedding_dim,
            gemini_key,
            base_url=GEMINI_BASE,
        )
        chat = ensure_provider(
            token,
            org,
            "Eval Chat",
            "GOOGLE_GEMINI",
            "CHAT",
            chat_model,
            None,
            gemini_key,
            base_url=GEMINI_BASE,
        )
    else:
        embedding_model = args.local_embedding_model
        embedding_dim = args.local_embedding_dim
        chat_model = args.local_chat_model
        workspace_slug = LOCAL_WS_SLUG
        workspace_name = "Golden Test Local"
        emb = ensure_provider(
            token,
            org,
            "Eval Local Token Hash",
            "LOCAL_TOKEN_HASH",
            "EMBEDDING",
            embedding_model,
            embedding_dim,
            None,
            base_url=None,
        )
        chat = ensure_provider(
            token,
            org,
            "Eval Local Ollama",
            "OLLAMA",
            "CHAT",
            chat_model,
            None,
            None,
            base_url=args.local_ollama_base,
            config_json={"request_profile": "OLLAMA", "read_timeout": 120.0, "max_attempts": 1},
        )
    ws = ensure_workspace(token, org, emb, chat, slug=workspace_slug, name=workspace_name)
    bot = ensure_chatbot(token, org, ws, model=chat_model)

    corpus_files = sorted((GOLDEN / "corpus").glob("*.md"))
    status, existing = api("GET", f"/workspaces/{ws}/documents", token, org)
    have = {d.get("name", "") for d in existing or []}
    for path in corpus_files:
        if path.name not in have:
            st, _ = upload_file(token, org, ws, path)
            print(f"upload {path.name}: {st}", flush=True)
    wait_ready(token, org, ws, {p.name for p in corpus_files})

    cases = []
    for case in qa:
        q = case["question"]
        exp = expected_keys(
            case.get("expected_document_ids", []), case.get("expected_chunk_ids", []), file_of
        )
        t0 = time.perf_counter()
        s, search = api(
            "GET",
            f"/workspaces/{ws}/search?q={urllib.parse.quote(q)}&limit=5",
            token,
            org,
        )
        ret_ms = (time.perf_counter() - t0) * 1000
        ranked = []
        if s == 200:
            for hit in search.get("hits", []):
                ranked.append(chunk_key(hit.get("source_name", ""), hit.get("page_number")))
        rel = {k: 1.0 for k in exp}
        answerable = bool(case.get("answerable"))
        predicted_answerable = len(ranked) > 0

        events, chat_ms, attempts = sse_chat(
            token,
            org,
            bot,
            q,
            retries=args.chat_retries,
            backoff_s=args.retry_backoff_seconds,
        )
        answer, inventory, usage, err = "", set(), None, None
        citation_inventory = []
        for kind, payload in events:
            if kind == "citations":
                citation_inventory = payload.get("citations", [])
                for c in payload.get("citations", []):
                    inventory.add(c.get("citation_id", ""))
            elif kind == "token":
                answer += payload.get("text", "")
            elif kind == "usage":
                usage = payload
            elif kind == "error":
                err = payload
        provider_error = is_provider_error(err)
        report = validate_citations(answer, inventory_ids=inventory)
        cited = list(report.used_ids)
        facts = [f for f in case.get("reference_facts", [])]
        ans_n = norm(answer)
        ans_digits = norm_digits(answer)
        recalled = (
            sum(fact_token_recall(f, ans_digits) for f in facts) / max(1, len(facts))
            if facts
            else 1.0
        )
        forbidden_hit = [
            c for c in case.get("forbidden_claims", []) if norm(c) and norm(c) in ans_n
        ]

        cases.append(
            {
                "id": case.get("id"),
                "answerable": answerable,
                "predicted_answerable": predicted_answerable,
                "retrieval_ms": round(ret_ms, 1),
                "chat_ms": round(chat_ms, 1),
                "hit@5": hit_at_k(ranked, exp),
                "mrr@5": mrr_at_k(ranked, exp),
                "ndcg@5": ndcg_at_k(ranked, rel),
                "cited_ids": cited,
                "citation_inventory": citation_inventory,
                "invalid_ids": list(report.invalid_ids),
                "coverage": report.coverage,
                "facts_recalled": round(recalled, 3),
                "facts_total": len(facts),
                "forbidden_hit": forbidden_hit,
                "chat_error": err,
                "provider_error": provider_error,
                "chat_attempts": attempts,
                "usage": usage,
                "answer": answer,
                "tags": case.get("tags", []),
                "split": case.get("split"),
            }
        )
        print(
            f"{case.get('id')} hit={cases[-1]['hit@5']} mrr={cases[-1]['mrr@5']:.2f} "
            f"err={bool(err)}",
            flush=True,
        )

    summary = summarize_cases(cases)
    thresholds = {
        "mrr@5": args.min_mrr,
        "ndcg@5": args.min_ndcg,
        "answerable_hit@5": args.min_answerable_hit,
        "retrieval_p95_ms": args.max_retrieval_p95_ms,
        "chat_p95_ms": args.max_chat_p95_ms,
        "rejection_f1": args.min_rejection_f1,
        "citation_precision": args.min_citation_precision,
        "answerable_direct_pass_rate": args.min_answerable_direct_pass_rate,
        "citation_coverage_mean": args.min_citation_coverage,
        "facts_recall": args.min_facts_recall,
        "provider_errors": args.max_provider_errors,
    }
    gate_passed, gate_checks = evaluate_release_gate(summary, thresholds)

    def sha(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()[:16]

    dataset = sha(
        (GOLDEN / "qa.json").read_bytes().hex()
        + (GOLDEN / "corpus_manifest.json").read_bytes().hex()
    )
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO), text=True
        ).strip()
    except Exception:
        commit = "unknown"

    report = {
        "mode": f"production-hybrid-{args.provider_mode}",
        "commit": commit,
        "dataset_hash": dataset,
        "config_hash": sha(
            f"provider={args.provider_mode} embedding={embedding_model} chat={chat_model} "
            "candidates=25 rrf_k=60 mapping=vi_hybrid_v2"
        ),
        "model_ids": {"embedding": embedding_model, "chat": chat_model},
        "seed": args.seed,
        "retrieval_config": {
            "provider_mode": args.provider_mode,
            "workspace_slug": workspace_slug,
            "candidates": 25,
            "rrf_k": 60,
            "mapping_version": "vi_hybrid_v2",
            "relevance_gate": False,
            "reranker": False,
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "release_gate": {"enabled": args.gate, "passed": gate_passed, "checks": gate_checks},
        "provider_error_policy": (
            "Provider/rate-limit errors are recorded separately "
            "and excluded from chat quality metrics."
        ),
        "cases": cases,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY: " + json.dumps(summary, ensure_ascii=False), flush=True)
    if args.gate and not gate_passed:
        print("RELEASE_GATE_FAILED: " + json.dumps(gate_checks, ensure_ascii=False), flush=True)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
