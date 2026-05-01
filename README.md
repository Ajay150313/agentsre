# agentsre

**SRE reliability instrumentation for agentic AI in production.**

[![PyPI version](https://img.shields.io/pypi/v/agentsre.svg)](https://pypi.org/project/agentsre/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://pypi.org/project/agentsre/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://github.com/ajay-devineni/agentsre/actions/workflows/tests.yml/badge.svg)](https://github.com/ajay-devineni/agentsre/actions)

---

Your AI agent is returning HTTP 200. Uptime is 99.9%. Every health check is green.

And it's making wrong decisions 30% of the time.

Your current observability stack won't tell you.

**agentsre** implements the four SLIs that catch what CloudWatch, Datadog, and Grafana miss — plus an A2A semantic boundary validator and agent chain circuit breaker for multi-agent systems.
## Why This Exists: A Real Postmortem

We had an AI agent managing payment routing in production. It ran for 6 hours making bad decisions before it caused an outage.

Here's the weird part: every metric was green. HTTP 200 responses. 99.99% uptime. P99 latency 142ms. CloudWatch said everything was healthy. Datadog said everything was healthy. PagerDuty didn't page anyone.

But the agent was falling apart.

Tool Invocation Efficiency went from 2.1 calls per task to 6.8 (3x normal). The approval queue grew from 12 pending items to 847. Decision confidence dropped from 0.92 to 0.41. And humans were rejecting 19% of decisions instead of the normal 1.2%.

None of that triggered an alert.

That's because traditional observability measures infrastructure. Network latency, error rates, uptime. But AI agents don't fail at the infrastructure layer. They fail at the semantic layer. Wrong decision, right HTTP 200.

We built agentsre after that outage. It measures what actually matters for agents.

## The problem

Traditional SLIs measure infrastructure-layer signals: latency, error rate, availability. AI agents fail at the **semantic layer** — wrong tool selection, context misinterpretation, output drift. These failures produce no HTTP errors. Your dashboards stay green.

```
Agent returns HTTP 200 ✓          — standard SLIs: healthy
Agent confidence drops from 92% to 41% — standard SLIs: healthy  
Agent making 6 tool calls instead of 2  — standard SLIs: healthy
Agent escalating 18% of tasks vs 3%     — standard SLIs: healthy
```

## The four SLIs

| SLI | What it catches | Layer |
|-----|----------------|-------|
| **Decision Quality Rate (DQR)** | Semantic drift from behavioral baseline | Leading indicator |
| **Tool Invocation Efficiency (TIE)** | Agent compensating for degraded tools/context | Early warning |
| **Human Escalation Rate (HER)** | Direct operational cost of unreliability | Lagging proxy |
| **Approval Queue Depth Drift (AQDD)** | Human-blocked tasks; queue silently growing¹ | Missing entirely |

> ¹ *AQDD is the failure mode standard SLO burn-rate alerts miss entirely: work submitted, never approved, queue depth growing while your dashboards show nothing. Introduced in [this LinkedIn discussion](https://linkedin.com/in/ajay-devineni).*

---

## Install

```bash
pip install agentsre          # core — zero dependencies
pip install agentsre[aws]     # + boto3 for CloudWatch publishing
```

## Quick start

```python
from agentsre import AgentSLICollector, TaskRecord

collector = AgentSLICollector()

# Record each task your agent completes
collector.record(TaskRecord(
    task_id="t-001",
    task_class="payment-routing",
    tool_calls=3,
    required_escalation=False,
    pending_approval=False,
    decision_confidence=0.91,   # 0.0–1.0 from your model output
    completed=True,
))

# Get all four SLIs
for result in collector.collect("payment-routing"):
    print(result)
# [DecisionQualityRate]       payment-routing: 91.0%       🟢
# [ToolInvocationEfficiency]  payment-routing: 3.0 calls   🟢
# [HumanEscalationRate]       payment-routing: 0.0%        🟢
# [ApprovalQueueDepthDrift]   payment-routing: 0 pending   🟢

# Only get breaches
if collector.breached("payment-routing"):
    alert_oncall()
```

## Publish to AWS CloudWatch

```python
from agentsre.cloudwatch import CloudWatchPublisher

publisher = CloudWatchPublisher(agent_id="financial-processor")
publisher.publish(collector.collect("payment-routing"))
# → Namespace: AgentReliability
# → Metrics:   DecisionQualityRate, ToolInvocationEfficiency,
#              HumanEscalationRate, ApprovalQueueDepthDrift
# → Dimensions: AgentId=financial-processor, TaskClass=payment-routing
```

## A2A semantic boundary validation

Catches the failure mode A2A multi-agent systems introduce: HTTP 200, valid JSON — but semantically wrong output that silently propagates through your agent chain.

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
    # Do NOT pass to orchestrator
    route_to_escalation(result)
```

## Agent chain circuit breaker

Operates at the semantic layer — opens when validated success rate drops, not when HTTP errors spike.

```python
from agentsre import AgentChainCircuitBreaker

breaker = AgentChainCircuitBreaker(
    open_threshold=85.0,   # open when success rate drops below 85%
    close_threshold=95.0,  # close after recovery probe exceeds 95%
    on_state_change=lambda s: page_oncall(s),
)

# Before each A2A delegation:
if not breaker.allow_request("risk-agent-v2", "risk-assessment"):
    return degraded_mode_handler(task)   # circuit is OPEN

# After validating the result:
breaker.record_result("risk-agent-v2", "risk-assessment", success=validation.valid)
```

---

## SLO targets — where to start

| SLI | Conservative target | Aggressive target |
|-----|-------------------|-------------------|
| DQR | > 85% | > 92% |
| TIE | < 1.5× baseline | < 1.2× baseline |
| HER | < 5% | < 2% |
| AQDD | < 2× baseline depth | < 1.5× baseline depth |

**Rule:** Run a 30-day observation window before committing to any SLO target. You cannot commit to reliability you have not yet measured.

---

## Progressive autonomy constraint ladder

When SLIs breach, don't kill the agent — reduce autonomy progressively:

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

See [`examples/progressive_constraints.py`](examples/) for the AWS SSM Automation implementation.

---

## AWS architecture

Full implementation guide on AWS Community Builders:  
→ [Single-agent + MCP: SLOs for Agentic AI on AWS](https://community.aws)  
→ [Multi-agent + A2A: The SRE Reliability Framework Nobody Has Written Yet](https://community.aws)

Key services used:
- **CloudWatch Custom Metrics** — DQR, TIE, HER, AQDD per task class
- **DynamoDB** — behavioral baseline store with 7-day rolling window
- **EventBridge** — breach-triggered investigation workflows
- **SSM Automation** — progressive autonomy constraint ladder
- **X-Ray** — distributed tracing across A2A agent boundaries

---

## The story behind this library

This library emerged from a production postmortem. An AI agent in a regulated financial services environment ran for **6 hours in silent failure mode** — no alerts, no pages, zero CloudWatch alarms — before causing a 40-minute outage.

The agent's Tool Invocation Efficiency had climbed from 2.1 to 6.8 calls per task. A degraded upstream service was returning ambiguous responses; the agent compensated by invoking 3× more tools. Task completion rate: 99%. Health checks: green. Every SLI we had: healthy.

The data was there. The SLI wasn't.

That's why this library exists.

---

## Contributing

PRs welcome — especially:
- **Alternative cloud implementations** — GCP (Cloud Monitoring), Azure (Application Insights)
- **Framework integrations** — LangChain, CrewAI, AutoGen, Amazon Bedrock Agents, LlamaIndex
- **Additional task-class baseline examples** for common agent patterns
- **Prometheus exporter** — `/metrics` endpoint for self-hosted deployments

See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

---

## Related writing

- [SLOs for Agentic AI: The Reliability Framework Production Teams Are Missing](https://dev.to/ajaydevineni) — DEV Community
- [Why SRE Principles Are the Missing Layer in MCP Security](https://dev.to/ajaydevineni) — DEV Community  
- [Multi-Agent Reliability on AWS: Building SRE Infrastructure for A2A + MCP](https://community.aws) — AWS Community Builders

---

## License

MIT © [Ajay Devineni](https://linkedin.com/in/ajay-devineni)

---

*If this helped you instrument your agents in production, a ⭐ means a lot — it helps other SRE practitioners find this library.*
