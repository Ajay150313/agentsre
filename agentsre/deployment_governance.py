AI Code Change Governance — the double-exposure reliability layer.
 
Governs the interaction between AI-generated code changes and
AI agent runtime behavior in the same production environment.
 
The double-exposure problem (Devineni, 2026):
    When AI-generated code changes and AI agent behavioral drift
    occur simultaneously, standard observability produces no signal.
    Detection requires behavioral baseline comparison, not infrastructure metrics.
 
Author: Ajay Devineni
"""
 
from __future__ import annotations
 
import statistics
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict
 
 
class DeploymentRisk(str, Enum):
    LOW = "LOW"                  # no AI code, no agent-adjacent changes
    ELEVATED = "ELEVATED"        # AI code OR agent-adjacent (not both)
    HIGH = "HIGH"                # AI code AND agent-adjacent changes
    DOUBLE_EXPOSURE = "DOUBLE_EXPOSURE"  # HIGH + active agent behavioral drift
 
 
@dataclass
class DeploymentRecord:
    """Record of a code deployment for governance evaluation."""
    deployment_id: str
    agent_id: str
    task_class: str
    is_ai_generated: bool
    is_agent_adjacent: bool          # touches tool env, config, or action space
    pre_tie_baseline: Optional[float] = None
    pre_dqr_baseline: Optional[float] = None
    post_tie_samples: List[float] = field(default_factory=list)
    post_dqr_samples: List[float] = field(default_factory=list)
    deployed_at: float = field(default_factory=time.time)
    approved_by: Optional[str] = None
    requires_approval: bool = False
 
 
@dataclass
class DeploymentEvaluation:
    """Result of evaluating a deployment's impact on agent behavior."""
    deployment_id: str
    risk_level: DeploymentRisk
    tie_drift_ratio: Optional[float]
    dqr_drift_ratio: Optional[float]
    behavioral_breach: bool
    requires_rollback: bool
    attribution_confidence: float     # 0.0–1.0 confidence that code change caused drift
    recommendation: str
 
    def __str__(self) -> str:
        status = "🔴 ROLLBACK" if self.requires_rollback else (
            "🟡 MONITOR" if self.behavioral_breach else "🟢 HEALTHY"
        )
        return (
            f"[Deployment {self.deployment_id}] {status}\n"
            f"  Risk: {self.risk_level.value}\n"
            f"  TIE drift: {self.tie_drift_ratio:.2f}x\n"
            f"  DQR drift: {self.dqr_drift_ratio:.2f}x\n"
            f"  Attribution confidence: {self.attribution_confidence:.0%}\n"
            f"  Recommendation: {self.recommendation}"
        ) if self.tie_drift_ratio else (
            f"[Deployment {self.deployment_id}] {status} — {self.recommendation}"
        )
 
 
