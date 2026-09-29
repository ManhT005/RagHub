from urllib.parse import urlsplit

from app.core.exceptions import AppError


def normalize_origin(value: str) -> str:
    if value == "*":
        raise ValueError("Wildcard origins are not supported.")
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Origin must use http or https and include a host.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Origin must not contain credentials.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Origin must not contain a path, query, or fragment.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Origin has an invalid port.") from exc
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    return f"{scheme}://{host}{f':{port}' if port is not None and not default_port else ''}"


def require_valid_origin(value: str) -> str:
    try:
        return normalize_origin(value)
    except ValueError as exc:
        raise AppError("INVALID_ORIGIN", str(exc), status_code=422) from exc
