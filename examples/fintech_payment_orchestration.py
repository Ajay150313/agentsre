"""
Real-World Example: Payment Processing SRE with Multi-Agent Orchestration

Demonstrates a fintech payment system with 5 coordinated agents.
Shows how semantic SLI degradation triggers progressive autonomy constraints.

Author: Ajay Devineni
License: MIT
"""

import json
from datetime import datetime
from agentsre.orchestration.orchestrator import (
    FintechSREOrchestrator,
    FintechComplianceValidator,
    AWSCloudWatchPublisher,
    AgentRole,
    AutonomyLevel
)


def simulate_payment_processing_day():
    """Simulate a day of payment processing with SRE orchestration"""
    
    print("=" * 80)
    print("FINTECH PAYMENT ORCHESTRATION - SRE EXAMPLE")
    print("=" * 80)
    
    orchestrator = FintechSREOrchestrator(
        namespace="PaymentProcessing",
        region="us-east-1"
    )
    
    compliance = FintechComplianceValidator()
    cw_publisher = AWSCloudWatchPublisher()
    
    agents = {
        "payment-proc-1": AgentRole.PAYMENT_PROCESSOR,
        "risk-assess-1": AgentRole.RISK_ASSESSOR,
        "compliance-1": AgentRole.COMPLIANCE_CHECKER,
        "settlement-1": AgentRole.SETTLEMENT,
        "ops-1": AgentRole.OPERATIONS,
    }
    
    for agent_id, role in agents.items():
        orchestrator.register_agent(agent_id, role, initial_autonomy=AutonomyLevel.FULL)
    
    def on_approval_needed(decision):
        print(f"\n🚨 AUTONOMY CHANGE: {decision.agent_id}")
        print(f"   {decision.previous_level.value} → {decision.new_level.value}")
        print(f"   Reason: {decision.reason}")
    
    orchestrator.approval_handler = on_approval_needed
    
    # SCENARIO 1: Normal operation
    print("\n" + "=" * 80)
    print("SCENARIO 1: Morning - Normal Operations (09:00 AM)")
    print("=" * 80)
    
    orchestrator.update_metrics("payment-proc-1", dqr=95.2, tie=1.08, her=0.8, aqd=8, confidence=0.97, cost=0.00008)
    orchestrator.update_metrics("risk-assess-1", dqr=92.1, tie=1.12, her=1.5, aqd=12, confidence=0.93, cost=0.00012)
    
    print(f"✅ All agents operating at full autonomy")
    
    # SCENARIO 2: Degradation
    print("\n" + "=" * 80)
    print("SCENARIO 2: Noon - Service Degradation Detected")
    print("=" * 80)
    
    orchestrator.update_metrics("payment-proc-1", dqr=88.5, tie=1.45, her=3.2, aqd=45, confidence=0.81, cost=0.00015)
    orchestrator.update_metrics("risk-assess-1", dqr=84.0, tie=1.58, her=6.8, aqd=92, confidence=0.72, cost=0.00018)
    
    # SCENARIO 3: Critical failure
    print("\n" + "=" * 80)
    print("SCENARIO 3: 3:00 PM - Cascading Semantic Failure")
    print("=" * 80)
    
    decision = orchestrator.update_metrics("payment-proc-1", dqr=62.0, tie=3.1, her=18.5, aqd=340, confidence=0.41, cost=0.00025)
    orchestrator.update_metrics("risk-assess-1", dqr=55.0, tie=4.2, her=22.0, aqd=580, confidence=0.38, cost=0.00032)
    
    print(f"🛑 Payment processor BLOCKED")
    
    # SCENARIO 4: Recovery
    print("\n" + "=" * 80)
    print("SCENARIO 4: 4:00 PM - Recovery")
    print("=" * 80)
    
    orchestrator.update_metrics("payment-proc-1", dqr=91.5, tie=1.15, her=2.1, aqd=52, confidence=0.89, cost=0.00009)
    orchestrator.update_metrics("risk-assess-1", dqr=89.2, tie=1.18, her=3.2, aqd=78, confidence=0.85, cost=0.00011)
    
    print("✅ Agents returning to full autonomy")
    
    # Final report
    print("\n" + "=" * 80)
    print("END OF DAY REPORT")
    print("=" * 80)
    print(json.dumps(orchestrator.get_orchestration_health(), indent=2))
    
    # ROI Analysis
    print("\n" + "=" * 80)
    print("COST & ROI ANALYSIS")
    print("=" * 80)
    
    for agent_id in agents.keys():
        roi = orchestrator.get_roi_metrics(agent_id)
        print(f"\n{agent_id}:")
        for k, v in roi.items():
            if k not in ["agent_id", "hours"]:
                print(f"  {k:30s}: {v}")
    
    # Autonomy decisions
    print("\n" + "=" * 80)
    print("AUTONOMY DECISIONS MADE")
    print("=" * 80)
    
    for i, decision in enumerate(orchestrator.decision_history, 1):
        print(f"\n{i}. {decision.agent_id}")
        print(f"   {decision.previous_level.value} → {decision.new_level.value}")
        print(f"   Triggered by: {', '.join(decision.triggered_by)}")


if __name__ == "__main__":
    simulate_payment_processing_day()
