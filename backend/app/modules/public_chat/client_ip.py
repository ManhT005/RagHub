import ipaddress

from fastapi import Request

from app.core.config import Settings, get_settings


def resolve_client_ip(request: Request, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    peer = request.client.host if request.client else "unknown"
    if not settings.trust_proxy_headers:
        return peer
    try:
        peer_address = ipaddress.ip_address(peer)
        networks = [
            ipaddress.ip_network(value.strip(), strict=False)
            for value in settings.trusted_proxy_cidrs.split(",")
            if value.strip()
        ]
    except ValueError:
        return peer
    if not any(peer_address in network for network in networks):
        return peer
    forwarded = request.headers.get("X-Real-IP")
    if not forwarded:
        return peer
    try:
        return str(ipaddress.ip_address(forwarded.strip()))
    except ValueError:
        return peer
