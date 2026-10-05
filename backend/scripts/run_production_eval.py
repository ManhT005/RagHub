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
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 3072
CHAT_MODEL = "gemini-3.5-flash-lite"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


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
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{path.name}\"\r\nContent-Type: {ctype}\r\n\r\n"
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


def sse_chat(token: str, org: str, chatbot: str, message: str):
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
    with urllib.request.urlopen(req, timeout=180) as resp:
        event = None
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:") and event:
                events.append((event, json.loads(line[len("data:"):].strip())))
                event = None
    return events, (time.perf_counter() - t0) * 1000


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
    token: str, org: str, name: str, ptype: str, cap: str, model: str, dim, secret: str
):
    status, items = api("GET", f"/organizations/{org}/providers", token, org)
    for item in items or []:
        if item.get("model") == model and item.get("capability") == cap:
            return item["id"]
    payload = {
        "name": name, "provider_type": ptype, "capability": cap, "model": model,
        "base_url": GEMINI_BASE, "secret": secret, "config_json": {}, "enabled": True,
    }
    if dim:
        payload["dimension"] = dim
    status, item = api("POST", f"/organizations/{org}/providers", token, org, payload)
    if status != 201:
        raise SystemExit(f"create provider {name} failed: {status} {item}")
    status, test = api("POST", f"/providers/{item['id']}/test", token, org, {})
    print(f"provider {name} test: {status} {json.dumps(test)[:200]}", flush=True)
    return item["id"]


def ensure_workspace(token: str, org: str, emb_id: str, chat_id: str):
    status, items = api("GET", "/workspaces", token, org)
    for ws in items or []:
        if ws.get("slug") == WS_SLUG:
            return ws["id"]
    status, ws = api(
        "POST", "/workspaces", token, org,
        {"name": "Golden Test", "slug": WS_SLUG,
         "embedding_model_id": emb_id, "chat_model_id": chat_id},
    )
    if status != 201:
        raise SystemExit(f"create workspace failed: {status} {ws}")
    return ws["id"]


def ensure_chatbot(token: str, org: str, ws: str):
    status, items = api("GET", f"/workspaces/{ws}/chatbots", token, org)
    for bot in items or []:
        if bot.get("name") == "Golden Eval":
            return bot["id"]
    status, bot = api(
        "POST", f"/workspaces/{ws}/chatbots", token, org,
        {"name": "Golden Eval", "model": CHAT_MODEL, "retrieval_limit": 5},
    )
    if status != 201:
        raise SystemExit(f"create chatbot failed: {status} {bot}")
    status, pub = api(
        "POST", f"/chatbots/{bot['id']}/publish", token, org,
        {"allowed_origins": ["http://localhost:8081"]},
    )
    if status != 200:
        raise SystemExit(f"publish chatbot failed: {status} {pub}")
    return bot["id"]


