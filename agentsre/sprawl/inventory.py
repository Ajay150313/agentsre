"""
agentsre.sprawl.inventory
~~~~~~~~~~~~~~~~~~~~~~~~~
Agent Fleet Inventory — the foundation of Agent Sprawl governance.

Before you can govern agent sprawl, you need to know what you're governing.
This module maintains a live inventory of every model, framework, and agent
component in your deployment, with SLO ownership and deprecation tracking.

Agent Sprawl (Devineni, 2026):
    The condition where AI agent infrastructure complexity — frameworks,
    models, tool layers, orchestration patterns — grows faster than your
    ability to measure and govern its reliability.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional


class ComponentType(str, Enum):
    MODEL = "model"
    FRAMEWORK = "framework"
    AGENT = "agent"
    TOOL_SERVER = "tool_server"


class GovernanceHealth(str, Enum):
    HEALTHY = "HEALTHY"          # score >= 80
    DEGRADED = "DEGRADED"        # score 50–79
    CRITICAL = "CRITICAL"        # score < 50  (governance debt)


@dataclass
class DeprecationAlert:
    component_id: str
    days_remaining: int
    slo_owner: str
    task_classes: List[str]
    fired_at: float = field(default_factory=time.time)


@dataclass
class FleetComponent:
    """
    A single model, framework, or agent in your production fleet.

    Every component must have:
      - A named SLO owner (not a team — a person)
      - A baseline establishment date
      - A deprecation date (if applicable)
    """
    component_id: str                          # e.g. "anthropic.claude-sonnet-4-6"
    component_type: ComponentType
    agent_id: str                              # which agent uses this
    task_classes: List[str]                    # task classes this component handles
    slo_owner: str                             # named human — email or username
    framework_version: Optional[str] = None
    baseline_established_at: Optional[str] = None
    deprecation_date: Optional[str] = None     # ISO 8601 date string
    current_tie_baseline: Optional[float] = None
    current_dqr_baseline: Optional[float] = None
    last_slo_review: Optional[str] = None
    notes: str = ""
    added_at: float = field(default_factory=time.time)

    # Internal alert tracking
    _alerts_sent: Dict[int, bool] = field(default_factory=dict, repr=False)

    def days_until_deprecation(self) -> Optional[int]:
        if not self.deprecation_date:
            return None
        dep = datetime.fromisoformat(self.deprecation_date).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (dep - now).days

    def governance_score(self) -> int:
        """
        0–100 governance health score.

        Scoring:
          +25 — named SLO owner present
          +25 — baseline established within last 90 days
          +25 — SLO review within last 90 days
          +25 — no overdue deprecation (or no deprecation date)
        """
        score = 0

        # SLO owner
        if self.slo_owner and "@" in self.slo_owner:
            score += 25

        # Baseline recency
        if self.baseline_established_at:
            try:
                baseline_dt = datetime.fromisoformat(self.baseline_established_at)
                if (datetime.now() - baseline_dt).days <= 90:
                    score += 25
            except ValueError:
                pass

        # SLO review recency
        if self.last_slo_review:
            try:
                review_dt = datetime.fromisoformat(self.last_slo_review)
                if (datetime.now() - review_dt).days <= 90:
                    score += 25
            except ValueError:
                pass

        # Deprecation
        days = self.days_until_deprecation()
        if days is None or days > 0:
            score += 25

        return score

    def governance_health(self) -> GovernanceHealth:
        score = self.governance_score()
        if score >= 80:
            return GovernanceHealth.HEALTHY
        elif score >= 50:
            return GovernanceHealth.DEGRADED
        return GovernanceHealth.CRITICAL

    def needs_deprecation_alert(self, threshold_days: int) -> bool:
        days = self.days_until_deprecation()
        if days is None:
            return False
        return days <= threshold_days and not self._alerts_sent.get(threshold_days, False)

    def mark_alert_sent(self, threshold_days: int) -> None:
        self._alerts_sent[threshold_days] = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["component_type"] = self.component_type.value
        d.pop("_alerts_sent", None)
        return d


class AgentFleetInventory:
    """
    Live inventory of every AI component in production.

    Usage::

        from agentsre.sprawl.inventory import AgentFleetInventory, FleetComponent, ComponentType

        inventory = AgentFleetInventory()

        inventory.register(FleetComponent(
            component_id="anthropic.claude-sonnet-4-6",
            component_type=ComponentType.MODEL,
            agent_id="payment-processor",
            task_classes=["payment-routing", "fraud-detection"],
            slo_owner="ajay@team.com",
            baseline_established_at="2026-04-01",
            deprecation_date="2027-06-01",
            last_slo_review="2026-04-01",
            current_tie_baseline=2.4,
            current_dqr_baseline=91.2,
        ))

        report = inventory.quarterly_review_report()
        alerts = inventory.pending_deprecation_alerts()
    """

    DEPRECATION_ALERT_THRESHOLDS = [60, 30, 7]

    def __init__(self):
        self._components: Dict[str, FleetComponent] = {}
        self._alert_callbacks = []

    # ── Registration ──────────────────────────────────────────

    def register(self, component: FleetComponent) -> None:
        """Register a component in the fleet inventory."""
        key = f"{component.agent_id}:{component.component_id}"
        self._components[key] = component

    def get(self, agent_id: str, component_id: str) -> Optional[FleetComponent]:
        return self._components.get(f"{agent_id}:{component_id}")

    def all(self) -> List[FleetComponent]:
        return list(self._components.values())

    def by_agent(self, agent_id: str) -> List[FleetComponent]:
        return [c for c in self._components.values() if c.agent_id == agent_id]

    def by_owner(self, slo_owner: str) -> List[FleetComponent]:
        return [c for c in self._components.values() if c.slo_owner == slo_owner]

    # ── Governance checks ─────────────────────────────────────

    def governance_debt(self) -> List[FleetComponent]:
        """Components with governance score < 50 — require immediate remediation."""
        return [c for c in self._components.values()
                if c.governance_health() == GovernanceHealth.CRITICAL]

    def orphaned_components(self) -> List[FleetComponent]:
        """Components with no valid SLO owner — the most critical governance gap."""
        return [c for c in self._components.values()
                if not c.slo_owner or "@" not in c.slo_owner]

    def pending_deprecation_alerts(self) -> List[DeprecationAlert]:
        """Return all deprecation alerts that should be fired now."""
        alerts = []
        for component in self._components.values():
            for threshold in self.DEPRECATION_ALERT_THRESHOLDS:
                if component.needs_deprecation_alert(threshold):
                    alerts.append(DeprecationAlert(
                        component_id=component.component_id,
                        days_remaining=threshold,
                        slo_owner=component.slo_owner,
                        task_classes=component.task_classes,
                    ))
                    component.mark_alert_sent(threshold)
        return alerts

    def overdue_baselines(self, max_age_days: int = 90) -> List[FleetComponent]:
        """Components whose TIE/DQR baselines are older than max_age_days."""
        result = []
        cutoff = datetime.now() - timedelta(days=max_age_days)
        for c in self._components.values():
            if not c.baseline_established_at:
                result.append(c)
                continue
            try:
                baseline_dt = datetime.fromisoformat(c.baseline_established_at)
                if baseline_dt < cutoff:
                    result.append(c)
            except ValueError:
                result.append(c)
        return result

    def overdue_slo_reviews(self, max_age_days: int = 90) -> List[FleetComponent]:
        """Components whose SLO review is older than max_age_days."""
        result = []
        cutoff = datetime.now() - timedelta(days=max_age_days)
        for c in self._components.values():
            if not c.last_slo_review:
                result.append(c)
                continue
            try:
                review_dt = datetime.fromisoformat(c.last_slo_review)
                if review_dt < cutoff:
                    result.append(c)
            except ValueError:
                result.append(c)
        return result

    # ── Quarterly review report ───────────────────────────────

    def quarterly_review_report(self) -> dict:
        """
        Generate a quarterly SLO review report for all fleet components.

        Returns a structured report with:
          - Overall fleet governance health
          - Per-component scores
          - Action items by priority
        """
        components = self.all()
        if not components:
            return {"status": "empty", "components": [], "action_items": []}

        scores = [c.governance_score() for c in components]
        fleet_health = sum(scores) / len(scores)

        healthy = [c for c in components if c.governance_health() == GovernanceHealth.HEALTHY]
        degraded = [c for c in components if c.governance_health() == GovernanceHealth.DEGRADED]
        critical = [c for c in components if c.governance_health() == GovernanceHealth.CRITICAL]

        action_items = []

        # P0: orphaned components
        for c in self.orphaned_components():
            action_items.append({
                "priority": "P0",
                "component": c.component_id,
                "agent": c.agent_id,
                "action": "ASSIGN_SLO_OWNER",
                "detail": "No named SLO owner. Assign immediately.",
            })

        # P1: imminent deprecations
        for c in components:
            days = c.days_until_deprecation()
            if days is not None and days <= 30:
                action_items.append({
                    "priority": "P1",
                    "component": c.component_id,
                    "agent": c.agent_id,
                    "action": "MIGRATE_DEPRECATED_MODEL",
                    "detail": f"Deprecation in {days} days. Owner: {c.slo_owner}",
                })

        # P2: stale baselines
        for c in self.overdue_baselines():
            action_items.append({
                "priority": "P2",
                "component": c.component_id,
                "agent": c.agent_id,
                "action": "REFRESH_BASELINE",
                "detail": "TIE/DQR baseline older than 90 days or missing.",
            })

        # P3: overdue reviews
        for c in self.overdue_slo_reviews():
            action_items.append({
                "priority": "P3",
                "component": c.component_id,
                "agent": c.agent_id,
                "action": "CONDUCT_SLO_REVIEW",
                "detail": "SLO review overdue (>90 days).",
            })

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fleet_governance_score": round(fleet_health, 1),
            "fleet_health": (
                "HEALTHY" if fleet_health >= 80
                else "DEGRADED" if fleet_health >= 50
                else "CRITICAL"
            ),
            "component_count": len(components),
            "healthy_count": len(healthy),
            "degraded_count": len(degraded),
            "critical_count": len(critical),
            "components": [
                {
                    "id": c.component_id,
                    "agent": c.agent_id,
                    "type": c.component_type.value,
                    "owner": c.slo_owner,
                    "score": c.governance_score(),
                    "health": c.governance_health().value,
                    "days_until_deprecation": c.days_until_deprecation(),
                }
                for c in components
            ],
            "action_items": sorted(action_items, key=lambda x: x["priority"]),
        }

    def summary(self) -> str:
        """Human-readable fleet summary for terminal output."""
        report = self.quarterly_review_report()
        lines = [
            f"Agent Fleet Inventory — {report['component_count']} components",
            f"Fleet governance score: {report['fleet_governance_score']}/100 [{report['fleet_health']}]",
            f"  Healthy:  {report['healthy_count']}",
            f"  Degraded: {report['degraded_count']}",
            f"  Critical: {report['critical_count']}",
            "",
            f"Action items: {len(report['action_items'])}",
        ]
        for item in report["action_items"]:
            lines.append(f"  [{item['priority']}] {item['component']} ({item['agent']}): {item['action']}")
        return "\n".join(lines)
