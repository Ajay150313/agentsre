"""
Agent Sprawl Governance — quickstart example.

Demonstrates:
  - Building an agent fleet inventory
  - Running a quarterly review
  - Framework upgrade governance with canary comparison
  - Deprecation alerting

Run with: python examples/sprawl/agent_sprawl_governance.py
"""

import random
from datetime import datetime, timedelta

from agentsre.sprawl import (
    AgentFleetInventory,
    FleetComponent,
    ComponentType,
    FrameworkVersionGovernance,
)

print("=" * 65)
print("agentsre — Agent Sprawl Governance Demo")
print("=" * 65)

# ── 1. Build the fleet inventory ─────────────────────────────

inventory = AgentFleetInventory()

# Model 1: well-governed
inventory.register(FleetComponent(
    component_id="anthropic.claude-sonnet-4-6",
    component_type=ComponentType.MODEL,
    agent_id="payment-processor",
    task_classes=["payment-routing", "fraud-detection"],
    slo_owner="ajay@team.com",
    framework_version="bedrock-agents-2.1",
    baseline_established_at=datetime.now().strftime("%Y-%m-%d"),
    deprecation_date=(datetime.now() + timedelta(days=400)).strftime("%Y-%m-%d"),
    last_slo_review=datetime.now().strftime("%Y-%m-%d"),
    current_tie_baseline=2.4,
    current_dqr_baseline=91.2,
))

# Model 2: governance debt — no owner, stale baseline
inventory.register(FleetComponent(
    component_id="gpt-4o",
    component_type=ComponentType.MODEL,
    agent_id="payment-processor",
    task_classes=["document-analysis"],
    slo_owner="",               # ← orphaned! no owner
    framework_version="openai-sdk-1.x",
    baseline_established_at="2025-10-01",   # ← stale baseline
    deprecation_date=(datetime.now() + timedelta(days=25)).strftime("%Y-%m-%d"),
    last_slo_review="2025-10-01",
    current_tie_baseline=3.1,
    current_dqr_baseline=87.4,
))

# Model 3: critically close to deprecation
inventory.register(FleetComponent(
    component_id="anthropic.claude-haiku-4-5",
    component_type=ComponentType.MODEL,
    agent_id="support-agent",
    task_classes=["ticket-routing"],
    slo_owner="sreeng@team.com",
    baseline_established_at=(datetime.now() - timedelta(days=50)).strftime("%Y-%m-%d"),
    deprecation_date=(datetime.now() + timedelta(days=6)).strftime("%Y-%m-%d"),  # ← 6 days!
    last_slo_review=(datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d"),
    current_tie_baseline=1.8,
    current_dqr_baseline=88.9,
))

print("\n📋 Fleet Inventory Summary\n")
print(inventory.summary())

# ── 2. Pending deprecation alerts ────────────────────────────

print("\n\n⚠️  Deprecation Alerts\n")
alerts = inventory.pending_deprecation_alerts()
if alerts:
    for alert in alerts:
        print(f"  🔴 {alert.component_id}")
        print(f"     Owner: {alert.slo_owner or 'UNASSIGNED'}")
        print(f"     Days remaining: {alert.days_remaining}")
        print(f"     Affected task classes: {alert.task_classes}")
else:
    print("  ✅ No pending alerts")

# ── 3. Quarterly review report ───────────────────────────────

print("\n\n📊 Quarterly Review Report\n")
report = inventory.quarterly_review_report()
print(f"  Fleet governance score: {report['fleet_governance_score']}/100")
print(f"  Fleet health: {report['fleet_health']}")
print(f"\n  Action items ({len(report['action_items'])}):")
for item in report["action_items"]:
    icon = {"P0": "🔴", "P1": "🟠", "P2": "🟡", "P3": "🔵"}.get(item["priority"], "•")
    print(f"  {icon} [{item['priority']}] {item['component']} — {item['action']}")
    print(f"       {item['detail']}")

# ── 4. Framework upgrade governance ──────────────────────────

print("\n\n🔬 Framework Upgrade Governance\n")
print("  Scenario: upgrading LangChain 0.2.x → 0.3.x")

gov = FrameworkVersionGovernance(
    tie_drift_threshold=1.15,
    dqr_drift_threshold=0.85,
    min_shadow_samples=20,
)

# Capture pre-upgrade baseline
gov.snapshot_baseline(
    agent_id="payment-processor",
    task_class="payment-routing",
    framework_version="langchain-0.2.x",
    tie_values=[2.1, 2.3, 2.0, 2.4, 2.2, 2.3, 2.1, 2.0] * 5,
    dqr_values=[91.2, 89.5, 92.0, 90.8, 91.5, 90.2, 92.1, 91.0] * 5,
)
print("  ✓ Pre-upgrade baseline captured")

# Simulate shadow traffic — SCENARIO A: framework adds overhead (drift > 15%)
print("\n  [Scenario A] New framework adds hidden retry overhead:")
for _ in range(25):
    gov.record_shadow_result(
        agent_id="payment-processor",
        task_class="payment-routing",
        shadow_version="langchain-0.3.x",
        tie=random.uniform(2.6, 3.2),   # elevated — framework overhead
        dqr=random.uniform(89.0, 92.0),
    )

result_a = gov.evaluate_upgrade(
    agent_id="payment-processor",
    task_class="payment-routing",
    production_version="langchain-0.2.x",
    shadow_version="langchain-0.3.x",
)
print(f"  {result_a}")

# Reset for scenario B
gov.reset_shadow("payment-processor", "payment-routing")

# SCENARIO B: clean upgrade, within bounds
print("\n  [Scenario B] Clean upgrade, no framework overhead:")
for _ in range(25):
    gov.record_shadow_result(
        agent_id="payment-processor",
        task_class="payment-routing",
        shadow_version="langchain-0.3.1-fixed",
        tie=random.uniform(2.1, 2.4),   # normal range
        dqr=random.uniform(90.0, 93.0),
    )

result_b = gov.evaluate_upgrade(
    agent_id="payment-processor",
    task_class="payment-routing",
    production_version="langchain-0.2.x",
    shadow_version="langchain-0.3.1-fixed",
)
print(f"  {result_b}")

print("\n✓ Done. This is the governance layer agent sprawl requires.\n")
print("  pip install agentsre")
print("  from agentsre.sprawl import AgentFleetInventory, FrameworkVersionGovernance\n")
