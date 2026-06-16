"""
Automation Complacency Rate (ACR) — human-side governance SLI.

When autonomous agents perform reliably over time, human operators
reduce active monitoring. When the agent eventually fails, operators
have lost the situational awareness to catch it quickly.

We have decades of research on this in aviation and industrial control.
It is now arriving in AI SRE.

ACR = decisions accepted without reasoning verification
      / total agent decisions, rolling 30-day window

ACR is not a technical SLI. It is a human behavior SLI.
You cannot alert your way to good ACR. You need a governance culture
where reasoning verification is a first-class on-call practice.

This module measures ACR. What you do with the measurement
is a team conversation, not an automated fix.

Three ACR signals:
    1. Overall trend — rising ACR over any 4-week window
    2. ACR by severity — P1 ACR > 5% is always unacceptable
    3. ACR × HER correlation — both falling = double exposure

Author: Ajay Devineni
License: MIT
Repository: github.com/Ajay150313/agentsre
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from enum import Enum


class VerificationStatus(Enum):
    PENDING   = "pending"     # Decision made, verification window open
    VERIFIED  = "verified"    # Human read the trace and confirmed reasoning
    EXPIRED   = "expired"     # Window closed without verification = ACR++
    WAIVED    = "waived"      # Explicitly waived (e.g. P4, low-risk action)


class Severity(Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"

    @property
    def verification_window_minutes(self) -> int:
        """How long the team has to verify before it counts as ACR."""
        return {
            "P1": 15,
            "P2": 60,
            "P3": 240,
            "P4": 480
        }[self.value]

    @property
    def acr_threshold_pct(self) -> float:
        """Maximum acceptable ACR for this severity level."""
        return {"P1": 5.0, "P2": 15.0, "P3": 40.0, "P4": 80.0}[self.value]


@dataclass
class VerificationRecord:
    """
    A single agent decision with its verification outcome.

    Attributes:
        decision_id: Unique identifier for this agent decision
        severity: Incident severity (P1-P4)
        action_taken: What the agent did
        rtd_trace_id: ID of the RTD trace — what to read for verification
        outcome_accepted: Did the team note the incident resolved?
        reasoning_verified: Did a human READ the RTD trace and validate?
        verifier: Who verified (None if not verified)
        decision_at: When the agent acted
        verified_at: When a human verified (None if not)
        reasoning_valid: Was the agent's reasoning correct? (if verified)
        rca_confirmed: Did the RCA match what actually happened?
    """
    decision_id: str
    severity: Severity
    action_taken: str
    rtd_trace_id: str
    outcome_accepted: bool = False
    reasoning_verified: bool = False
    verifier: Optional[str] = None
    decision_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    verified_at: Optional[str] = None
    reasoning_valid: Optional[bool] = None
    rca_confirmed: Optional[bool] = None

    @property
    def counts_as_complacent(self) -> bool:
        """
        True if this decision contributes to ACR.

        A decision is complacent if:
        - The outcome was accepted (team noted resolution)
        - But the reasoning was NOT verified
        - And the verification window has expired

        Note: PENDING decisions don't yet count as complacent.
        They may still be verified within the window.
        """
        if not self.outcome_accepted:
            return False
        if self.reasoning_verified:
            return False

        deadline = (
            datetime.fromisoformat(self.decision_at) +
            timedelta(minutes=self.severity.verification_window_minutes)
        )
        return datetime.now(timezone.utc) > deadline

    @property
    def verification_status(self) -> VerificationStatus:
        if self.reasoning_verified:
            return VerificationStatus.VERIFIED
        deadline = (
            datetime.fromisoformat(self.decision_at) +
            timedelta(minutes=self.severity.verification_window_minutes)
        )
        if datetime.now(timezone.utc) > deadline:
            return VerificationStatus.EXPIRED
        return VerificationStatus.PENDING


@dataclass
class ACRTracker:
    """
    Track Automation Complacency Rate for a production AI agent.

    ACR is a human behavior SLI — it measures whether your team
    is actively verifying agent reasoning or passively accepting outcomes.

    Rising ACR is NOT evidence the agent is getting better.
    It is evidence the team is watching less carefully.

    Use acr_by_severity() — overall ACR can hide P1/P2 exposure
    when those incidents are rare but high-stakes.

    Attributes:
        agent_id: Agent being monitored
        task_class: Task category (ACR varies by task familiarity)
        window_days: Rolling window for ACR calculation
    """
    agent_id: str
    task_class: str
    window_days: int = 30
    _records: List[VerificationRecord] = field(
        default_factory=list, repr=False
    )

    def record(self, decision: VerificationRecord) -> None:
        """Add a decision record to the tracker."""
        self._records.append(decision)
        self._prune()

    def _prune(self) -> None:
        """Remove records outside rolling window."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.window_days)
        self._records = [
            r for r in self._records
            if datetime.fromisoformat(r.decision_at) > cutoff
        ]

    def _window_records(self) -> List[VerificationRecord]:
        """Records within the current rolling window."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.window_days)
        return [
            r for r in self._records
            if datetime.fromisoformat(r.decision_at) > cutoff
        ]

    @property
    def overall_acr(self) -> Optional[float]:
        """Overall ACR across all severities (0-100)."""
        records = self._window_records()
        if not records:
            return None
        complacent = sum(1 for r in records if r.counts_as_complacent)
        return round(complacent / len(records) * 100, 1)

    def acr_by_severity(self) -> Dict[str, Optional[float]]:
        """
        ACR broken down by severity level.

        Always use this alongside overall_acr.
        Overall ACR of 10% is very different if all complacent
        decisions are P4 vs if any are P1.
        """
        result = {}
        records = self._window_records()
        for sev in Severity:
            sev_records = [r for r in records if r.severity == sev]
            if not sev_records:
                result[sev.value] = None
                continue
            complacent = sum(1 for r in sev_records if r.counts_as_complacent)
            result[sev.value] = round(complacent / len(sev_records) * 100, 1)
        return result

    def double_exposure_check(self,
                               her_current: float,
                               her_30d_ago: float) -> Dict:
        """
        Check for double-exposure pattern:
        HER dropping (agent acting more autonomously) while
        ACR rising (team reviewing less carefully).

        This combination = maximum undetected risk surface.

        Args:
            her_current: Current HER percentage
            her_30d_ago: HER 30 days ago for trend comparison
        """
        her_dropping = her_current < her_30d_ago
        acr = self.overall_acr or 0.0
        acr_rising = acr > 15.0  # flag if above 15%

        double_exposure = her_dropping and acr_rising
        return {
            "her_current": her_current,
            "her_30d_ago": her_30d_ago,
            "her_trend": "DROPPING" if her_dropping else "STABLE_OR_RISING",
            "overall_acr_pct": acr,
            "double_exposure_detected": double_exposure,
            "risk_level": "CRITICAL" if double_exposure else "OK",
            "recommendation": (
                "IMMEDIATE REVIEW: Agent acting more autonomously while team "
                "reviews less carefully. Maximum undetected risk surface. "
                "Schedule team governance review and increase P1/P2 "
                "verification requirements before next change window."
                if double_exposure
                else "No double-exposure pattern detected."
            )
        }

    def acr_status(self) -> Dict:
        """
        Full ACR status report for CloudWatch publication
        and SRE governance review.
        """
        records = self._window_records()
        by_sev = self.acr_by_severity()

        # Find worst severity with complacency
        p1_acr = by_sev.get('P1') or 0.0
        p2_acr = by_sev.get('P2') or 0.0

        if p1_acr > Severity.P1.acr_threshold_pct:
            status = "CRITICAL"
            rec = (f"P1 ACR at {p1_acr}% — above 5% threshold. "
                   "P1 incidents accepted without reasoning verification. "
                   "Immediate team governance review required.")
        elif p2_acr > Severity.P2.acr_threshold_pct:
            status = "WARNING"
            rec = (f"P2 ACR at {p2_acr}% — above 15% threshold. "
                   "Review team verification practices for P2 incidents.")
        elif (self.overall_acr or 0.0) > 30.0:
            status = "WARNING"
            rec = (f"Overall ACR at {self.overall_acr}% — "
                   "team may be drifting toward passive acceptance. "
                   "Schedule verification practice review.")
        else:
            status = "OK"
            rec = "ACR within acceptable bounds. Continue monitoring."

        return {
            "agent_id": self.agent_id,
            "task_class": self.task_class,
            "window_days": self.window_days,
            "total_decisions": len(records),
            "overall_acr_pct": self.overall_acr,
            "acr_by_severity": by_sev,
            "status": status,
            "recommendation": rec,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    def to_json(self) -> str:
        return json.dumps(self.acr_status(), indent=2)