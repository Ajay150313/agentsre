"""
Agent Dependency Risk Score (ADRS) — supply chain governance for AI SRE agents.

When an AI SRE agent becomes your first responder to production incidents,
it is no longer a tool sitting beside your production stack.
It is a dependency inside your production stack.

We have mature processes for governing production dependencies:
version pinning, changelog tracking, breaking change detection,
rollback procedures, SLA requirements.

We have almost none of that for AI SRE agents.

ADRS is a composite score measuring how well-governed an AI SRE
agent is as a production dependency. It combines four signals:

    BRE  (Blast Radius Exposure)     — how much damage if behavior drifts?
    VDR  (Version Drift Rate)        — how often does the agent change without your knowledge?
    VC   (Verification Coverage)     — what fraction of decisions are actively verified?
    RT   (Recovery Time)             — how fast can you revert to human-only operations?

ADRS = (BRE × 0.35) + (VDR × 0.25) + (VC_inv × 0.25) + (RT × 0.15)

Score interpretation:
    0-3:  LOW      — well-governed production dependency
    4-6:  MEDIUM   — some gaps, review recommended
    7-8:  HIGH     — significant gaps, formal remediation required
    9-10: CRITICAL — high-risk unmanaged dependency, restrict scope immediately

Author: Ajay Devineni
License: MIT
Repository: github.com/Ajay150313/agentsre
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


@dataclass
class ADRSSignals:
    """
    Four input signals for ADRS calculation.

    Attributes:
        blast_radius_exposure: 0-10. How many/what type of systems
            can this agent touch? 0=read-only narrow, 10=IAM+DB+billing.
        version_drift_rate: 0-10. How often does agent change without
            team knowledge and re-validation? 0=all changes reviewed,
            10=vendor updates with zero team awareness.
        verification_coverage_inverse: 0-10. Inverse of ACR.
            0=all decisions verified, 10=zero verification (pure ACR).
        recovery_time: 0-10. How long to detect drift and revert?
            0=EvalPipeline+runbook+drill all in place, 10=none of them.
    """
    blast_radius_exposure: float        # BRE: 0-10
    version_drift_rate: float           # VDR: 0-10
    verification_coverage_inverse: float # VC_inv: 0-10 (inverse of coverage)
    recovery_time: float                # RT: 0-10

    def validate(self) -> list:
        errors = []
        for name, val in [
            ("blast_radius_exposure", self.blast_radius_exposure),
            ("version_drift_rate", self.version_drift_rate),
            ("verification_coverage_inverse", self.verification_coverage_inverse),
            ("recovery_time", self.recovery_time),
        ]:
            if not 0 <= val <= 10:
                errors.append(f"{name} must be 0-10, got {val}")
        return errors


@dataclass
class ADRSResult:
    """
    ADRS calculation result with signal breakdown and recommendation.

    Attributes:
        agent_id: Agent that was scored
        adrs: Composite score (0-10)
        risk_level: LOW / MEDIUM / HIGH / CRITICAL
        signal_breakdown: Score and weighted contribution per signal
        recommendation: Specific remediation guidance
        calculated_at: ISO timestamp
    """
    agent_id: str
    adrs: float
    risk_level: str
    signal_breakdown: Dict
    recommendation: str
    calculated_at: str

    @property
    def requires_immediate_action(self) -> bool:
        """True when agent should be restricted pending remediation."""
        return self.risk_level in ('HIGH', 'CRITICAL')

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "adrs": self.adrs,
            "risk_level": self.risk_level,
            "signal_breakdown": self.signal_breakdown,
            "recommendation": self.recommendation,
            "requires_immediate_action": self.requires_immediate_action,
            "calculated_at": self.calculated_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# Signal weights — must sum to 1.0
_WEIGHTS = {
    "blast_radius_exposure":         0.35,
    "version_drift_rate":            0.25,
    "verification_coverage_inverse": 0.25,
    "recovery_time":                 0.15,
}


def calculate_adrs(agent_id: str, signals: ADRSSignals) -> ADRSResult:
    """
    Calculate Agent Dependency Risk Score.

    Args:
        agent_id: Identifier of the agent being scored
        signals: Four ADRSSignals inputs (each 0-10)

    Returns:
        ADRSResult with composite score, risk level, and recommendation.

    Raises:
        ValueError: If any signal is outside 0-10 range.
    """
    errors = signals.validate()
    if errors:
        raise ValueError(f"Invalid ADRS signals: {errors}")

    signal_values = {
        "blast_radius_exposure":         signals.blast_radius_exposure,
        "version_drift_rate":            signals.version_drift_rate,
        "verification_coverage_inverse": signals.verification_coverage_inverse,
        "recovery_time":                 signals.recovery_time,
    }

    breakdown = {}
    adrs = 0.0
    for signal, value in signal_values.items():
        weight = _WEIGHTS[signal]
        contribution = round(value * weight, 3)
        adrs += contribution
        breakdown[signal] = {
            "score": value,
            "weight": weight,
            "contribution": contribution,
        }
    adrs = round(adrs, 2)

    if adrs >= 9.0:
        risk = "CRITICAL"
        rec = (
            "Agent is a high-risk unmanaged production dependency. "
            "Restrict to read-only / shadow mode immediately. "
            "Required before re-enabling autonomous operation: "
            "(1) Reduce blast radius to minimum viable scope. "
            "(2) Implement change notification for all model/config updates. "
            "(3) Document and practice revert-to-human-only runbook. "
            "(4) Achieve ACR < 5% for P1/P2 incidents over 30 days."
        )
    elif adrs >= 7.0:
        risk = "HIGH"
        rec = (
            "Significant dependency governance gaps. "
            "30-day formal remediation plan required. "
            "Focus on highest-scoring signal first: "
            f"{max(breakdown, key=lambda k: breakdown[k]['contribution'])}."
        )
    elif adrs >= 4.0:
        risk = "MEDIUM"
        rec = (
            "Some governance gaps. "
            "Review in next sprint. Address highest-scoring signal: "
            f"{max(breakdown, key=lambda k: breakdown[k]['contribution'])}."
        )
    else:
        risk = "LOW"
        rec = (
            "Well-governed production dependency. "
            "Quarterly review recommended. "
            "Maintain current EvalPipeline cadence and revert drill schedule."
        )

    return ADRSResult(
        agent_id=agent_id,
        adrs=adrs,
        risk_level=risk,
        signal_breakdown=breakdown,
        recommendation=rec,
        calculated_at=datetime.now(timezone.utc).isoformat()
    )


def adrs_from_defaults(agent_id: str) -> ADRSResult:
    """
    Calculate ADRS using conservative default signals.
    Use when telemetry is incomplete — defaults assume worst case.

    Unknown blast radius = 10. No changelog tracking = 10.
    No verification data = 7. No revert drill = 10.

    This is intentionally harsh. Unknown = high risk.
    """
    return calculate_adrs(
        agent_id,
        ADRSSignals(
            blast_radius_exposure=10.0,
            version_drift_rate=10.0,
            verification_coverage_inverse=7.0,
            recovery_time=10.0
        )
    )