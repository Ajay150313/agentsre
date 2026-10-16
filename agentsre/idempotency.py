"""
IdempotencyGuard — blocks repeated irreversible agent actions.

An agent that times out and retries can complete the same write twice.
Dashboards stay green: HTTP 200, latency in budget, no error rate.

This module treats that as its own failure class.

    DuplicateActionRate = blocked repeats / checks, rolling window

Three rules for any agent that can write to a money or state system:
    1. Every action gets a deterministic key (action + sorted params + scope)
    2. Repeats inside the window are blocked and counted, not silently retried
    3. DuplicateActionRate is an SLI. If it rises, the agent is compensating
       for something broken upstream.

In-process only. Cross-process deployments need a shared store
(conditional write) in front of this check.

Author: Ajay Devineni
License: MIT
Repository: github.com/Ajay150313/agentsre
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List


def action_key(action: str, params: Dict[str, Any], scope: str = "") -> str:
    """Stable hash of action + params + scope. Key order does not matter."""
    payload = json.dumps(
        {"a": action, "p": params, "s": scope},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    key: str
    reason: str
    prior_count: int


class IdempotencyGuard:
    """Allow an identical action at most ``max_repeats`` times per window.

    Thread-safe. Caps the in-memory map so a long-running process cannot
    grow without bound.
    """

    def __init__(
        self,
        window_seconds: float = 300.0,
        max_repeats: int = 1,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if max_repeats < 1:
            raise ValueError("max_repeats must be >= 1")
        self.window_seconds = window_seconds
        self.max_repeats = max_repeats
        self.max_keys = max_keys
        self._clock = clock
        self._seen: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        self.checked = 0
        self.blocked = 0

    def check(
        self,
        action: str,
        params: Dict[str, Any],
        scope: str = "",
    ) -> GuardDecision:
        key = action_key(action, params, scope)
        now = self._clock()
        with self._lock:
            self.checked += 1
            if len(self._seen) > self.max_keys:
                self._prune(now)
            stamps = [
                t for t in self._seen.get(key, [])
                if now - t <= self.window_seconds
            ]
            if len(stamps) >= self.max_repeats:
                self._seen[key] = stamps
                self.blocked += 1
                return GuardDecision(
                    False, key, "duplicate_within_window", len(stamps)
                )
            stamps.append(now)
            self._seen[key] = stamps
            return GuardDecision(True, key, "ok", len(stamps) - 1)

    def _prune(self, now: float) -> None:
        for k in list(self._seen):
            live = [t for t in self._seen[k] if now - t <= self.window_seconds]
            if live:
                self._seen[k] = live
            else:
                del self._seen[k]

    @property
    def duplicate_action_rate(self) -> float:
        return self.blocked / self.checked if self.checked else 0.0
