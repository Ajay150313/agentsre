"""
agentsre.control_plane
~~~~~~~~~~~~~~~~~~~~~~
Agent Control Plane SLIs — the orchestration layer above your agents.

Control plane failures produce correlated degradation across multiple
agents simultaneously. Standard per-agent SLIs miss this entirely.

Three SLIs for the control plane layer:
  RAR — Routing Accuracy Rate       (routing logic drift detection)
  RSI — Retry Storm Index           (retry storm early warning)
  DCS — Decomposition Completeness  (subtask coverage validation)

Author: Ajay Devineni
"""

from __future__ import annotations
import time
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class ControlPlaneEvent:
    event_id: str
    event_type: str          # "primary" | "retry" | "decomposition"
    task_class: str
    assigned_agent: Optional[str] = None
    is_correct_routing: Optional[bool] = None
    subtask_coverage: Optional[float] = None   # 0.0–1.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ControlPlaneSLIResult:
    metric: str
    value: float
    unit: str
    task_class: str
    sample_count: int
    breached: bool
    threshold: float
    alert_message: str = ""

    def __str__(self) -> str:
        status = "🔴 BREACH" if self.breached else "🟢 OK"
        return (
            f"[{self.metric}] {self.task_class}: "
            f"{self.value:.1f}{self.unit} "
            f"(n={self.sample_count}) {status}"
        )


class ControlPlaneSLICollector:
    """
    Collects and calculates the three Agent Control Plane SLIs.

    Usage::

        from agentsre.control_plane import ControlPlaneSLICollector, ControlPlaneEvent

        collector = ControlPlaneSLICollector()

        # Record a primary task routing event
        collector.record(ControlPlaneEvent(
            event_id="e-001",
            event_type="primary",
            task_class="payment-routing",
            assigned_agent="agent-alpha",
            is_correct_routing=True,
        ))

        # Record a retry event (from control plane retry logic)
        collector.record(ControlPlaneEvent(
            event_id="e-002",
            event_type="retry",
            task_class="payment-routing",
        ))

        # Record a decomposition completeness event
        collector.record(ControlPlaneEvent(
            event_id="e-003",
            event_type="decomposition",
            task_class="payment-routing",
            subtask_coverage=0.85,  # 85% of requirements covered
        ))

        results = collector.collect("payment-routing")
        for r in results:
            print(r)
    """

    def __init__(
        self,
        rar_threshold: float = 85.0,      # alert if RAR < 85%
        rsi_threshold: float = 0.50,      # alert if RSI > 0.50
        dcs_threshold: float = 80.0,      # alert if DCS < 80%
        window_seconds: int = 900,        # 15-minute rolling window
    ):
        self.rar_threshold = rar_threshold
        self.rsi_threshold = rsi_threshold
        self.dcs_threshold = dcs_threshold
        self.window_seconds = window_seconds
        self._events: Dict[str, List[ControlPlaneEvent]] = {}

    def record(self, event: ControlPlaneEvent) -> None:
        cls = event.task_class
        self._events.setdefault(cls, []).append(event)
        self._evict(cls)

    def collect(self, task_class: str) -> List[ControlPlaneSLIResult]:
        return [
            self._rar(task_class),
            self._rsi(task_class),
            self._dcs(task_class),
        ]

    def breached(self, task_class: str) -> List[ControlPlaneSLIResult]:
        return [r for r in self.collect(task_class) if r.breached]

    def _rar(self, task_class: str) -> ControlPlaneSLIResult:
        events = [e for e in self._get(task_class)
                  if e.event_type == "primary" and e.is_correct_routing is not None]
        if not events:
            return self._empty("RoutingAccuracyRate", "%", self.rar_threshold, task_class)
        value = (sum(1 for e in events if e.is_correct_routing) / len(events)) * 100
        breached = value < self.rar_threshold
        return ControlPlaneSLIResult(
            metric="RoutingAccuracyRate", value=round(value, 1), unit="%",
            task_class=task_class, sample_count=len(events),
            breached=breached, threshold=self.rar_threshold,
            alert_message=f"Routing accuracy {value:.1f}% below threshold {self.rar_threshold}%" if breached else "",
        )

    def _rsi(self, task_class: str) -> ControlPlaneSLIResult:
        events = self._get(task_class)
        primary = sum(1 for e in events if e.event_type == "primary")
        retries = sum(1 for e in events if e.event_type == "retry")
        value = (retries / primary) if primary > 0 else 0.0
        breached = value > self.rsi_threshold
        return ControlPlaneSLIResult(
            metric="RetryStormIndex", value=round(value, 3), unit="x",
            task_class=task_class, sample_count=primary + retries,
            breached=breached, threshold=self.rsi_threshold,
            alert_message=f"RSI {value:.2f}x — retry storm in progress" if value > 1.0
                         else f"RSI {value:.2f}x — approaching storm threshold" if breached else "",
        )

    def _dcs(self, task_class: str) -> ControlPlaneSLIResult:
        events = [e for e in self._get(task_class)
                  if e.event_type == "decomposition" and e.subtask_coverage is not None]
        if not events:
            return self._empty("DecompositionCompletenessScore", "%", self.dcs_threshold, task_class)
        value = statistics.mean(e.subtask_coverage for e in events) * 100
        breached = value < self.dcs_threshold
        return ControlPlaneSLIResult(
            metric="DecompositionCompletenessScore", value=round(value, 1), unit="%",
            task_class=task_class, sample_count=len(events),
            breached=breached, threshold=self.dcs_threshold,
            alert_message=f"Decomposition coverage {value:.1f}% — task requirements not fully covered" if breached else "",
        )

    def _get(self, task_class: str) -> List[ControlPlaneEvent]:
        self._evict(task_class)
        return list(self._events.get(task_class, []))

    def _evict(self, task_class: str) -> None:
        cutoff = time.time() - self.window_seconds
        q = self._events.get(task_class, [])
        self._events[task_class] = [e for e in q if e.timestamp >= cutoff]

    @staticmethod
    def _empty(metric, unit, threshold, task_class) -> ControlPlaneSLIResult:
        return ControlPlaneSLIResult(
            metric=metric, value=0.0, unit=unit, task_class=task_class,
            sample_count=0, breached=False, threshold=threshold,
        )
