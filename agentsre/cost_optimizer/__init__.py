"""
Cost Optimizer Module for agentsre

Tracks, analyzes, and optimizes costs for AI agents in production.

Features:
- Real-time cost tracking across OpenAI, Anthropic, Bedrock
- Cost per agent, cost per task, cost per operation
- Optimization recommendations (model routing, batch API, caching)
- Budget alerts and hard limits
- Cost anomaly detection

Author: Ajay Devineni
License: MIT
"""

from .tracker import CostTracker, CostMetrics
from .optimizer import CostOptimizer, OptimizationSuggestion
from .alerts import BudgetAlert, AlertManager as CostAlertManager

__all__ = [
    "CostTracker",
    "CostMetrics",
    "CostOptimizer",
    "OptimizationSuggestion",
    "BudgetAlert",
    "CostAlertManager",
]
