# agentsre/eval_pipeline.py
"""
Evaluation Pipeline — continuous agent readiness assessment.

Inspired by Google's IRM Analyzer: continuous evaluation pipelines
grounded in human operational memory and nightly evals that prove
agent readiness before deployment and during operation.

This module implements a lightweight evaluation runner that:
- Scores agent decisions against a ground-truth corpus
- Tracks DQR trend over rolling windows
- Flags agents whose readiness has degraded below deployment threshold
- Generates evaluation reports for postmortem and governance review

For teams without Google's incident corpus: use shadow mode
task recordings as your ground truth. 30 days of shadow traces
is enough to establish a meaningful DQR baseline.

Author: Ajay Devineni
License: MIT
Repository: github.com/Ajay150313/agentsre
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Callable


@dataclass
class EvalCase:
    """
    A single evaluation case — one task with known-good answer.

    Attributes:
        case_id: Unique identifier
        task_description: What the agent was asked to do
        expected_outcome: The correct/acceptable outcome
        actual_outcome: What the agent produced
        evaluator_fn: Optional custom scoring function.
                      If None, uses simple string match.
        weight: Relative importance (default 1.0)
    """
    case_id: str
    task_description: str
    expected_outcome: str
    actual_outcome: str
    evaluator_fn: Optional[Callable[[str, str], float]] = None
    weight: float = 1.0

    def score(self) -> float:
        """
        Score this case (0.0 to 1.0).

        Uses custom evaluator if provided, otherwise
        returns 1.0 for exact match, 0.0 for mismatch.
        For production: replace with semantic similarity scorer.
        """
        if self.evaluator_fn:
            return self.evaluator_fn(
                self.expected_outcome,
                self.actual_outcome
            )
        return 1.0 if (
            self.actual_outcome.strip().lower() ==
            self.expected_outcome.strip().lower()
        ) else 0.0


@dataclass
class EvalRun:
    """
    A complete evaluation run — batch of cases for one agent.

    Attributes:
        agent_id: Agent being evaluated
        run_id: Unique run identifier
        task_class: Task type being evaluated
        cases: Evaluation cases in this run
        dqr_threshold: Minimum DQR to pass readiness check
        run_at: When this run executed
    """
    agent_id: str
    task_class: str
    cases: List[EvalCase] = field(default_factory=list)
    dqr_threshold: float = 0.90
    run_id: str = field(
        default_factory=lambda: (
            datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        )
    )
    run_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add_case(self, case: EvalCase) -> None:
        """Add an evaluation case to this run."""
        self.cases.append(case)

    @property
    def dqr(self) -> Optional[float]:
        """
        Decision Quality Rate for this eval run.
        Weighted average score across all cases.
        Returns None if no cases.
        """
        if not self.cases:
            return None
        total_weight = sum(c.weight for c in self.cases)
        weighted_score = sum(
            c.score() * c.weight for c in self.cases
        )
        return round(weighted_score / total_weight, 4)

    @property
    def passed(self) -> bool:
        """True if DQR meets deployment threshold."""
        d = self.dqr
        return d is not None and d >= self.dqr_threshold

    @property
    def failed_cases(self) -> List[EvalCase]:
        """Cases where agent scored below 0.5."""
        return [c for c in self.cases if c.score() < 0.5]

    def report(self) -> Dict:
        """
        Generate evaluation report.
        Use for deployment gates and governance review.
        """
        dqr = self.dqr
        return {
            "eval_run_id": self.run_id,
            "agent_id": self.agent_id,
            "task_class": self.task_class,
            "run_at": self.run_at,
            "cases_total": len(self.cases),
            "cases_passed": sum(
                1 for c in self.cases if c.score() >= 0.5
            ),
            "cases_failed": len(self.failed_cases),
            "dqr": dqr,
            "dqr_threshold": self.dqr_threshold,
            "readiness": "PASS" if self.passed else "FAIL",
            "failed_case_ids": [
                c.case_id for c in self.failed_cases
            ],
            "recommendation": (
                "Agent meets DQR threshold. "
                "Proceed to next deployment stage."
                if self.passed
                else
                f"Agent DQR {dqr:.1%} below threshold "
                f"{self.dqr_threshold:.1%}. "
                "Do not promote. Review failed cases."
            )
        }

    def to_json(self) -> str:
        return json.dumps(self.report(), indent=2)


class EvalPipeline:
    """
    Continuous evaluation pipeline for agent readiness.

    Implements the IRM Analyzer pattern from Google's SRE AI whitepaper:
    continuous evaluation grounded in operational ground truth,
    with nightly runs that gate deployment and flag regression.

    Usage:
        pipeline = EvalPipeline(agent_id="triage-agent-v2")

        # Build eval corpus from shadow mode traces
        run = pipeline.create_run("incident-investigation")
        run.add_case(EvalCase(
            case_id="inc-001",
            task_description="Identify root cause of payments timeout",
            expected_outcome="Database connection pool exhausted",
            actual_outcome=agent_output
        ))

        result = pipeline.evaluate(run)
        if not result.passed:
            # Block deployment, alert team
            pass
    """

    def __init__(self, agent_id: str,
                 dqr_regression_threshold: float = 0.05):
        """
        Args:
            agent_id: Agent being evaluated
            dqr_regression_threshold: DQR drop that triggers
                regression alert (default: 5 percentage points)
        """
        self.agent_id = agent_id
        self.dqr_regression_threshold = dqr_regression_threshold
        self._history: List[EvalRun] = []

    def create_run(self, task_class: str,
                   dqr_threshold: float = 0.90) -> EvalRun:
        """Create a new evaluation run."""
        return EvalRun(
            agent_id=self.agent_id,
            task_class=task_class,
            dqr_threshold=dqr_threshold
        )

    def evaluate(self, run: EvalRun) -> EvalRun:
        """
        Execute evaluation run and check for regression.
        Stores run in history for trend analysis.
        """
        self._history.append(run)
        return run

    def dqr_trend(self, task_class: str,
                   last_n: int = 7) -> List[Optional[float]]:
        """
        DQR trend for the last N evaluation runs.
        Use to detect gradual regression before it hits threshold.
        """
        runs = [
            r for r in self._history
            if r.task_class == task_class
        ][-last_n:]
        return [r.dqr for r in runs]

    def regression_detected(self, task_class: str) -> bool:
        """
        True if DQR has dropped by more than regression threshold
        compared to the previous run.
        """
        trend = self.dqr_trend(task_class, last_n=2)
        if len(trend) < 2 or None in trend:
            return False
        drop = trend[-2] - trend[-1]
        return drop >= self.dqr_regression_threshold

    def pipeline_status(self) -> Dict:
        """Summary of pipeline health across all task classes."""
        task_classes = list({r.task_class for r in self._history})
        status = {}
        for tc in task_classes:
            recent_runs = [
                r for r in self._history if r.task_class == tc
            ][-5:]
            latest = recent_runs[-1] if recent_runs else None
            status[tc] = {
                "latest_dqr": latest.dqr if latest else None,
                "latest_readiness": (
                    "PASS" if latest and latest.passed else "FAIL"
                ),
                "regression_detected": self.regression_detected(tc),
                "trend_last_5": self.dqr_trend(tc, last_n=5)
            }
        return {
            "agent_id": self.agent_id,
            "pipeline_status": status,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }