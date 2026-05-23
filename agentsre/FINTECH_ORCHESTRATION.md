# Fintech SRE Orchestration System

Production-grade orchestration system for coordinating AI agents in payment systems.

## Features

- **Multi-Agent Coordination**: Manages 5+ agents (payment, risk, compliance, settlement, ops)
- **Semantic Health Monitoring**: Tracks DQR, TIE, HER, AQDD in real-time
- **Progressive Autonomy Constraints**: Automatically downgrades agent autonomy based on semantic drift
- **AWS Integration**: CloudWatch metrics, cost tracking, ROI calculation
- **Fintech Compliance**: Validates transactions against regulatory rules
- **Human Approval Workflows**: Routes high-risk decisions to on-call SRE

## Quick Start

```python
from agentsre.orchestration import FintechSREOrchestrator, AgentRole

orch = FintechSREOrchestrator()
orch.register_agent("payment-1", AgentRole.PAYMENT_PROCESSOR)

orch.update_metrics(
    agent_id="payment-1",
    dqr=94.5,      # Decision Quality Rate
    tie=1.1,       # Tool Invocation Efficiency
    her=1.2,       # Human Escalation Rate
    aqd=5,         # Approval Queue Depth
    confidence=0.96,
    cost=0.0001
)

print(orch.get_autonomy_level("payment-1"))  # FULL
print(orch.get_roi_metrics("payment-1"))
```

## Why This Matters

Traditional monitoring measures infrastructure. Agents fail at the semantic layer.

Real example: DQR 94% → 62%, TIE 1.1x → 3.1x, Queue 8 → 340. Your monitoring says everything is fine. This system says BLOCKED.

Catches semantic failures 48+ hours before traditional SLIs.

## Real-World Scenario

See `examples/fintech_payment_orchestration.py` for complete example.

## Architecture

Each agent tracks:
- **DQR**: Decision Quality Rate (are they picking the right tool?)
- **TIE**: Tool Invocation Efficiency (are they over-compensating?)
- **HER**: Human Escalation Rate (are humans rejecting them?)
- **AQDD**: Approval Queue Depth Drift (is work piling up?)

Autonomy levels:
- **FULL**: High confidence, low drift
- **GUIDED**: Some signs of degradation
- **SUPERVISED**: Significant degradation
- **BLOCKED**: Critical failure risk

## Production Deployment

AWS CloudWatch integration for production environments.

## License

MIT
