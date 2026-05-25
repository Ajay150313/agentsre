# agentsre/pre_action_gate.py
"""
Pre-Action SRE Gate — SLI-gated authorization for autonomous agent actions.

Agents skip the judgment call chaos engineering was built around:
checking whether the system has capacity to absorb an action RIGHT NOW.

Human engineers check this before running experiments.
Your agents should check it before acting autonomously.

Three gate checks using signals already in your SRE stack:
    1. Error budget remaining — does the system have headroom?
    2. AQDD (Approval Queue Depth Drift) — can humans course-correct?
    3. HER trend — is the agent already outside its reliable envelope?

If any check fails: agent escalates per ARO record. Does not act.
Every check — approved or blocked — logs a structured audit record.

This converts your existing SLIs from passive observability signals
into active action authorization signals.

Author: Ajay Devineni
License: MIT
Repository: github.com/Ajay150313/agentsre
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


# Default thresholds — calibrate per agent/task class in shadow mode
DEFAULT_ERROR_BUDGET_MIN_PCT = 20.0   # Don't act when budget is critically low
DEFAULT_AQDD_MAX_DEPTH = 3            # Don't act when approval queue is backed up
DEFAULT_HER_MAX_TREND_PCT = 15.0      # Don't act when agent is escalating too much


@dataclass
class SREGateResult:
    """
    Result of a Pre-Action SRE Gate evaluation.

    If approved is False — agent must NOT proceed with autonomous action.
    Route to escalation_path from the agent's ARO registration.

    Attributes:
        approved: True = proceed. False = escalate, do not act.
        blocking_check: Which check failed ('error_budget'/'aqdd'/'her_trend')
        error_budget_pct: Error budget remaining at check time
        aqdd_depth: Approval queue depth at check time
        her_trend_pct: Agent HER trend at check time
        recommendation: Human-readable guidance for the agent/owner
        checked_at: ISO timestamp of gate evaluation
    """
    approved: bool
    blocking_check: Optional[str]
    error_budget_pct: float
    aqdd_depth: int
    her_trend_pct: float
    recommendation: str
    checked_at: str


class PreActionSREGate:
    """
    Pre-Action SRE Gate for autonomous agent action authorization.

    Instantiate once per agent or once per action class.
    Call check() before any autonomous write, remediation,
    scale event, or config change.

    Thresholds must be calibrated empirically per agent and task class.
    Use the same 30-day shadow mode protocol as HER and RTD baselines.
    Default thresholds are conservative starting points only.
    """

    def __init__(self,
                 error_budget_min_pct: float = DEFAULT_ERROR_BUDGET_MIN_PCT,
                 aqdd_max_depth: int = DEFAULT_AQDD_MAX_DEPTH,
                 her_max_trend_pct: float = DEFAULT_HER_MAX_TREND_PCT):
        self.error_budget_min_pct = error_budget_min_pct
        self.aqdd_max_depth = aqdd_max_depth
        self.her_max_trend_pct = her_max_trend_pct

    def check(self,
              agent_id: str,
              intended_action: str,
              error_budget_pct: float,
              aqdd_depth: int,
              her_trend_pct: float) -> SREGateResult:
        """
        Evaluate whether autonomous action is safe given current SRE state.

        Call this before every autonomous state-changing action.
        If result.approved is False — escalate, do not act.

        Args:
            agent_id: Agent requesting authorization
            intended_action: What the agent plans to do
            error_budget_pct: Current error budget remaining (0-100)
            aqdd_depth: Current pending approval count
            her_trend_pct: Agent's recent HER rate (0-100)

        Returns:
            SREGateResult with approval decision and structured reasoning
        """
        ts = datetime.now(timezone.utc).isoformat()

        if error_budget_pct < self.error_budget_min_pct:
            return SREGateResult(
                approved=False,
                blocking_check="error_budget",
                error_budget_pct=error_budget_pct,
                aqdd_depth=aqdd_depth,
                her_trend_pct=her_trend_pct,
                recommendation=(
                    f"Error budget at {error_budget_pct:.1f}% — "
                    f"below minimum {self.error_budget_min_pct}%. "
                    "System cannot absorb unexpected outcomes. "
                    "Escalate to human owner per ARO record."
                ),
                checked_at=ts
            )

        if aqdd_depth > self.aqdd_max_depth:
            return SREGateResult(
                approved=False,
                blocking_check="aqdd",
                error_budget_pct=error_budget_pct,
                aqdd_depth=aqdd_depth,
                her_trend_pct=her_trend_pct,
                recommendation=(
                    f"Approval queue depth {aqdd_depth} exceeds "
                    f"maximum {self.aqdd_max_depth}. "
                    "Human oversight is backed up. "
                    "Mistakes cannot be caught in time. Hold action."
                ),
                checked_at=ts
            )

        if her_trend_pct > self.her_max_trend_pct:
            return SREGateResult(
                approved=False,
                blocking_check="her_trend",
                error_budget_pct=error_budget_pct,
                aqdd_depth=aqdd_depth,
                her_trend_pct=her_trend_pct,
                recommendation=(
                    f"HER trend at {her_trend_pct:.1f}% — "
                    f"above threshold {self.her_max_trend_pct}%. "
                    "Agent is outside its reliable operating envelope. "
                    "Escalate rather than act autonomously."
                ),
                checked_at=ts
            )

        return SREGateResult(
            approved=True,
            blocking_check=None,
            error_budget_pct=error_budget_pct,
            aqdd_depth=aqdd_depth,
            her_trend_pct=her_trend_pct,
            recommendation="Autonomous action cleared. Proceed within registered blast radius.",
            checked_at=ts
        )

    def to_audit_log(self, agent_id: str,
                     intended_action: str,
                     result: SREGateResult) -> dict:
        """
        Structured audit record for every gate evaluation.

        Log this for EVERY check — approved and blocked.
        This is your postmortem data: the SRE state snapshot
        that preceded any autonomous action.
        """
        return {
            "trace_type": "pre_action_gate",
            "agent_id": agent_id,
            "intended_action": intended_action,
            "gate_approved": result.approved,
            "blocking_check": result.blocking_check,
            "sre_state_at_check": {
                "error_budget_pct": result.error_budget_pct,
                "aqdd_depth": result.aqdd_depth,
                "her_trend_pct": result.her_trend_pct,
            },
            "recommendation": result.recommendation,
            "thresholds_applied": {
                "error_budget_min_pct": self.error_budget_min_pct,
                "aqdd_max_depth": self.aqdd_max_depth,
                "her_max_trend_pct": self.her_max_trend_pct,
            },
            "checked_at": result.checked_at,
        }

    def to_json(self, agent_id: str,
                intended_action: str,
                result: SREGateResult) -> str:
        return json.dumps(
            self.to_audit_log(agent_id, intended_action, result),
            indent=2
        )