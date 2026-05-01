"""
agentsre.metrics
~~~~~~~~~~~~~~~~
The four SLIs for agentic AI reliability that standard observability misses.

  DQR  - Decision Quality Rate        (semantic drift detection)
  TIE  - Tool Invocation Efficiency   (compensation early-warning)
  HER  - Human Escalation Rate        (direct reliability proxy)
  AQDD - Approval Queue Depth Drift   (human-blocked failure mode)
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional


# ──────────────────────────────────────────────────────────────
# Shared primitives
# ──────────────────────────────────────────────────────────────

@dataclass
class TaskRecord:
    task_id: str
    task_class: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: int = 0
    required_escalation: bool = False
    pending_approval: bool = False
    decision_confidence: float = 1.0  # 0.0–1.0
    completed: bool = False


@dataclass
class SLIResult:
    name: str
    value: float
    unit: str
    task_class: str
    window_seconds: int
    sample_count: int
    baseline: Optional[float]
    drift_ratio: Optional[float]  # value / baseline; None if no baseline yet
    breached: bool
    threshold: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        breach = " ⚠ BREACHED" if self.breached else ""
        drift = f"  drift={self.drift_ratio:.2f}x" if self.drift_ratio else ""
        return (
            f"[{self.name}] {self.task_class}: "
            f"{self.value:.1f}{self.unit} "
            f"(n={self.sample_count}, threshold={self.threshold}{self.unit})"
            f"{drift}{breach}"
        )


# ──────────────────────────────────────────────────────────────
# Sliding-window store (in-memory, per task_class)
# ──────────────────────────────────────────────────────────────

class _WindowStore:
    """Keeps the last `window_seconds` of TaskRecords per task_class."""

    def __init__(self, window_seconds: int = 3600):
        self.window_seconds = window_seconds
        self._records: Dict[str, Deque[TaskRecord]] = {}

    def add(self, record: TaskRecord) -> None:
        cls = record.task_class
        if cls not in self._records:
            self._records[cls] = deque()
        self._records[cls].append(record)
        self._evict(cls)

    def get(self, task_class: str) -> List[TaskRecord]:
        self._evict(task_class)
        return list(self._records.get(task_class, []))

    def task_classes(self) -> List[str]:
        return list(self._records.keys())

    def _evict(self, task_class: str) -> None:
        cutoff = time.time() - self.window_seconds
        q = self._records.get(task_class, deque())
        while q and q[0].timestamp < cutoff:
            q.popleft()


# ──────────────────────────────────────────────────────────────
# Baseline store  (7-day rolling averages per task_class)
# ──────────────────────────────────────────────────────────────

class BaselineStore:
    """
    Stores per-metric, per-task-class baselines.
    In production replace this with DynamoDB / Redis.
    """

    def __init__(self) -> None:
        self._baselines: Dict[str, Dict[str, float]] = {}

    def update(self, task_class: str, metric: str, value: float) -> None:
        if task_class not in self._baselines:
            self._baselines[task_class] = {}
        prev = self._baselines[task_class].get(metric)
        # Exponential moving average (α=0.1) once a baseline exists
        if prev is None:
            self._baselines[task_class][metric] = value
        else:
            self._baselines[task_class][metric] = 0.9 * prev + 0.1 * value

    def get(self, task_class: str, metric: str) -> Optional[float]:
        return self._baselines.get(task_class, {}).get(metric)


# ──────────────────────────────────────────────────────────────
# SLI calculators
# ──────────────────────────────────────────────────────────────

class DecisionQualityRate:
    """
    DQR — percentage of decisions within expected behavioral bounds.

    Uses the mean `decision_confidence` of completed tasks in the window.
    A sudden drop is a leading indicator of tool degradation or prompt drift.

    Threshold: alert when DQR < `threshold` (default 85 %).
    """

    name = "DecisionQualityRate"

    def __init__(
        self,
        store: _WindowStore,
        baseline_store: BaselineStore,
        threshold: float = 85.0,
        window_seconds: int = 3600,
    ):
        self._store = store
        self._baseline = baseline_store
        self.threshold = threshold
        self.window_seconds = window_seconds

    def calculate(self, task_class: str) -> SLIResult:
        records = [r for r in self._store.get(task_class) if r.completed]
        if not records:
            return self._empty(task_class)

        value = statistics.mean(r.decision_confidence for r in records) * 100
        self._baseline.update(task_class, self.name, value)
        baseline = self._baseline.get(task_class, self.name)
        drift = (value / baseline) if baseline else None

        return SLIResult(
            name=self.name,
            value=round(value, 2),
            unit="%",
            task_class=task_class,
            window_seconds=self.window_seconds,
            sample_count=len(records),
            baseline=round(baseline, 2) if baseline else None,
            drift_ratio=round(drift, 3) if drift else None,
            breached=value < self.threshold,
            threshold=self.threshold,
        )

    def _empty(self, task_class: str) -> SLIResult:
        return SLIResult(
            name=self.name, value=0.0, unit="%", task_class=task_class,
            window_seconds=self.window_seconds, sample_count=0,
            baseline=None, drift_ratio=None, breached=False,
            threshold=self.threshold,
        )


class ToolInvocationEfficiency:
    """
    TIE — mean MCP tool calls per completed task vs. rolling baseline.

    A climbing ratio means the agent is compensating for something —
    ambiguous context, degraded tool responses, prompt drift.

    Threshold: alert when TIE > `baseline × multiplier` (default 1.5×).
    """

    name = "ToolInvocationEfficiency"

    def __init__(
        self,
        store: _WindowStore,
        baseline_store: BaselineStore,
        drift_multiplier: float = 1.5,
        window_seconds: int = 3600,
    ):
        self._store = store
        self._baseline = baseline_store
        self.drift_multiplier = drift_multiplier
        self.window_seconds = window_seconds

    def calculate(self, task_class: str) -> SLIResult:
        records = [r for r in self._store.get(task_class) if r.completed]
        if not records:
            return self._empty(task_class)

        value = statistics.mean(r.tool_calls for r in records)
        self._baseline.update(task_class, self.name, value)
        baseline = self._baseline.get(task_class, self.name)
        drift = (value / baseline) if baseline else None
        threshold_abs = (baseline * self.drift_multiplier) if baseline else float("inf")

        return SLIResult(
            name=self.name,
            value=round(value, 2),
            unit=" calls/task",
            task_class=task_class,
            window_seconds=self.window_seconds,
            sample_count=len(records),
            baseline=round(baseline, 2) if baseline else None,
            drift_ratio=round(drift, 3) if drift else None,
            breached=bool(drift and drift >= self.drift_multiplier),
            threshold=self.drift_multiplier,
        )

    def _empty(self, task_class: str) -> SLIResult:
        return SLIResult(
            name=self.name, value=0.0, unit=" calls/task", task_class=task_class,
            window_seconds=self.window_seconds, sample_count=0,
            baseline=None, drift_ratio=None, breached=False,
            threshold=self.drift_multiplier,
        )


class HumanEscalationRate:
    """
    HER — percentage of tasks requiring human intervention.

    The most direct proxy for agent reliability. Set a budget.
    If your agent escalates 2× more than its 7-day baseline,
    reliability is degrading — even if every health check is green.

    Threshold: alert when HER > `threshold` (default 5 %).
    """

    name = "HumanEscalationRate"

    def __init__(
        self,
        store: _WindowStore,
        baseline_store: BaselineStore,
        threshold: float = 5.0,
        window_seconds: int = 604800,  # 7 days default
    ):
        self._store = store
        self._baseline = baseline_store
        self.threshold = threshold
        self.window_seconds = window_seconds

    def calculate(self, task_class: str) -> SLIResult:
        records = self._store.get(task_class)
        if not records:
            return self._empty(task_class)

        escalated = sum(1 for r in records if r.required_escalation)
        value = (escalated / len(records)) * 100
        self._baseline.update(task_class, self.name, value)
        baseline = self._baseline.get(task_class, self.name)
        drift = (value / baseline) if baseline and baseline > 0 else None

        return SLIResult(
            name=self.name,
            value=round(value, 2),
            unit="%",
            task_class=task_class,
            window_seconds=self.window_seconds,
            sample_count=len(records),
            baseline=round(baseline, 2) if baseline else None,
            drift_ratio=round(drift, 3) if drift else None,
            breached=value > self.threshold,
            threshold=self.threshold,
        )

    def _empty(self, task_class: str) -> SLIResult:
        return SLIResult(
            name=self.name, value=0.0, unit="%", task_class=task_class,
            window_seconds=self.window_seconds, sample_count=0,
            baseline=None, drift_ratio=None, breached=False,
            threshold=self.threshold,
        )


class ApprovalQueueDepthDrift:
    """
    AQDD — Approval Queue Depth Drift (Ajay Devineni, 2026)

    The failure mode standard SLO burn-rate alerts miss entirely:
    tasks submitted, never approved, queue silently growing.
    Standard SLOs assume work eventually completes — AQDD tracks
    the queue depth as a time-series, not a completion metric.

    Breaches when current depth > baseline × `drift_multiplier`
    for longer than `sustained_minutes`.
    """

    name = "ApprovalQueueDepthDrift"

    def __init__(
        self,
        store: _WindowStore,
        baseline_store: BaselineStore,
        drift_multiplier: float = 2.0,
        sustained_minutes: int = 30,
        window_seconds: int = 3600,
    ):
        self._store = store
        self._baseline = baseline_store
        self.drift_multiplier = drift_multiplier
        self.sustained_minutes = sustained_minutes
        self.window_seconds = window_seconds
        # Tracks how long we've been above threshold per task_class
        self._breach_start: Dict[str, Optional[float]] = {}

    def calculate(self, task_class: str) -> SLIResult:
        records = self._store.get(task_class)
        pending = sum(1 for r in records if r.pending_approval and not r.completed)
        value = float(pending)

        self._baseline.update(task_class, self.name, value)
        baseline = self._baseline.get(task_class, self.name)
        drift = (value / baseline) if baseline and baseline > 0 else None
        threshold_abs = (baseline * self.drift_multiplier) if baseline else float("inf")

        above_threshold = bool(drift and drift >= self.drift_multiplier)
        now = time.time()

        if above_threshold:
            if self._breach_start.get(task_class) is None:
                self._breach_start[task_class] = now
            sustained_secs = now - self._breach_start[task_class]
            breached = sustained_secs >= self.sustained_minutes * 60
        else:
            self._breach_start[task_class] = None
            breached = False

        return SLIResult(
            name=self.name,
            value=value,
            unit=" pending",
            task_class=task_class,
            window_seconds=self.window_seconds,
            sample_count=len(records),
            baseline=round(baseline, 2) if baseline else None,
            drift_ratio=round(drift, 3) if drift else None,
            breached=breached,
            threshold=self.drift_multiplier,
        )

    def _empty(self, task_class: str) -> SLIResult:
        return SLIResult(
            name=self.name, value=0.0, unit=" pending", task_class=task_class,
            window_seconds=self.window_seconds, sample_count=0,
            baseline=None, drift_ratio=None, breached=False,
            threshold=self.drift_multiplier,
        )


# ──────────────────────────────────────────────────────────────
# Unified collector — single entry point
# ──────────────────────────────────────────────────────────────

class AgentSLICollector:
    """
    Collect all four SLIs for every task class in the store.

    Usage::

        from agentsre import AgentSLICollector, TaskRecord

        collector = AgentSLICollector()
        collector.record(TaskRecord(
            task_id="t-001",
            task_class="payment-routing",
            tool_calls=3,
            required_escalation=False,
            decision_confidence=0.91,
            completed=True,
        ))
        results = collector.collect("payment-routing")
        for r in results:
            print(r)
    """

    def __init__(self, window_seconds: int = 3600):
        self._store = _WindowStore(window_seconds)
        self._baseline = BaselineStore()
        self._dqr = DecisionQualityRate(self._store, self._baseline)
        self._tie = ToolInvocationEfficiency(self._store, self._baseline)
        self._her = HumanEscalationRate(self._store, self._baseline)
        self._aqdd = ApprovalQueueDepthDrift(self._store, self._baseline)

    def record(self, task: TaskRecord) -> None:
        """Add a task record to the rolling window."""
        self._store.add(task)

    def collect(self, task_class: str) -> List[SLIResult]:
        """Return all four SLI results for a given task class."""
        return [
            self._dqr.calculate(task_class),
            self._tie.calculate(task_class),
            self._her.calculate(task_class),
            self._aqdd.calculate(task_class),
        ]

    def collect_all(self) -> Dict[str, List[SLIResult]]:
        """Return SLI results for every task class seen so far."""
        return {cls: self.collect(cls) for cls in self._store.task_classes()}

    def breached(self, task_class: str) -> List[SLIResult]:
        """Return only SLIs currently in breach for a given task class."""
        return [r for r in self.collect(task_class) if r.breached]
