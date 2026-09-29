import hashlib
import hmac
import secrets


def generate_conversation_token() -> str:
    return "rhct_" + secrets.token_urlsafe(32)


def hash_conversation_token(raw_token: str, pepper: str) -> str:
    payload = f"public-conversation:{raw_token}".encode()
    return hmac.new(pepper.encode(), payload, hashlib.sha256).hexdigest()


def conversation_token_matches(raw_token: str, expected_hash: str, pepper: str) -> bool:
    candidate = hash_conversation_token(raw_token, pepper)
    return hmac.compare_digest(candidate, expected_hash)