def wait_ready(token: str, org: str, ws: str, needed: set[str], timeout_s: int = 1800):
    # Quota/rate-limit flaps pass through FAILED between patient retries; only
    # terminal parse/validation codes abort the wait. Golden .md files never hit those.
    terminal_codes = {
        "INVALID_PDF", "TEXT_DECODE_FAILED", "EMPTY_EXTRACTED_TEXT",
        "UNSUPPORTED_FILE_TYPE", "INVALID_FILE_SIGNATURE", "MACRO_BLOCKED",
        "DECOMPRESSION_BOMB", "DOCUMENT_LIMIT_EXCEEDED", "OCR_REQUIRED",
        "OCR_TIMEOUT", "CHUNKING_FAILED", "EMPTY_FILE", "STORAGE_UNAVAILABLE",
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
            d for d in docs or []
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

    org = ensure_org(token)
    emb = ensure_provider(token, org, "Eval Embedding", "GOOGLE_GEMINI", "EMBEDDING",
                          EMBED_MODEL, EMBED_DIM, gemini_key)
    chat = ensure_provider(token, org, "Eval Chat", "GOOGLE_GEMINI", "CHAT",
                           CHAT_MODEL, None, gemini_key)
    ws = ensure_workspace(token, org, emb, chat)
    bot = ensure_chatbot(token, org, ws)

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
        exp = expected_keys(case.get("expected_document_ids", []),
                            case.get("expected_chunk_ids", []), file_of)
        t0 = time.perf_counter()
        s, search = api(
            "GET", f"/workspaces/{ws}/search?q={urllib.parse.quote(q)}&limit=5",
            token, org,
        )
        ret_ms = (time.perf_counter() - t0) * 1000
        ranked = []
        if s == 200:
            for hit in search.get("hits", []):
                ranked.append(chunk_key(hit.get("source_name", ""), hit.get("page_number")))
        rel = {k: 1.0 for k in exp}
        answerable = bool(case.get("answerable"))
        predicted_answerable = len(ranked) > 0

        events, chat_ms = sse_chat(token, org, bot, q)
        answer, inventory, usage, err = "", set(), None, None
        for kind, payload in events:
            if kind == "citations":
                for c in payload.get("citations", []):
                    inventory.add(c.get("citation_id", ""))
            elif kind == "token":
                answer += payload.get("text", "")
            elif kind == "usage":
                usage = payload
            elif kind == "error":
                err = payload
        report = validate_citations(answer, inventory_ids=inventory)
        cited = list(report.used_ids)
        facts = [f for f in case.get("reference_facts", [])]
        ans_n = norm(answer)
        ans_digits = norm_digits(answer)
        recalled = (
            sum(fact_token_recall(f, ans_digits) for f in facts) / max(1, len(facts))
            if facts else 1.0
        )
        forbidden_hit = [
            c for c in case.get("forbidden_claims", []) if norm(c) and norm(c) in ans_n
        ]

        cases.append({
            "id": case.get("id"),
            "answerable": answerable,
            "predicted_answerable": predicted_answerable,
            "retrieval_ms": round(ret_ms, 1),
            "chat_ms": round(chat_ms, 1),
            "hit@5": hit_at_k(ranked, exp),
            "mrr@5": mrr_at_k(ranked, exp),
            "ndcg@5": ndcg_at_k(ranked, rel),
            "cited_ids": cited,
            "invalid_ids": list(report.invalid_ids),
            "coverage": report.coverage,
            "facts_recalled": round(recalled, 3),
            "facts_total": len(facts),
            "forbidden_hit": forbidden_hit,
            "chat_error": err,
            "usage": usage,
            "answer": answer,
            "tags": case.get("tags", []),
            "split": case.get("split"),
        })
        print(f"{case.get('id')} hit={cases[-1]['hit@5']} mrr={cases[-1]['mrr@5']:.2f} "
              f"err={bool(err)}", flush=True)

    answerable_cases = [c for c in cases if c["answerable"]]
    rej = rejection_scores(
        predicted_unanswerable=[not c["predicted_answerable"] for c in cases],
        actual_unanswerable=[not c["answerable"] for c in cases],
    )
    summary = {
        "hit@5": sum(c["hit@5"] for c in cases) / len(cases),
        "answerable_hit@5": sum(c["hit@5"] for c in answerable_cases) / max(
            1, len(answerable_cases)
        ),
        "mrr@5": sum(c["mrr@5"] for c in cases) / len(cases),
        "ndcg@5": sum(c["ndcg@5"] for c in cases) / len(cases),
        "rejection_f1": rej["f1"],
        "rejection_precision": rej["precision"],
        "rejection_recall": rej["recall"],
        "citation_invalid_total": sum(len(c["invalid_ids"]) for c in cases),
        "citation_coverage_mean": sum(c["coverage"] for c in cases) / len(cases),
        "facts_recall": round(
            sum(c["facts_recalled"] for c in cases) / max(1, len(cases)), 3
        ),
        "forbidden_hits": sum(len(c["forbidden_hit"]) for c in cases),
        "chat_errors": sum(1 for c in cases if c["chat_error"]),
        "retrieval_p50_ms": sorted(c["retrieval_ms"] for c in cases)[len(cases) // 2],
        "retrieval_p95_ms": sorted(c["retrieval_ms"] for c in cases)[int(len(cases) * 0.95) - 1],
        "chat_p50_ms": sorted(c["chat_ms"] for c in cases)[len(cases) // 2],
    }

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
        "mode": "production-hybrid",
        "commit": commit,
        "dataset_hash": dataset,
        "config_hash": sha("candidates=25 rrf_k=60 mapping=vi_hybrid_v2"),
        "model_ids": {"embedding": EMBED_MODEL, "chat": CHAT_MODEL},
        "seed": args.seed,
        "retrieval_config": {"candidates": 25, "rrf_k": 60, "mapping_version": "vi_hybrid_v2",
                             "relevance_gate": False, "reranker": False},
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "cases": cases,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY: " + json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
