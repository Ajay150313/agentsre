"""
Integration example: Using v0.4.0 orchestration with existing agentsre code

Shows how:
- Old code (AgentSLICollector) records task metrics
- New code (FintechSREOrchestrator) monitors semantic health
- AlertManager sends notifications when thresholds breach

Author: Ajay Devineni
License: MIT
"""

from agentsre import AgentSLICollector, TaskRecord
from agentsre.orchestration import FintechSREOrchestrator, AlertManager, AgentRole, AlertSeverity

# Initialize existing metrics collector
collector = AgentSLICollector()

# Initialize new orchestrator
orchestrator = FintechSREOrchestrator(namespace="PaymentProcessing")
orchestrator.register_agent("payment-1", AgentRole.PAYMENT_PROCESSOR)

# Initialize new alert manager
alert_manager = AlertManager()

def on_alert(alert_dict):
    print(f"\n🚨 ALERT: {alert_dict['agent_id']} - {alert_dict['severity']}")

alert_manager.slack_handler = on_alert

# Scenario 1: Record tasks with existing collector
print("=" * 80)
print("SCENARIO 1: Recording tasks with AgentSLICollecprint("SCENARIO 1: Recording tasks with AgentSLICollecprint("SCENARIO 1: Rcord(TaskRecorprint("SCENARIO 1: Recording tasks with AgentSLICos=print("SCENARIO 1: Recording tasks with AgentSLICollecprintscprint("SCENARIO 1: Recording tasks with AgentSLICollecpdeciprint("SCENARIe=0.95,
print("SCENpleted=True,
    ))

# Get metrics from existing code
metrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrmetrUsemetrmetrmetrmetrmetrmetrmetrmetrmetrm code)
print("\n" + "=" * 80)
print(print(print(print(print(prinntprint(print(print(print(print(prinntprint(print(print(print(printom collector results
dqr = 95.5  # From collector above

# Update orchestra# Update orchestra# Update otra# Update orchestra# Update or_id# Update orches   dqr=dqr,
    tie=1.1,
    her=0.5,
    aqd=2,
    confidence=0.95,
    cost=0.0001
)

print(f"✅ Agent autonomy level: {orchestrprint(f"✅ Agent autonomy level: {orchestrp)

# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc# Trigge# Sc# Sc# Sc#  ## Sc# Sc# Sc# Tr
    confidence=0.42,
    cost=0.0003
)

# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create#et# Create# Create# , "HE# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Createt(f"✅ Alert created: {alert.severity# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create# Create#rat# Create# Cge# Createediations[:3], 1):
    print(f"  {i}. {step.action} ({step.estimated_time_minutes}min)")

print("\n" + "=" * 80)
print("INTEGRATION SUCCESSFUL")
print("=" * 80)
print("✅ Old code (AgentSLICollector) collecting task metrics")
print("✅ New code (FintechSREOrchestrator) monitoring semantic health")
print("✅ New code (AlertManager) sending alerts on degradation")
print("\nBoth systems work together seamlessly!")
