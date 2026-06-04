# agentsre/tool_evaluation.py
"""
AI SRE Tool Evaluation Framework — five-question SLI-based scorecard.

Use to evaluate commercial AI SRE tools (Datadog Bits AI, New Relic
SRE Agent, Komodor Klaudia, Middleware OpsAI, etc.) or internal builds
against the production SLI framework from the agentsre series.

Five questions map to five SLI dimensions:
    Q1 → Reasoning observability (RTD)
    Q2 → Human Escalation Rate transparency (HER)
    Q3 → Pre-action reliability gate (error budget, AQDD, HER)
    Q4 → Blast radius definition (scope of accuracy claims)
    Q5 → Ownership and audit trail (postmortem readiness)

Score each sub-question: 0 (no), 1 (partial), 2 (yes, with evidence).
Total >= 8/20: consider for production.
Total 5-7/20: pilot with governance layer built separately.
Total < 5/20: not production-ready for autonomous operation.

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
class QuestionScore:
    """Score and notes for one evaluation question."""
    score_a: int = 0        # First sub-question (0/1/2)
    score_b: int = 0        # Second sub-question (0/1/2)
    notes: str = ""
    evidence_url: Optional[str] = None  # Link to vendor docs/demo

    @property
    def total(self) -> int:
        return self.score_a + self.score_b


@dataclass
class ToolEvaluationScore:
    """
    Five-question AI SRE tool evaluation scorecard.

    Instantiate with tool name and your environment context.
    Score each question using the score() method.
    Call report() to generate the full evaluation.

    Example:
        eval = ToolEvaluationScore(
            tool_name="Datadog Bits AI",
            evaluator="ajay-devineni",
            environment_context="AWS EKS, 40 microservices, fintech"
        )
        eval.q1_reasoning.score_a = 1  # partial RTD tracking
        eval.q1_reasoning.score_b = 0  # cannot query decision sequence
        eval.q1_reasoning.notes = "Logs prompts and tool calls, no re-plan count"
        print(eval.recommendation)
    """
    tool_name: str
    evaluator: str
    environment_context: str

    # Q1: Does it instrument the reasoning layer?
    # score_a: tracks re-planning cycles per task (not just tool calls)
    # score_b: can query full decision sequence after an incident
    q1_reasoning: QuestionScore = field(default_factory=QuestionScore)

    # Q2: Is HER transparent in their benchmark?
    # score_a: HER in benchmark environment explicitly disclosed
    # score_b: autonomous vs assisted resolution split disclosed
    q2_her: QuestionScore = field(default_factory=QuestionScore)

    # Q3: Does it check SLO state before acting?
    # score_a: checks error budget remaining before autonomous action
    # score_b: gate thresholds are configurable per environment
    q3_gate: QuestionScore = field(default_factory=QuestionScore)

    # Q4: Is the blast radius defined?
    # score_a: blast radius explicitly documented
    # score_b: accuracy claims scoped to blast radius domain
    q4_blast_radius: QuestionScore = field(default_factory=QuestionScore)

    # Q5: Ownership and postmortem readiness
    # score_a: generates structured audit log of agent decisions
    # score_b: audit log is queryable during incident postmortem
    q5_audit: QuestionScore = field(default_factory=QuestionScore)

    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def total_score(self) -> int:
        return (
            self.q1_reasoning.total +
            self.q2_her.total +
            self.q3_gate.total +
            self.q4_blast_radius.total +
            self.q5_audit.total
        )

    @property
    def recommendation(self) -> str:
        s = self.total_score
        if s >= 8:
            return (
                "CONSIDER FOR PRODUCTION: meets baseline governance requirements. "
                "Run 30-day shadow mode before canary deployment."
            )
        elif s >= 5:
            return (
                "PILOT WITH CAUTION: build Pre-Action Gate, ARO registry, "
                "and audit layer separately before production deployment."
            )
        return (
            "NOT PRODUCTION-READY: missing critical governance capabilities. "
            "Use as investigation assistant only — no autonomous remediation."
        )

    @property
    def weakest_dimension(self) -> str:
        scores = {
            "Reasoning observability (RTD)": self.q1_reasoning.total,
            "HER transparency": self.q2_her.total,
            "Pre-action SLO gate": self.q3_gate.total,
            "Blast radius definition": self.q4_blast_radius.total,
            "Audit and ownership": self.q5_audit.total,
        }
        return min(scores, key=scores.get)

    def report(self) -> Dict:
        return {
            "tool": self.tool_name,
            "evaluator": self.evaluator,
            "environment": self.environment_context,
            "evaluated_at": self.evaluated_at,
            "scores": {
                "q1_reasoning_layer": {
                    "description": "Does it instrument reasoning loops, not just tool calls?",
                    "tracks_replanning_cycles": self.q1_reasoning.score_a,
                    "queryable_decision_sequence": self.q1_reasoning.score_b,
                    "subtotal": f"{self.q1_reasoning.total}/4",
                    "notes": self.q1_reasoning.notes,
                    "evidence": self.q1_reasoning.evidence_url,
                },
                "q2_her_transparency": {
                    "description": "What is HER in their benchmark environment?",
                    "her_disclosed": self.q2_her.score_a,
                    "autonomous_split_disclosed": self.q2_her.score_b,
                    "subtotal": f"{self.q2_her.total}/4",
                    "notes": self.q2_her.notes,
                    "evidence": self.q2_her.evidence_url,
                },
                "q3_pre_action_gate": {
                    "description": "Does it check SLO state before acting autonomously?",
                    "checks_error_budget": self.q3_gate.score_a,
                    "configurable_thresholds": self.q3_gate.score_b,
                    "subtotal": f"{self.q3_gate.total}/4",
                    "notes": self.q3_gate.notes,
                    "evidence": self.q3_gate.evidence_url,
                },
                "q4_blast_radius": {
                    "description": "Is the blast radius explicitly defined?",
                    "explicit_definition": self.q4_blast_radius.score_a,
                    "accuracy_claims_scoped": self.q4_blast_radius.score_b,
                    "subtotal": f"{self.q4_blast_radius.total}/4",
                    "notes": self.q4_blast_radius.notes,
                    "evidence": self.q4_blast_radius.evidence_url,
                },
                "q5_audit_ownership": {
                    "description": "Does it generate a postmortem-ready audit trail?",
                    "audit_log_generated": self.q5_audit.score_a,
                    "queryable_in_postmortem": self.q5_audit.score_b,
                    "subtotal": f"{self.q5_audit.total}/4",
                    "notes": self.q5_audit.notes,
                    "evidence": self.q5_audit.evidence_url,
                },
            },
            "summary": {
                "total_score": f"{self.total_score}/20",
                "weakest_dimension": self.weakest_dimension,
                "recommendation": self.recommendation,
            }
        }

    def to_json(self) -> str:
        return json.dumps(self.report(), indent=2)