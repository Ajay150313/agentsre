# agentsre

**SRE reliability instrumentation for agentic AI in production.**

[![PyPI version](https://img.shields.io/pypi/v/agentsre.svg)](https://pypi.org/project/agentsre/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://pypi.org/project/agentsre/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://github.com/Ajay150313/agentsre/actions/workflows/tests.yml/badge.svg)](https://github.com/Ajay150313/agentsre/actions)

---

## Latest

📝 **[Agent Sprawl is Your Next Production Incident](https://www.linkedin.com/posts/ajay-devineni_agenticai-sre-reliability-ugcPost-7455786901673902080-BCRM)** — LinkedIn (April 30, 2026)

📄 **[Governing Agent Sprawl on AWS](https://builder.aws.com/content/3D6NGmNr6iymtUqZn6lSWcvY09X/governing-agent-sprawl-on-aws-fleet-inventory-framework-canary-and-deprecation-alerting-for-multi-model-bedrock-deployments)** — AWS Community Builders

✍️ **[Agent Sprawl: SRE Response to Datadog's State of AI Engineering 2026](https://dev.to/ajaydevineni/agent-sprawl-is-your-next-production-incident-an-sre-response-to-datadogs-state-of-ai-engineering-3k83)** — DEV Community

---

Your AI agent is returning HTTP 200. Uptime is 99.9%. Every health check is green.

And it's making wrong decisions 30% of the time.

Your current observability stack won't tell you.

**agentsre** implements the four SLIs that catch what CloudWatch, Datadog, and Grafana miss — plus an A2A semantic boundary validator, agent chain circuit breaker, and Agent Sprawl governance module for multi-model, multi-framework production deployments.

---

## Why This Exists: A Real Postmortem

An AI agent in a production environment ran for 6 hours making bad decisions before it caused an outage.

Every metric was green. HTTP 200 responses. 99.99% uptime. P99 latency 142ms. CloudWatch healthy. Datadog healthy. PagerDuty silent.

But the agent was failing at the semantic layer:

- Tool Invocation Efficiency: 2.1 calls/task → 6.8 (3× normal)
- Approval queue: 12 pending → 847 pending
- Decision confidence: 0.92 → 0.41
- Human rejection rate: 1.2% → 19%

None of that triggered an alert. Traditional observability measures infrastructure. AI agents fail at the **semantic layer** — wrong decision, right HTTP 200.

That's why this library exists.

---

## The Problem

```
Agent returns HTTP 200 ✓               — standard SLIs: healthy
Agent confidence drops 92% → 41%      — standard SLIs: healthy
Agent making 6 tool calls instead of 2 — standard SLIs: healthy
Agent escalating 18% of tasks vs 3%   — standard SLIs: healthy
```

---

## The Four SLIs

| SLI | What it catches | Layer |
|-----|----------------|-------|
| **Decision Quality Rate (DQR)** | Semantic drift from behavioral baseline | Leading indicator |
| **Tool Invocation Efficiency (TIE)** | Agent compensating for degraded tools/context | Early warning |
| **Human Escalation Rate (HER)** | Direct operational cost of unreliability | Lagging proxy |
| **Approval Queue Depth Drift (AQDD)** | Human-blocked tasks; queue silently growing¹ | Missing entirely |

> ¹ *AQDD is the failure mode standard SLO burn-rate alerts miss entirely: work submitted, never approved, queue depth growing while dashboards show nothing. Introduced in [this LinkedIn discussion](https://www.linkedin.com/posts/ajay-devineni_agenticai-sre-reliability-ugcPost-7455786901673902080-BCRM).*

---

## Install

```bash
pip install agentsre          # core — zero dependencies
pip install agentsre[aws]     # + boto3 for CloudWatch publishing
```

## Quick Start

```python
from agentsre import AgentSLICollector, TaskRecord

collector = AgentSLICollector()

collector.record(TaskRecord(
    task_id="t-001",
    task_class="payment-routing",
    tool_calls=3,
    required_escalation=False,
    pending_approval=False,
    decision_confidence=0.91,   # 0.0–1.0 from your model output
    completed=True,
))

for result in collector.collect("payment-routing"):
    print(result)
# [DecisionQualityRate]       payment-routing: 91.0%      🟢
# [ToolInvocationEfficiency]  payment-routing: 3.0 calls  🟢
# [HumanEscalationRate]       payment-routing: 0.0%       🟢
# [ApprovalQueueDepthDrift]   payment-routing: 0 pending  🟢

if collector.breached("payment-routing"):
    alert_oncall()
```

## Publish to AWS CloudWatch

```python
from agentsre.cloudwatch import CloudWatchPublisher

publisher = CloudWatchPublisher(agent_id="my-agent")
publisher.publish(collector.collect("payment-routing"))
# → Namespace:  AgentReliability
# → Metrics:    DecisionQualityRate, ToolInvocationEfficiency,
#               HumanEscalationRate, ApprovalQueueDepthDrift
# → Dimensions: AgentId=my-agent, TaskClass=payment-routing
```

## A2A Semantic Boundary Validation

Catches the multi-agent failure mode where HTTP 200s mask semantically wrong output propagating through your agent chain.

```python
from agentsre import A2ASemanticValidator

validator = A2ASemanticValidator(behavioral_threshold=0.75)

validator.register_schema("risk-assessment", {
    "required_fields": ["risk_score", "confidence", "factors"],
    "field_types": {"risk_score": (int, float), "confidence": float},
})

result = validator.validate(
    task_result={"output": {"risk_score": 7.2, "confidence": 0.88, "factors": [...]}},
    sub_agent_id="risk-agent-v2",
    task_class="risk-assessment",
)

if not result.valid:
    route_to_escalation(result)  # do NOT pass to orchestrator
```

## Agent Chain Circuit Breaker

Operates at the semantic validation success rate — not the HTTP success rate.

```python
from agentsre import AgentChainCircuitBreaker

breaker = AgentChainCircuitBreaker(
    open_threshold=85.0,   # open when success rate drops below 85%
    close_threshold=95.0,  # close after recovery probe exceeds 95%
    on_state_change=lambda s: page_oncall(s),
)

if not breaker.allow_request("risk-agent-v2", "risk-assessment"):
    return degraded_mode_handler(task)

breaker.record_result("risk-agent-v2", "risk-assessment", success=validation.valid)
```

## Agent Sprawl Governance (v0.2.0)

Governs the condition where AI agent complexity grows faster than your ability to measure and govern its reliability.

```python
from agentsre.sprawl import AgentFleetInventory, FleetComponent, ComponentType
from agentsre.sprawl import FrameworkVersionGovernance, UpgradeDecision

# Fleet inventory with SLO ownership + deprecation tracking
inventory = AgentFleetInventory()
inventory.register(FleetComponent(
    component_id="anthropic.claude-sonnet-4-6",
    component_type=ComponentType.MODEL,
    agent_id="payment-processor",
    task_classes=["payment-routing"],
    slo_owner="owner@team.com",          # named human — not a team
    baseline_established_at="2026-04-01",
    deprecation_date="2027-06-01",
    last_slo_review="2026-04-01",
    current_tie_baseline=2.4,
    current_dqr_baseline=91.2,
))

print(inventory.summary())
alerts = inventory.pending_deprecation_alerts()  # fires at 60/30/7 days
report = inventory.quarterly_review_report()     # P0-P3 action items

# Framework upgrade canary — blocks promotion if TIE drifts >15%
gov = FrameworkVersionGovernance(tie_drift_threshold=1.15, dqr_drift_threshold=0.85)
gov.snapshot_baseline("payment-processor", "payment-routing", "langchain-0.2.x",
                       tie_values=[2.1, 2.3, 2.0], dqr_values=[91.2, 89.5, 92.0])

result = gov.evaluate_upgrade("payment-processor", "payment-routing",
                               "langchain-0.2.x", "langchain-0.3.x")
if result.decision == UpgradeDecision.BLOCK:
    rollback()  # framework added hidden overhead — don't promote
```

---

## SLO Targets — Where to Start

| SLI | Conservative | Aggressive |
|-----|-------------|-----------|
| DQR | > 85% | > 92% |
| TIE | < 1.5× baseline | < 1.2× baseline |
| HER | < 5% | < 2% |
| AQDD | < 2× baseline | < 1.5× baseline |

**Rule:** Run a 30-day observation window before committing to any SLO target. You cannot commit to reliability you have not yet measured.

---

## Progressive Autonomy Constraint Ladder

```
Level 1 — DQR drops 15% or TIE hits 1.5× baseline
          Enhanced logging. No autonomy reduction.

Level 2 — DQR drops 25% or TIE hits 2× baseline
          Human approval required for write operations.

Level 3 — HER exceeds 2× target
          Read-only mode. All writes require explicit authorization.

Level 4 — Level 3 sustained for 30+ minutes
          Suspend autonomous operation. Page on-call.
```

---

## AWS Architecture

Full implementation guides on AWS Community Builders:

→ **[Governing Agent Sprawl on AWS: Fleet Inventory, Framework Canary, Deprecation Alerting](https://builder.aws.com/content/3D6NGmNr6iymtUqZn6lSWcvY09X/governing-agent-sprawl-on-aws-fleet-inventory-framework-canary-and-deprecation-alerting-for-multi-model-bedrock-deployments)**

Key AWS services:
- **CloudWatch Custom Metrics** — DQR, TIE, HER, AQDD per task class + per model
- **DynamoDB** — behavioral baseline store + agent fleet inventory
- **EventBridge** — breach-triggered investigation workflows + deprecation alerts
- **SSM Automation** — progressive autonomy constraint ladder
- **X-Ray** — distributed tracing across A2A agent boundaries
- **CodePipeline** — framework upgrade canary gate

---

## Related Writing

**LinkedIn:**
- [Agent Sprawl is Your Next Production Incident](https://www.linkedin.com/posts/ajay-devineni_agenticai-sre-reliability-ugcPost-7455786901673902080-BCRM) *(April 30, 2026)*
- [A2A + MCP in Production: The SRE Reliability Framework Nobody Has Written Yet](https://www.linkedin.com/in/ajay-devineni/)
- [SLOs for Agentic AI: The Reliability Framework Production Teams Are Missing](https://www.linkedin.com/in/ajay-devineni/)

**DEV Community:**
- [Agent Sprawl: SRE Response to Datadog's State of AI Engineering 2026](https://dev.to/ajaydevineni/agent-sprawl-is-your-next-production-incident-an-sre-response-to-datadogs-state-of-ai-engineering-3k83)
- [Why SRE Principles Are the Missing Layer in MCP Security](https://dev.to/ajaydevineni/why-sre-principles-are-the-missing-layer-in-mcp-security-2fo8)

**AWS Community Builders:**
- [Governing Agent Sprawl on AWS](https://builder.aws.com/content/3D6NGmNr6iymtUqZn6lSWcvY09X/governing-agent-sprawl-on-aws-fleet-inventory-framework-canary-and-deprecation-alerting-for-multi-model-bedrock-deployments)

---

## Contributing

PRs welcome — especially:
- **Alternative cloud implementations** — GCP (Cloud Monitoring), Azure (Application Insights)
- **Framework integrations** — LangChain, CrewAI, AutoGen, Amazon Bedrock Agents, LlamaIndex
- **Prometheus exporter** — `/metrics` endpoint for self-hosted deployments
- **Additional task-class baseline examples**

See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

---

## License

MIT © [Ajay Devineni](https://linkedin.com/in/ajay-devineni)

---

*If this helped you instrument your agents in production, a ⭐ means a lot — it helps other SRE practitioners find this library.*

---

## 🎯 Enterprise Feature: Fintech SRE Orchestration

Production system for coordinating AI agents in payment processing.

**What it does:**
- Monitors 5+ agents with semantic SLIs (DQR, TIE, HER, AQDD)
- Automatically constrains autonomy when semantic drift detected
- Publishes to AWS CloudWatch
- Validates transactions against compliance rules
- Tracks cost and ROI per agent

**Why it matters:**
Catches semantic failures (wrong decisions despite HTTP 200) 48+ hours before traditional SLIs fire.

See [FINTECH_ORCHESTRATION.md](agentsre/FINTECH_ORCHESTRATION.md) for details.

---

## v0.5.0: Cost Optimization Module

Production cost tracking for AI agents.

**Features:**
- Real-time cost tracking (OpenAI, Anthropic models)
- Cost per agent, cost per task
- Optimization recommendations
- Budget alerts

**Quick start:**

```python
from agentsre.cost_optimizer import CostTracker, CostOptimizer

tracker = CostTracker()

# Track API calls
tracker.track_api_call(
    agent_id="payment-router",
    model="claude-opus",
    input_tokens=1000,
    output_tokens=500
)

# Get metrics
metrics = tracker.get_metrics("payment-router")
print(f"Cost per call: ${metrics.cost_per_call():.4f}")

# Get suggestions
optimizer = CostOptimizer(tracker)
suggestions = optimizer.analyze()
```


## Architecture Mapping — Google SRE AI Whitepaper (May 2026)

| Google Component | agentsre Module | Description |
|---|---|---|
| Actus (execution guardrails) | `pre_action_gate.py` | Error budget + AQDD + HER gate before action |
| IRM Analyzer (eval pipelines) | `eval_pipeline.py` | DQR trend + regression detection |
| AI Operator (agent governance) | `aro.py` + `sprawl_registry.py` | ARO registration + fleet PRR |
| Human operational memory | `reasoning_trace.py` | RTD traces as ground truth corpus |

Reference: https://sre.google/resources/practices-and-processes/ai-engineering-reliable-operations/
