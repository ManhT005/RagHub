import asyncio
import hashlib
import json
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from fastapi import FastAPI, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.core.database import Session, Record, Token, DATA
from app.core.security import current_user, password_hash, issue
from app.modules import repository as repo
from app.modules.ingestion import ingest
from app.modules.search import search

@asynccontextmanager
async def lifespan(app):
    with Session() as db:
        interrupted = [(r.id, r.owner) for r in db.query(Record).filter_by(kind="document").all()
                       if json.loads(r.payload).get("status") in {"QUEUED", "PARSING", "CHUNKING"}]
    for identifier, owner in interrupted:
        repo.update(identifier, owner, {"status": "FAILED", "error": "Server restarted; please re-index."})
    yield

app = FastAPI(title="RagHub Demo", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:4200", "http://localhost:8080", "http://localhost:8081"], allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])
User = Annotated[str, Depends(current_user)]

@app.exception_handler(HTTPException)
async def errors(request, exc):
    return JSONResponse({"error": {"code": str(exc.status_code), "message": exc.detail}}, status_code=exc.status_code, headers=exc.headers)

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=8, max_length=128)
class Named(BaseModel):
    name: str = Field(min_length=1, max_length=120)
class BotConfig(Named):
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080", "http://localhost:8081", "http://localhost:4200"], max_length=10)
class Question(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "mode": "demo", "retrieval": "BM25", "provider": "extractive"}

@app.post("/api/v1/auth/register", status_code=201)
def register(body: Credentials):
    email = body.email.lower().strip()
    from sqlalchemy.exc import IntegrityError
    try:
        with Session.begin() as db:
            db.add(Record(id=email, kind="user", owner=email, parent="", payload=json.dumps({"password": password_hash(body.password)})))
    except IntegrityError:
        raise HTTPException(409, "Email already registered")
    return {"access_token": issue(email), "email": email}

@app.post("/api/v1/auth/login")
def login(body: Credentials):
    email = body.email.lower().strip()
    try:
        account = repo.get(email, email, "user")
    except HTTPException:
        raise HTTPException(401, "Invalid credentials")
    if not secrets.compare_digest(account["password"], password_hash(body.password, account["password"].split(":")[0])):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": issue(email), "email": email}

@app.post("/api/v1/auth/logout", status_code=204)
def logout(request: Request, owner: User):
    with Session.begin() as db:
        token = db.get(Token, hashlib.sha256(request.headers["authorization"][7:].encode()).hexdigest())
        if token:
            db.delete(token)

@app.get("/api/v1/workspaces")
def workspaces(owner: User):
    return repo.listing("workspace", owner)
@app.post("/api/v1/workspaces", status_code=201)
def workspace(body: Named, owner: User):
    return repo.create("workspace", owner, {"name": body.name})
@app.get("/api/v1/workspaces/{wid}/documents")
def documents(wid: str, owner: User):
    repo.get(wid, owner, "workspace")
    return [{k: v for k, v in d.items() if k != "chunks"} for d in repo.listing("document", owner, wid)]

@app.post("/api/v1/workspaces/{wid}/documents", status_code=202)
async def upload(wid: str, owner: User, tasks: BackgroundTasks, file: UploadFile = File(...)):
    repo.get(wid, owner, "workspace")
    name = Path((file.filename or "document").replace("\\", "/")).name
    ext = Path(name).suffix.lower()
    allowed = {".pdf": {"application/pdf"}, ".txt": {"text/plain"}, ".md": {"text/markdown", "text/plain", "application/octet-stream"}}
    if ext not in allowed or file.content_type not in allowed[ext]:
        raise HTTPException(415, "Supported: PDF, TXT, MD with matching MIME type")
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Demo upload limit: 5 MB")
    if not content or (ext == ".pdf" and not content.startswith(b"%PDF-")):
        raise HTTPException(422, "Invalid file content")
    checksum = hashlib.sha256(content).hexdigest()
    if any(d.get("checksum") == checksum and d["status"] != "DELETED" for d in repo.listing("document", owner, wid)):
        raise HTTPException(409, "Document already exists in this workspace")
    doc = repo.create("document", owner, {"name": name, "status": "QUEUED", "checksum": checksum, "extension": ext, "chunk_count": 0}, wid)
    (DATA / doc["id"]).write_bytes(content)
    tasks.add_task(ingest, doc["id"], owner, content, ext)
    return doc

