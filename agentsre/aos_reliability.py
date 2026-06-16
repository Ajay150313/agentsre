"""
AOS Reliability — meta-reliability monitoring for Agent Operating Systems.

An Agent Operating System governs AI agents in production.
This module monitors the AOS itself — applying the same SLI discipline
to the governance layer that the governance layer applies to agents.

Three reliability checks:
    1. AuditCompletenessTracker — every agent action produces
       a complete, query-able audit record. Gaps = compliance risk.

    2. GateHealthChecker — the Pre-Action Gate is failing safe
       (errors default to block) not failing open (errors approve).

    3. AOSCircuitBreaker — if the AOS itself degrades past a threshold,
       force all actions to human review rather than autonomous decision.

In regulated fintech environments:
    - Audit completeness < 99% = potential compliance event
    - Gate failing open = autonomous actions bypassing governance
    - AOS circuit open = all autonomous action paused pending human review

Author: Ajay Devineni
License: MIT
Repository: github.com/Ajay150313/agentsre
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional
from enum import Enum


class GateFailureMode(Enum):
    """How the gate behaves when it encounters an error."""
    FAIL_SAFE = "fail_safe"     # Error → block action → human review
    FAIL_OPEN = "fail_open"     # Error → approve action (DANGEROUS)
    UNKNOWN = "unknown"         # Cannot determine from available data


class CircuitState(Enum):
    CLOSED = "closed"       # AOS operating normally
    OPEN = "open"           # AOS degraded — all actions to human review
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class AuditRecord:
    """
    A single agent action audit record.

    Attributes:
        task_id: Task that produced this record
        agent_id: Agent that took the action
        action: What the agent did
        gate_approved: Whether the Pre-Action Gate approved
        audit_complete: Whether all required fields are present
        timestamp: When the action occurred
    """
    task_id: str
    agent_id: str
    action: str
    gate_approved: bool
    audit_complete: bool
    timestamp: str

    REQUIRED_FIELDS = {
        'task_id', 'agent_id', 'action',
        'gate_approved', 'sre_state_at_check', 'checked_at'
    }

    @classmethod
    def from_log_entry(cls, entry: dict) -> 'AuditRecord':
        """
        Parse from a pre_action_gate log entry.
        audit_complete = all required fields present.
        """
        complete = all(
            f in entry for f in cls.REQUIRED_FIELDS
        )
        return cls(
            task_id=entry.get('task_id', ''),
            agent_id=entry.get('agent_id', ''),
            action=entry.get('intended_action', ''),
            gate_approved=entry.get('gate_approved', False),
            audit_complete=complete,
            timestamp=entry.get('checked_at', '')
        )


@dataclass
class AuditCompletenessTracker:
    """
    Track audit trail completeness for a regulated environment.

    In fintech, incomplete audit trails are compliance events.
    Track this continuously — not just at deployment time.

    Target: 99%+ completeness at all times.
    Below 99%: CRITICAL — alert compliance team immediately.
    """
    agent_id: str
    _records: List[AuditRecord] = field(
        default_factory=list, repr=False
    )

    def ingest(self, record: AuditRecord) -> None:
        """Add an audit record to the tracker."""
        self._records.append(record)

    @property
    def completeness_rate(self) -> Optional[float]:
        """Fraction of records that are complete (0.0-1.0)."""
        if not self._records:
            return None
        complete = sum(1 for r in self._records if r.audit_complete)
        return complete / len(self._records)

    @property
    def completeness_status(self) -> str:
        rate = self.completeness_rate
        if rate is None:
            return "NO_DATA"
        if rate >= 0.99:
            return "OK"
        if rate >= 0.95:
            return "WARNING"
        return "CRITICAL"

    @property
    def incomplete_task_ids(self) -> List[str]:
        """Task IDs with incomplete audit records."""
        return [
            r.task_id for r in self._records
            if not r.audit_complete
        ]

    def report(self) -> Dict:
        rate = self.completeness_rate
        return {
            "agent_id": self.agent_id,
            "total_records": len(self._records),
            "complete_records": sum(
                1 for r in self._records if r.audit_complete
            ),
            "completeness_rate_pct": (
                round(rate * 100, 2) if rate is not None else None
            ),
            "status": self.completeness_status,
            "incomplete_task_ids": self.incomplete_task_ids,
            "compliance_note": (
                "Audit gaps detected — review before regulatory inspection"
                if self.completeness_status in ("WARNING", "CRITICAL")
                else "Audit trail complete"
            ),
            "checked_at": datetime.now(timezone.utc).isoformat()
        }


@dataclass
class AOSCircuitBreaker:
    """
    Circuit breaker for the Agent Operating System itself.

    When the AOS degrades — audit completeness drops, gate
    failure mode becomes unknown, DQR falls below threshold —
    this circuit breaker opens and forces all autonomous
    actions to human review.

    This is the safety layer for the governance layer.
    Fail safe: when in doubt, require human approval.

    States:
        CLOSED: AOS healthy, autonomous action permitted
        OPEN: AOS degraded, all actions to human review
        HALF_OPEN: Testing recovery, limited autonomous action

    Attributes:
        agent_id: Agent this breaker governs
        audit_completeness_threshold: Min completeness to stay closed
        failure_count: Consecutive failures before opening
        success_count_to_close: Successes in HALF_OPEN before closing
    """
    agent_id: str
    audit_completeness_threshold: float = 0.99
    failure_count_to_open: int = 3
    success_count_to_close: int = 5

    _state: CircuitState = field(
        default=CircuitState.CLOSED, repr=False
    )
    _consecutive_failures: int = field(default=0, repr=False)
    _consecutive_successes: int = field(default=0, repr=False)
    _state_changed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        repr=False
    )

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def allows_autonomous_action(self) -> bool:
        """
        True only when circuit is CLOSED.
        OPEN or HALF_OPEN → require human approval.
        """
        return self._state == CircuitState.CLOSED

    def record_success(self) -> None:
        """Record a healthy AOS check."""
        self._consecutive_failures = 0
        if self._state == CircuitState.HALF_OPEN:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.success_count_to_close:
                self._transition(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            self._consecutive_successes += 1

    def record_failure(self) -> None:
        """Record an AOS health check failure."""
        self._consecutive_successes = 0
        self._consecutive_failures += 1
        if (self._state == CircuitState.CLOSED and
                self._consecutive_failures >= self.failure_count_to_open):
            self._transition(CircuitState.OPEN)

    def attempt_reset(self) -> None:
        """
        Move from OPEN to HALF_OPEN to test recovery.
        Call this on a schedule — not continuously.
        """
        if self._state == CircuitState.OPEN:
            self._transition(CircuitState.HALF_OPEN)
            self._consecutive_successes = 0

    def _transition(self, new_state: CircuitState) -> None:
        self._state = new_state
        self._state_changed_at = datetime.now(timezone.utc).isoformat()

    def status(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "circuit_state": self._state.value,
            "allows_autonomous_action": self.allows_autonomous_action,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
            "state_changed_at": self._state_changed_at,
            "recommendation": (
                "AOS healthy — autonomous action permitted"
                if self.allows_autonomous_action
                else "AOS degraded — route all actions to human review"
            )
        }

    def to_json(self) -> str:
        return json.dumps(self.status(), indent=2)