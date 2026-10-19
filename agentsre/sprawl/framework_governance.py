"""
agentsre.sprawl.framework_governance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Framework Version Governance

Every framework upgrade should be treated as a production deployment.
This module captures pre-upgrade baselines, compares shadow deployments,
and blocks promotion when TIE/DQR drift exceeds acceptable bounds.

The core insight: framework upgrades change the call graph underneath
your agent. Standard CI/CD checks miss this because the framework adds
steps you did not write — retries, fallbacks, context management —
that alter your Tool Invocation Efficiency baseline silently.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class UpgradeDecision(str, Enum):
    PROMOTE = "PROMOTE"          # drift within bounds — safe to promote
    BLOCK = "BLOCK"              # drift exceeded bounds — block promotion
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # need more shadow traffic


@dataclass
class BaselineSnapshot:
    """Pre-upgrade baseline captured before a framework version change."""
    agent_id: str
    task_class: str
    framework_version: str
    tie_baseline: float       # mean tool calls per task
    dqr_baseline: float       # mean decision confidence %
    sample_count: int
    captured_at: float = field(default_factory=time.time)


@dataclass
class ShadowComparison:
    """Comparison between production and shadow (new framework version) baselines."""
    agent_id: str
    task_class: str
    production_version: str
    shadow_version: str
    production_tie: float
    shadow_tie: float
    production_dqr: float
    shadow_dqr: float
    tie_drift_ratio: float      # shadow_tie / production_tie
    dqr_drift_ratio: float      # shadow_dqr / production_dqr
    decision: UpgradeDecision
    block_reason: Optional[str]
    evaluated_at: float = field(default_factory=time.time)

    def __str__(self) -> str:
        icon = "✅" if self.decision == UpgradeDecision.PROMOTE else "🚫"
        return (
            f"{icon} Framework upgrade {self.production_version} → {self.shadow_version} "
            f"[{self.agent_id}/{self.task_class}]\n"
            f"   TIE drift: {self.tie_drift_ratio:.2f}x  "
            f"DQR drift: {self.dqr_drift_ratio:.2f}x  "
            f"Decision: {self.decision.value}"
            + (f"\n   Block reason: {self.block_reason}" if self.block_reason else "")
        )


class FrameworkVersionGovernance:
    """
    Governs framework upgrades by comparing pre/post behavioral baselines.

    Workflow:
        1. Call snapshot_baseline() before any framework upgrade
        2. Deploy new framework version in shadow mode
        3. Record shadow traffic via record_shadow_result()
        4. Call evaluate_upgrade() — get PROMOTE / BLOCK / INSUFFICIENT_DATA
        5. Only promote when PROMOTE is returned

    Usage::

        gov = FrameworkVersionGovernance(
            tie_drift_threshold=1.15,   # block if TIE drifts >15%
            dqr_drift_threshold=0.85,   # block if DQR drops >15%
            min_shadow_samples=50,
        )

        # Before upgrade:
        gov.snapshot_baseline(
            agent_id="payment-processor",
            task_class="payment-routing",
            framework_version="langchain-0.2.x",
            tie_values=[2.1, 2.3, 2.0, 2.4],
            dqr_values=[91.2, 89.5, 92.0, 90.8],
        )

        # After running shadow traffic:
        for task in shadow_tasks:
            gov.record_shadow_result(
                agent_id="payment-processor",
                task_class="payment-routing",
                shadow_version="langchain-0.3.x",
                tie=task.tool_calls,
                dqr=task.confidence * 100,
            )

        result = gov.evaluate_upgrade(
            agent_id="payment-processor",
            task_class="payment-routing",
            production_version="langchain-0.2.x",
            shadow_version="langchain-0.3.x",
        )
        print(result)
    """

    def __init__(
        self,
        tie_drift_threshold: float = 1.15,    # >15% increase blocks upgrade
        dqr_drift_threshold: float = 0.85,    # >15% drop blocks upgrade
        min_shadow_samples: int = 50,
    ):
        self.tie_drift_threshold = tie_drift_threshold
        self.dqr_drift_threshold = dqr_drift_threshold
        self.min_shadow_samples = min_shadow_samples

        self._baselines: Dict[str, BaselineSnapshot] = {}
        self._shadow_tie: Dict[str, List[float]] = {}
        self._shadow_dqr: Dict[str, List[float]] = {}

    # ── Baseline capture ──────────────────────────────────────

    def snapshot_baseline(
        self,
        agent_id: str,
        task_class: str,
        framework_version: str,
        tie_values: List[float],
        dqr_values: List[float],
    ) -> BaselineSnapshot:
        """
        Capture the current production baseline before a framework upgrade.
        Call this the day before deploying the new framework version.
        """
        if not tie_values or not dqr_values:
            raise ValueError("tie_values and dqr_values must not be empty")

        snapshot = BaselineSnapshot(
            agent_id=agent_id,
            task_class=task_class,
            framework_version=framework_version,
            tie_baseline=statistics.mean(tie_values),
            dqr_baseline=statistics.mean(dqr_values),
            sample_count=min(len(tie_values), len(dqr_values)),
        )
        key = self._key(agent_id, task_class)
        self._baselines[key] = snapshot
        return snapshot

    # ── Shadow recording ──────────────────────────────────────

    def record_shadow_result(
        self,
        agent_id: str,
        task_class: str,
        shadow_version: str,
        tie: float,
        dqr: float,
    ) -> None:
        """Record a single task result from the shadow (new framework version)."""
        key = self._key(agent_id, task_class)
        self._shadow_tie.setdefault(key, []).append(tie)
        self._shadow_dqr.setdefault(key, []).append(dqr)

    # ── Upgrade evaluation ────────────────────────────────────

    def evaluate_upgrade(
        self,
        agent_id: str,
        task_class: str,
        production_version: str,
        shadow_version: str,
    ) -> ShadowComparison:
        """
        Compare shadow baselines against the pre-upgrade production snapshot.
        Returns PROMOTE, BLOCK, or INSUFFICIENT_DATA.
        """
        key = self._key(agent_id, task_class)
        baseline = self._baselines.get(key)

        if not baseline:
            raise ValueError(
                f"No baseline snapshot found for {agent_id}/{task_class}. "
                "Call snapshot_baseline() before the upgrade."
            )

        shadow_tie_vals = self._shadow_tie.get(key, [])
        shadow_dqr_vals = self._shadow_dqr.get(key, [])

        if len(shadow_tie_vals) < self.min_shadow_samples:
            return ShadowComparison(
                agent_id=agent_id,
                task_class=task_class,
                production_version=production_version,
                shadow_version=shadow_version,
                production_tie=baseline.tie_baseline,
                shadow_tie=0.0,
                production_dqr=baseline.dqr_baseline,
                shadow_dqr=0.0,
                tie_drift_ratio=0.0,
                dqr_drift_ratio=0.0,
                decision=UpgradeDecision.INSUFFICIENT_DATA,
                block_reason=(
                    f"Need {self.min_shadow_samples} shadow samples, "
                    f"have {len(shadow_tie_vals)}"
                ),
            )

        shadow_tie = statistics.mean(shadow_tie_vals)
        shadow_dqr = statistics.mean(shadow_dqr_vals)
        tie_drift = shadow_tie / baseline.tie_baseline if baseline.tie_baseline else 1.0
        dqr_drift = shadow_dqr / baseline.dqr_baseline if baseline.dqr_baseline else 1.0

        block_reason = None
        if tie_drift > self.tie_drift_threshold:
            block_reason = (
                f"TIE drift {tie_drift:.2f}x exceeds threshold {self.tie_drift_threshold}x "
                f"({baseline.tie_baseline:.1f} → {shadow_tie:.1f} calls/task)"
            )
        elif dqr_drift < self.dqr_drift_threshold:
            block_reason = (
                f"DQR drift {dqr_drift:.2f}x below threshold {self.dqr_drift_threshold}x "
                f"({baseline.dqr_baseline:.1f}% → {shadow_dqr:.1f}%)"
            )

        decision = UpgradeDecision.BLOCK if block_reason else UpgradeDecision.PROMOTE

        return ShadowComparison(
            agent_id=agent_id,
            task_class=task_class,
            production_version=production_version,
            shadow_version=shadow_version,
            production_tie=round(baseline.tie_baseline, 2),
            shadow_tie=round(shadow_tie, 2),
            production_dqr=round(baseline.dqr_baseline, 2),
            shadow_dqr=round(shadow_dqr, 2),
            tie_drift_ratio=round(tie_drift, 3),
            dqr_drift_ratio=round(dqr_drift, 3),
            decision=decision,
            block_reason=block_reason,
        )

    def reset_shadow(self, agent_id: str, task_class: str) -> None:
        """Clear shadow data (e.g., after a failed upgrade, before retry)."""
        key = self._key(agent_id, task_class)
        self._shadow_tie.pop(key, None)
        self._shadow_dqr.pop(key, None)

    @staticmethod
    def _key(agent_id: str, task_class: str) -> str:
        return f"{agent_id}:{task_class}"
