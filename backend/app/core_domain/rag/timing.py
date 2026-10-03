import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class ChatStreamTiming:
    clock: Callable[[], float] = time.monotonic
    started_at: float = field(init=False)
    first_token_ms: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.started_at = self.clock()

    def record_token(self) -> None:
        if self.first_token_ms is None:
            self.first_token_ms = self.elapsed_ms()

    def elapsed_ms(self) -> int:
        return int((self.clock() - self.started_at) * 1000)
