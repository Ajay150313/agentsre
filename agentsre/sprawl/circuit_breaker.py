"""
agentsre.circuit_breaker
~~~~~~~~~~~~~~~~~~~~~~~~
Agent Chain Circuit Breaker

Operates at the SEMANTIC layer — not the HTTP layer.
Opens when an A2A sub-agent's validated success rate drops below
threshold, preventing cascade failures through multi-agent chains.

States:  CLOSED → OPEN → HALF_OPEN → CLOSED
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"          # Normal operation
    OPEN = "OPEN"              # Sub-agent degraded — block delegations
    HALF_OPEN = "HALF_OPEN"    # Recovery probe in progress


@dataclass
class CircuitStatus:
    sub_agent_id: str
    task_class: str
    state: CircuitState
    success_rate: float          # % over rolling window
    failure_count: int
    last_state_change: float
    opens_at_threshold: float
    closes_at_threshold: float

    def __str__(self) -> str:
        return (
            f"[Circuit {self.state}] {self.sub_agent_id}/{self.task_class} "
            f"success_rate={self.success_rate:.1f}%  failures={self.failure_count}"
        )


class AgentChainCircuitBreaker:
    """
    Semantic circuit breaker for A2A sub-agent delegations.

    Unlike an HTTP circuit breaker, this opens based on the
    *semantic validation success rate* — catching the failure
    mode where HTTP 200s are masking wrong outputs.

    Usage::

        breaker = AgentChainCircuitBreaker()

        # After each A2A validation result:
        breaker.record_result(
            sub_agent_id="risk-agent-v2",
            task_class="risk-assessment",
            success=validation_result.valid,
        )

        # Before delegating to a sub-agent:
        if not breaker.allow_request("risk-agent-v2", "risk-assessment"):
            # Circuit is OPEN — route to degraded-mode handler
            return degraded_mode_handler(task)

        # Execute delegation
        result = delegate_to_sub_agent(...)
    """

    def __init__(
        self,
        open_threshold: float = 85.0,       # Open when success rate drops below this %
        close_threshold: float = 95.0,      # Close when recovery probe exceeds this %
        window_size: int = 20,              # Number of recent results to evaluate
        half_open_probe_count: int = 3,     # Canary requests before deciding to close
        on_state_change: Optional[Callable[[CircuitStatus], None]] = None,
    ):
        self.open_threshold = open_threshold
        self.close_threshold = close_threshold
        self.window_size = window_size
        self.half_open_probe_count = half_open_probe_count
        self.on_state_change = on_state_change

        self._states: Dict[str, CircuitState] = {}
        self._results: Dict[str, list] = {}      # key → [bool, ...]
        self._probe_counts: Dict[str, int] = {}
        self._probe_successes: Dict[str, int] = {}
        self._last_change: Dict[str, float] = {}

    # ── Core API ──────────────────────────────────────────────

    def allow_request(self, sub_agent_id: str, task_class: str) -> bool:
        """
        Returns True if the circuit allows delegation to this sub-agent.
        Returns False if the circuit is OPEN (sub-agent is degraded).
        """
        key = self._key(sub_agent_id, task_class)
        state = self._states.get(key, CircuitState.CLOSED)

        if state == CircuitState.CLOSED:
            return True

        if state == CircuitState.OPEN:
            logger.warning(
                "Circuit OPEN for %s/%s — delegation blocked.",
                sub_agent_id,
                task_class,
            )
            return False

        # HALF_OPEN: allow probe requests up to half_open_probe_count
        if state == CircuitState.HALF_OPEN:
            probes = self._probe_counts.get(key, 0)
            if probes < self.half_open_probe_count:
                self._probe_counts[key] = probes + 1
                return True
            return False

        return True

    def record_result(
        self, sub_agent_id: str, task_class: str, success: bool
    ) -> CircuitStatus:
        """
        Record the outcome of a validation check for a sub-agent delegation.
        Triggers state transitions automatically.
        """
        key = self._key(sub_agent_id, task_class)

        window = self._results.setdefault(key, [])
        window.append(success)
        if len(window) > self.window_size:
            window.pop(0)

        state = self._states.get(key, CircuitState.CLOSED)
        success_rate = (sum(window) / len(window)) * 100 if window else 100.0

        # HALF_OPEN probe tracking
        if state == CircuitState.HALF_OPEN and success:
            self._probe_successes[key] = self._probe_successes.get(key, 0) + 1
            if self._probe_successes.get(key, 0) >= self.half_open_probe_count:
                self._transition(key, sub_agent_id, task_class, CircuitState.CLOSED, success_rate)
                self._probe_counts[key] = 0
                self._probe_successes[key] = 0

        elif state == CircuitState.HALF_OPEN and not success:
            # Probe failed — go back to OPEN
            self._transition(key, sub_agent_id, task_class, CircuitState.OPEN, success_rate)
            self._probe_counts[key] = 0
            self._probe_successes[key] = 0

        elif state == CircuitState.CLOSED and success_rate < self.open_threshold:
            self._transition(key, sub_agent_id, task_class, CircuitState.OPEN, success_rate)

        elif state == CircuitState.OPEN and success_rate >= self.close_threshold:
            # Auto-recovery to HALF_OPEN for probe
            self._transition(key, sub_agent_id, task_class, CircuitState.HALF_OPEN, success_rate)

        return self.status(sub_agent_id, task_class)

    def reset(self, sub_agent_id: str, task_class: str) -> None:
        """Manually reset circuit to CLOSED (e.g., after a confirmed fix)."""
        key = self._key(sub_agent_id, task_class)
        self._states[key] = CircuitState.CLOSED
        self._results[key] = []
        self._probe_counts[key] = 0
        self._probe_successes[key] = 0
        logger.info("Circuit manually reset to CLOSED: %s/%s", sub_agent_id, task_class)

    def status(self, sub_agent_id: str, task_class: str) -> CircuitStatus:
        key = self._key(sub_agent_id, task_class)
        window = self._results.get(key, [])
        success_rate = (sum(window) / len(window)) * 100 if window else 100.0
        failures = sum(1 for r in window if not r)

        return CircuitStatus(
            sub_agent_id=sub_agent_id,
            task_class=task_class,
            state=self._states.get(key, CircuitState.CLOSED),
            success_rate=round(success_rate, 1),
            failure_count=failures,
            last_state_change=self._last_change.get(key, 0.0),
            opens_at_threshold=self.open_threshold,
            closes_at_threshold=self.close_threshold,
        )

    # ── Internals ─────────────────────────────────────────────

    def _transition(
        self,
        key: str,
        sub_agent_id: str,
        task_class: str,
        new_state: CircuitState,
        success_rate: float,
    ) -> None:
        old_state = self._states.get(key, CircuitState.CLOSED)
        if old_state == new_state:
            return
        self._states[key] = new_state
        self._last_change[key] = time.time()
        logger.warning(
            "Circuit state change: %s/%s  %s → %s  (success_rate=%.1f%%)",
            sub_agent_id,
            task_class,
            old_state,
            new_state,
            success_rate,
        )
        if self.on_state_change:
            status = self.status(sub_agent_id, task_class)
            try:
                self.on_state_change(status)
            except Exception as exc:  # noqa: BLE001
                logger.error("on_state_change callback error: %s", exc)

    @staticmethod
    def _key(sub_agent_id: str, task_class: str) -> str:
        return f"{sub_agent_id}:{task_class}"
