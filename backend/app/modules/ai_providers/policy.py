from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderRequestPolicy:
    connect_timeout: float = 10.0
    read_timeout: float = 45.0
    max_attempts: int = 3
    backoff_seconds: float = 0.25
