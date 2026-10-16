from agentsre.idempotency import IdempotencyGuard, action_key


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_blocks_duplicate_within_window() -> None:
    clock = Clock()
    guard = IdempotencyGuard(window_seconds=60, clock=clock)
    first = guard.check("transfer", {"to": "A", "amt": 10})
    second = guard.check("transfer", {"amt": 10, "to": "A"})
    assert first.allowed
    assert not second.allowed
    assert second.reason == "duplicate_within_window"
    assert guard.duplicate_action_rate == 0.5


def test_allows_after_window() -> None:
    clock = Clock()
    guard = IdempotencyGuard(window_seconds=60, clock=clock)
    guard.check("transfer", {"amt": 10})
    clock.t = 61
    assert guard.check("transfer", {"amt": 10}).allowed


def test_different_params_and_scopes_are_independent() -> None:
    guard = IdempotencyGuard(clock=Clock())
    assert guard.check("transfer", {"amt": 10}, scope="acct-1").allowed
    assert guard.check("transfer", {"amt": 11}, scope="acct-1").allowed
    assert guard.check("transfer", {"amt": 10}, scope="acct-2").allowed


def test_action_key_is_order_independent() -> None:
    assert action_key("pay", {"a": 1, "b": 2}) == action_key("pay", {"b": 2, "a": 1})


def test_rejects_bad_config() -> None:
    try:
        IdempotencyGuard(window_seconds=0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