class AICodeDeploymentGovernor:
    """
    Governs AI-generated code deployments that touch agent environments.
 
    Implements the double-exposure governance pattern:
    1. Classify deployment risk (LOW / ELEVATED / HIGH / DOUBLE_EXPOSURE)
    2. Capture pre-deployment behavioral baselines
    3. Collect post-deployment behavioral samples
    4. Evaluate drift and generate rollback recommendation
 
    Usage::
 
        from agentsre.deployment_governance import AICodeDeploymentGovernor, DeploymentRecord
 
        governor = AICodeDeploymentGovernor(
            tie_drift_threshold=1.15,
            dqr_drift_threshold=0.85,
            min_post_samples=20,
        )
 
        # At deployment start
        record = DeploymentRecord(
            deployment_id="deploy-2026-05-05-001",
            agent_id="payment-processor",
            task_class="payment-routing",
            is_ai_generated=True,
            is_agent_adjacent=True,
        )
        risk = governor.classify_risk(record)
        print(f"Deployment risk: {risk.value}")
 
        if risk in [DeploymentRisk.HIGH, DeploymentRisk.DOUBLE_EXPOSURE]:
            governor.capture_pre_baseline(record, current_tie_samples, current_dqr_samples)
 
        # 48 hours post-deployment
        governor.record_post_sample(record.deployment_id, tie=3.1, dqr=87.2)
 
        evaluation = governor.evaluate(record)
        print(evaluation)
    """
 
    def __init__(
        self,
        tie_drift_threshold: float = 1.15,
        dqr_drift_threshold: float = 0.85,
        min_post_samples: int = 20,
        rollback_tie_threshold: float = 1.30,
        rollback_dqr_threshold: float = 0.70,
    ):
        self.tie_drift_threshold = tie_drift_threshold
        self.dqr_drift_threshold = dqr_drift_threshold
        self.min_post_samples = min_post_samples
        self.rollback_tie_threshold = rollback_tie_threshold
        self.rollback_dqr_threshold = rollback_dqr_threshold
 
        self._records: Dict[str, DeploymentRecord] = {}
        self._post_tie: Dict[str, List[float]] = {}
        self._post_dqr: Dict[str, List[float]] = {}
 
    def classify_risk(self, record: DeploymentRecord) -> DeploymentRisk:
        """Classify deployment risk before it goes out."""
        if not record.is_ai_generated and not record.is_agent_adjacent:
            return DeploymentRisk.LOW
        if record.is_ai_generated and record.is_agent_adjacent:
            return DeploymentRisk.HIGH
        return DeploymentRisk.ELEVATED
 
    def capture_pre_baseline(
        self,
        record: DeploymentRecord,
        tie_samples: List[float],
        dqr_samples: List[float],
    ) -> None:
        """Capture pre-deployment behavioral baseline. Call before deploying."""
        if not tie_samples or not dqr_samples:
            raise ValueError("Baseline samples must not be empty")
        record.pre_tie_baseline = statistics.mean(tie_samples)
        record.pre_dqr_baseline = statistics.mean(dqr_samples)
        record.requires_approval = self.classify_risk(record) in [
            DeploymentRisk.HIGH, DeploymentRisk.DOUBLE_EXPOSURE
        ]
        self._records[record.deployment_id] = record
 
    def record_post_sample(
        self,
        deployment_id: str,
        tie: float,
        dqr: float,
    ) -> None:
        """Record a post-deployment behavioral sample."""
        self._post_tie.setdefault(deployment_id, []).append(tie)
        self._post_dqr.setdefault(deployment_id, []).append(dqr)
 
    def evaluate(self, record: DeploymentRecord) -> DeploymentEvaluation:
        """
        Evaluate post-deployment behavioral drift against pre-deployment baseline.
        Returns rollback recommendation if drift exceeds thresholds.
        """
        dep_id = record.deployment_id
        post_tie = self._post_tie.get(dep_id, [])
        post_dqr = self._post_dqr.get(dep_id, [])
 
        if len(post_tie) < self.min_post_samples:
            return DeploymentEvaluation(
                deployment_id=dep_id,
                risk_level=self.classify_risk(record),
                tie_drift_ratio=None,
                dqr_drift_ratio=None,
                behavioral_breach=False,
                requires_rollback=False,
                attribution_confidence=0.0,
                recommendation=f"Need {self.min_post_samples} post-deployment samples, have {len(post_tie)}. Continue monitoring.",
            )
 
        if not record.pre_tie_baseline or not record.pre_dqr_baseline:
            return DeploymentEvaluation(
                deployment_id=dep_id,
                risk_level=self.classify_risk(record),
                tie_drift_ratio=None,
                dqr_drift_ratio=None,
                behavioral_breach=False,
                requires_rollback=False,
                attribution_confidence=0.0,
                recommendation="No pre-deployment baseline captured. Cannot evaluate drift. Capture baseline before next deployment.",
            )
 
        mean_post_tie = statistics.mean(post_tie)
        mean_post_dqr = statistics.mean(post_dqr)
        tie_drift = mean_post_tie / record.pre_tie_baseline
        dqr_drift = mean_post_dqr / record.pre_dqr_baseline
 
        behavioral_breach = (
            tie_drift > self.tie_drift_threshold or
            dqr_drift < self.dqr_drift_threshold
        )
        requires_rollback = (
            tie_drift > self.rollback_tie_threshold or
            dqr_drift < self.rollback_dqr_threshold
        )
 
        # Attribution confidence: higher if AI-generated AND agent-adjacent
        base_confidence = 0.6
        if record.is_ai_generated:
            base_confidence += 0.2
        if record.is_agent_adjacent:
            base_confidence += 0.2
        attribution_confidence = min(base_confidence, 1.0) if behavioral_breach else 0.0
 
        if requires_rollback:
            recommendation = (
                f"ROLLBACK RECOMMENDED. TIE drift {tie_drift:.2f}x or DQR drift {dqr_drift:.2f}x "
                f"exceeds rollback threshold. Attribution confidence: {attribution_confidence:.0%}."
            )
        elif behavioral_breach:
            recommendation = (
                f"MONITOR CLOSELY. Behavioral drift detected (TIE {tie_drift:.2f}x, DQR {dqr_drift:.2f}x). "
                f"Continue sampling for 4 more hours before clearing."
            )
        else:
            recommendation = "Behavioral baselines stable post-deployment. No action required."
 
        return DeploymentEvaluation(
            deployment_id=dep_id,
            risk_level=self.classify_risk(record),
            tie_drift_ratio=round(tie_drift, 3),
            dqr_drift_ratio=round(dqr_drift, 3),
            behavioral_breach=behavioral_breach,
            requires_rollback=requires_rollback,
            attribution_confidence=round(attribution_confidence, 2),
            recommendation=recommendation,
        )
 
    def blast_radius_report(self, agent_id: str) -> dict:
        """
        Generate double-exposure blast radius report for an agent.
        Run this quarterly and before any major infrastructure change.
        """
        agent_deployments = [
            r for r in self._records.values()
            if r.agent_id == agent_id
        ]
        high_risk = [r for r in agent_deployments if self.classify_risk(r) == DeploymentRisk.HIGH]
        return {
            "agent_id": agent_id,
            "total_deployments_reviewed": len(agent_deployments),
            "high_risk_deployments": len(high_risk),
            "double_exposure_risk": "HIGH" if any(
                r.is_ai_generated and r.is_agent_adjacent for r in agent_deployments
            ) else "LOW",
            "recommendation": (
                "Run double-exposure runbook drill. At least one HIGH-risk deployment pattern detected."
                if high_risk else
                "No HIGH-risk patterns in reviewed deployments."
            ),
        }