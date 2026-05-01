"""
agentsre.sprawl
~~~~~~~~~~~~~~~
Agent Sprawl governance — the reliability layer for multi-model,
multi-framework production AI deployments.

Agent Sprawl (Devineni, 2026):
    The condition where AI agent infrastructure complexity grows
    faster than your ability to measure and govern its reliability.

Modules:
    inventory           — Agent fleet inventory with SLO ownership + deprecation tracking
    framework_governance — Framework upgrade canary + baseline comparison
"""

from .inventory import (
    AgentFleetInventory,
    FleetComponent,
    ComponentType,
    GovernanceHealth,
    DeprecationAlert,
)
from .framework_governance import (
    FrameworkVersionGovernance,
    BaselineSnapshot,
    ShadowComparison,
    UpgradeDecision,
)

__all__ = [
    "AgentFleetInventory",
    "FleetComponent",
    "ComponentType",
    "GovernanceHealth",
    "DeprecationAlert",
    "FrameworkVersionGovernance",
    "BaselineSnapshot",
    "ShadowComparison",
    "UpgradeDecision",
]
