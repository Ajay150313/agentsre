---
name: agentsre
description: Instrument AI agents with SRE reliability signals using the agentsre Python library. Use when adding semantic SLIs (decision quality, tool-call efficiency, human escalation, approval queue drift), blocking duplicate irreversible agent actions, validating agent-to-agent output, or adding a circuit breaker to a multi-agent chain.
---

# agentsre

Reliability instrumentation for agentic AI in production. Standard SLIs (HTTP 200, latency,
error rate) stay green while an agent makes wrong decisions. agentsre measures the semantic layer.

Install: `pip install agentsre` (core has no dependencies; `agentsre[aws]` adds CloudWatch publishing).

## The four SLIs

| SLI | Meaning | Alert when |
|---|---|---|
| DQR | Decision Quality Rate (mean confidence of completed tasks) | below 85% |
| TIE | Tool Invocation Efficiency (tool calls per task vs. baseline) | 1.5x baseline or more |
| HER | Human Escalation Rate | above 5% |
| AQDD | Approval Queue Depth Drift | queue growing vs. baseline |

## Record tasks and read SLIs

```python
from agentsre import AgentSLICollector, TaskRecord

collector = AgentSLICollector()
collector.record(TaskRecord(
    task_id="t-001", task_class="payment-routing",
    tool_calls=3, required_escalation=False, pending_approval=False,
    decision_confidence=0.91, completed=True,
))
for result in collector.collect("payment-routing"):
    print(result)
if collector.breached("payment-routing"):
    ...  # page or degrade
```

Drift is measured against the baseline from earlier `collect()` calls, so call `collect()`
on a schedule. The first call has no baseline and reports `drift_ratio=None`.

## Block a retried write

```python
from agentsre import IdempotencyGuard

guard = IdempotencyGuard(window_seconds=300, max_repeats=1)
decision = guard.check("transfer_funds", {"to": "acct-9", "amount": 120}, scope="user-42")
if not decision.allowed:
    ...  # do not repeat the write
guard.duplicate_action_rate  # export as an SLI
```

The guard is in-process. Across processes, put a conditional write in a shared store in front of it.

## Validate agent-to-agent output

```python
from agentsre import A2ASemanticValidator

v = A2ASemanticValidator(behavioral_threshold=0.75)
v.register_schema("risk", {"required_fields": ["risk_score", "confidence"]})
result = v.validate({"output": {"risk_score": 7.2, "confidence": 0.88}}, "risk-agent", "risk")
if not result.valid:
    ...  # escalate, do not pass downstream
v.semantic_validation_rate("risk-agent", "risk")  # percent, includes structural failures
```

## Circuit breaker on semantic success

```python
from agentsre import AgentChainCircuitBreaker

breaker = AgentChainCircuitBreaker(open_threshold=85.0, close_threshold=95.0)
if not breaker.allow_request("risk-agent", "risk"):
    ...  # use degraded mode
breaker.record_result("risk-agent", "risk", success=result.valid)
```

## Guidance

- Treat `DuplicateActionRate` and semantic validation rate as SLIs with their own SLOs.
- Alert on drift from baseline, not only on absolute thresholds.
- Constrain autonomy when SLIs breach; do not just notify.
- Run tests with `pytest -q`.
