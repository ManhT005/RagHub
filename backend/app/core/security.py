import hashlib
import secrets
import time
from fastapi import Header, HTTPException
from app.core.database import Session, Token

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ":" + digest

def issue(owner):
    token = secrets.token_urlsafe(32)
    with Session.begin() as db:
        db.add(Token(digest=hashlib.sha256(token.encode()).hexdigest(), owner=owner, expires=int(time.time()) + 3600))
    return token

def current_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please sign in")
    with Session() as db:
        token = db.get(Token, hashlib.sha256(authorization[7:].encode()).hexdigest())
        if not token or token.expires <= time.time():
            raise HTTPException(401, "Session expired")
        return token.owner
