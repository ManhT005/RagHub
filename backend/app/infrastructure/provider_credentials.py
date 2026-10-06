def resolve_provider_secret(config, cipher, *, provider_type: str | None = None) -> str | None:
    """Credentials belong to the connection; environment import is a control-plane action."""
    connection = getattr(config, "connection", None)
    encrypted = connection.encrypted_secret if connection is not None else config.encrypted_secret
    return cipher.decrypt(encrypted) if encrypted else None
