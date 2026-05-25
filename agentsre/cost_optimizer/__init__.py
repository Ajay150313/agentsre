"""
Cost Optimizer Module for agentsre

Tracks and optimizes costs for AI agents in production.

Author: Ajay Devineni
License: MIT
"""

__version__ = "0.5.0"
__author__ = "Ajay Devineni"

# Import classes but catch import errors gracefully
try:
    from .tracker import CostTracker, CostMetrics
    from .optimizer import CostOptimizer, OptimizationSuggestion
    from .alerts import BudgetAlert, CostAlertManager
    
    __all__ = [
        "CostTracker",
        "CostMetrics", 
        "CostOptimizer",
        "OptimizationSuggestion",
        "BudgetAlert",
        "CostAlertManager",
    ]
except ImportError as e:
    print(f"Warning: Could not import cost_optimizer modules: {e}")
    __all__ = []
