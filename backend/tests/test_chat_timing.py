from app.modules.chatbots.timing import ChatStreamTiming


class Clock:
    def __init__(self) -> None:
        self.value = 10.0

    def __call__(self) -> float:
        return self.value


def test_first_token_latency_is_recorded_only_once() -> None:
    clock = Clock()
    timing = ChatStreamTiming(clock=clock)

    clock.value = 10.923
    timing.record_token()
    clock.value = 11.5
    timing.record_token()

    assert timing.first_token_ms == 923
    assert timing.elapsed_ms() == 1500
    assert timing.first_token_ms <= timing.elapsed_ms()


def test_first_token_latency_stays_empty_without_a_token() -> None:
    clock = Clock()
    timing = ChatStreamTiming(clock=clock)

    clock.value = 10.25

    assert timing.first_token_ms is None
    assert timing.elapsed_ms() == 250