@app.post("/api/v1/documents/{did}/reindex", status_code=202)
def reindex(did: str, owner: User, tasks: BackgroundTasks):
    doc = repo.get(did, owner, "document")
    if doc["status"] not in {"READY", "FAILED"}:
        raise HTTPException(409, "Document is busy or deleted")
    repo.update(did, owner, {"status": "QUEUED"})
    tasks.add_task(ingest, did, owner, (DATA / did).read_bytes(), doc["extension"])
    return {"status": "QUEUED"}

@app.delete("/api/v1/documents/{did}", status_code=204)
def delete(did: str, owner: User):
    doc = repo.get(did, owner, "document")
    if doc["status"] in {"QUEUED", "PARSING", "CHUNKING"}:
        raise HTTPException(409, "Wait for ingestion to complete")
    repo.update(did, owner, {"status": "DELETED", "chunks": [], "chunk_count": 0})

@app.get("/api/v1/workspaces/{wid}/chatbots")
def bots(wid: str, owner: User):
    repo.get(wid, owner, "workspace")
    return repo.listing("chatbot", owner, wid)
@app.post("/api/v1/workspaces/{wid}/chatbots", status_code=201)
def bot(wid: str, body: BotConfig, owner: User):
    repo.get(wid, owner, "workspace")
    for origin in body.allowed_origins:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or "*" in origin:
            raise HTTPException(422, "Origin must contain scheme, host, optional port; no path")
    return repo.create("chatbot", owner, {"name": body.name, "workspace_id": wid, "allowed_origins": body.allowed_origins, "published": False}, wid)
@app.post("/api/v1/chatbots/{bid}/publish")
def publish(bid: str, owner: User):
    bot = repo.get(bid, owner, "chatbot")
    return repo.update(bid, owner, {"published": not bot["published"]})

buckets = {}
active = set()
def public_bot(bid, request):
    bot = repo.get(bid, kind="chatbot")
    if not bot["published"]:
        raise HTTPException(404, "Chatbot is not published")
    if request.headers.get("origin") not in bot["allowed_origins"]:
        raise HTTPException(403, "Origin is not allowed")
    return bot
@app.get("/api/v1/public/chatbots/{bid}/config")
def config(bid: str, request: Request):
    bot = public_bot(bid, request)
    return {"name": bot["name"], "mode": "extractive-demo"}
@app.post("/api/v1/public/chatbots/{bid}/chat")
async def public_chat(bid: str, body: Question, request: Request):
    return answer(public_bot(bid, request), body, request)
@app.post("/api/v1/chatbots/{bid}/test")
async def test_chat(bid: str, body: Question, request: Request, owner: User):
    return answer(repo.get(bid, owner, "chatbot"), body, request)

def answer(bot, body, request):
    now = time.monotonic()
    for old in list(buckets):
        if now - buckets[old][0] >= 60:
            del buckets[old]
    key = (bot["id"], request.client.host if request.client else "local")
    started, count = buckets.get(key, (now, 0))
    if count >= 20 or bot["id"] in active:
        raise HTTPException(429, "Demo limit: 20 questions/minute and 1 active request/chatbot", headers={"Retry-After": "60"})
    buckets[key] = (started, count + 1)
    hits = search(bot["_owner"], bot["workspace_id"], body.message)
    text = "No matching information in this workspace." if not hits else "Relevant document excerpts (demo, no LLM):\n\n" + "\n\n".join(f"[{i+1}] {h['text']}" for i, h in enumerate(hits))
    active.add(bot["id"])
    async def stream():
        try:
            yield "event: citations\ndata: " + json.dumps(hits, ensure_ascii=False) + "\n\n"
            for start in range(0, len(text), 40):
                yield "event: token\ndata: " + json.dumps(text[start:start+40], ensure_ascii=False) + "\n\n"
                await asyncio.sleep(.01)
            repo.create("conversation", bot["_owner"], {"question": body.message, "answer": text, "citations": hits}, bot["id"])
            yield 'event: done\ndata: {}\n\n'
        finally:
            active.discard(bot["id"])
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
