"""
Quick-start example: agentsre in a financial services agent pipeline.

Shows all four SLIs + A2A validation + circuit breaker working together.
Run with: python examples/quickstart.py
"""

import random
import time

from agentsre import (
    AgentSLICollector,
    TaskRecord,
    A2ASemanticValidator,
    AgentChainCircuitBreaker,
)
from agentsre.cloudwatch import CloudWatchPublisher

# ── 1. Initialise ─────────────────────────────────────────────

collector = AgentSLICollector(window_seconds=3600)
validator = A2ASemanticValidator(behavioral_threshold=0.75)
breaker   = AgentChainCircuitBreaker(
    open_threshold=85.0,
    window_size=20,
    on_state_change=lambda s: print(f"\n⚡ CIRCUIT STATE CHANGE → {s}\n"),
)
publisher = CloudWatchPublisher(agent_id="financial-processor", dry_run=True)

# Register A2A schema for the risk-assessment sub-agent
validator.register_schema(
    "risk-assessment",
    {
        "required_fields": ["risk_score", "confidence", "factors"],
        "field_types": {"risk_score": (int, float), "confidence": float},
    },
)

# ── 2. Simulate a payment-routing agent workload ──────────────

print("=" * 60)
print("agentsre — quick-start simulation")
print("Simulating 30 payment-routing tasks...")
print("=" * 60)

for i in range(30):
    task_id = f"task-{i:03d}"

    # Introduce degradation after task 20 to trigger TIE + DQR drift
    degraded = i >= 20

    record = TaskRecord(
        task_id=task_id,
        task_class="payment-routing",
        tool_calls=random.randint(6, 9) if degraded else random.randint(2, 3),
        required_escalation=random.random() < (0.30 if degraded else 0.03),
        pending_approval=random.random() < 0.05,
        decision_confidence=random.uniform(0.45, 0.65) if degraded else random.uniform(0.85, 0.98),
        completed=True,
    )
    collector.record(record)

# ── 3. Collect and display SLI results ───────────────────────

print("\n📊 SLI Results — payment-routing\n")
results = collector.collect("payment-routing")
for r in results:
    icon = "🔴" if r.breached else "🟢"
    print(f"  {icon}  {r}")

# Publish to CloudWatch (dry_run=True — prints instead of sending)
print("\n☁️  CloudWatch publish (dry run):")
publisher.publish(results)

# ── 4. A2A validation simulation ─────────────────────────────

print("\n\n🔍 A2A Semantic Boundary Validation — risk-assessment sub-agent\n")

sub_agent_results = [
    # Good results
    {"output": {"risk_score": 7.2, "confidence": 0.91, "factors": ["velocity", "geo"]}},
    {"output": {"risk_score": 3.1, "confidence": 0.88, "factors": ["known-device"]}},
    {"output": {"risk_score": 8.9, "confidence": 0.95, "factors": ["new-payee", "large-amount"]}},
    # Degraded results (missing fields, low confidence)
    {"output": {"risk_score": 5.0}},                          # missing confidence + factors
    {"output": {"risk_score": 4.1, "confidence": 0.20}},      # confidence below threshold
    {"output": {}},                                            # empty output
]

for raw in sub_agent_results:
    vr = validator.validate(raw, "risk-agent-v2", "risk-assessment")
    breaker.record_result("risk-agent-v2", "risk-assessment", success=vr.valid)
    icon = "✅" if vr.valid else "❌"
    print(f"  {icon}  {vr}")

print(f"\n  Circuit status: {breaker.status('risk-agent-v2', 'risk-assessment')}")
svr = validator.semantic_validation_rate("risk-agent-v2", "risk-assessment")
print(f"  Semantic validation rate: {svr:.1f}%")

# ── 5. Summary ────────────────────────────────────────────────

print("\n\n📋 Breach Summary\n")
breaches = collector.breached("payment-routing")
if breaches:
    for b in breaches:
        print(f"  ⚠  {b.name} breached — drift={b.drift_ratio}x baseline")
else:
    print("  ✅ No breaches detected")

print("\n✓ Done. Deploy agentsre to see real metrics in CloudWatch.\n")
print("  pip install agentsre[aws]")
print("  publisher = CloudWatchPublisher(agent_id='your-agent', dry_run=False)")
