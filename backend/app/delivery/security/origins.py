from urllib.parse import urlsplit


def normalize_origin(value: str | None) -> str | None:
    if not value or any(ord(char) <= 32 for char in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or "*" in host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            return None
        host = host.encode("idna").decode("ascii").lower()
        if ":" in host:
            from ipaddress import IPv6Address

            IPv6Address(host)
            host = f"[{host}]"
        elif not all(char.isalnum() or char in ".-" for char in host):
            return None
        if port == {"http": 80, "https": 443}[parsed.scheme]:
            port = None
        return f"{parsed.scheme}://{host}" + (f":{port}" if port is not None else "")
    except (ValueError, UnicodeError):
        return None


def origin_is_allowed(origin: str | None, allowed_origins: list[str]) -> bool:
    normalized = normalize_origin(origin)
    return normalized is not None and normalized in {
        normalize_origin(value) for value in allowed_origins
    }
