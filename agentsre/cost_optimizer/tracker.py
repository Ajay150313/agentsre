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
EOF

# Verify
cat agentsre/cost_optimizer/__init__.py

STEP 4: Create cost_optimizer/tracker.py (Main Code)
bashcat > agentsre/cost_optimizer/tracker.py << 'ENDFILE'
"""
Cost tracking for AI agents - tracks all API calls and calculates costs

Author: Ajay Devineni
License: MIT
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    GOOGLE = "google"


@dataclass
class TokenUsage:
    """Token usage for a single API call"""
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    model: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CostMetrics:
    """Cost metrics for an agent or task"""
    agent_id: str
    total_cost: float = 0.0
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    avg_cost_per_call: float = 0.0
    cost_per_successful_call: float = 0.0
    by_model: Dict[str, float] = field(default_factory=dict)
    by_operation: Dict[str, float] = field(default_factory=dict)
    last_24h_cost: float = 0.0
    last_30d_cost: float = 0.0


class CostTracker:
    """
    Tracks costs for AI agents across multiple providers.
    
    Supports: OpenAI, Anthropic, Bedrock, Google
    """
    
    # Pricing as of May 2026 (update as needed)
    PRICING = {
        "openai": {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-4o": {"input": 0.005, "output": 0.015},
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        },
        "anthropic": {
            "claude-opus": {"input": 0.015, "output": 0.075},
            "claude-sonnet": {"input": 0.003, "output": 0.015},
            "claude-haiku": {"input": 0.00080, "output": 0.0024},
        },
        "bedrock": {
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00080, "output": 0.0024},
        }
    }
    
    def __init__(self):
        self.calls: List[Dict] = []
        self.agent_metrics: Dict[str, CostMetrics] = {}
        self.daily_budget: Optional[float] = None
        self.monthly_budget: Optional[float] = None
        self.alert_thresholds = {"50": 0.5, "80": 0.8, "100": 1.0}
    
    def track_api_call(
        self,
        agent_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        success: bool = True,
        operation: str = "default"
    ) -> float:
        """
        Track an API call and calculate cost
        
        Returns: cost of this call
        """
        
        # Get model pricing
        cost = self._calculate_cost(model, input_tokens, output_tokens, cached_tokens)
        
        # Record call
        call_record = {
            "agent_id": agent_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "cost": cost,
            "success": success,
            "operation": operation,
            "timestamp": datetime.now().isoformat()
        }
        
        self.calls.append(call_record)
        
        # Update metrics
        self._update_metrics(agent_id, model, operation, cost, success)
        
        # Check budget alerts
        self._check_budget_alerts()
        
        logger.info(f"Tracked {agent_id}: {model} - ${cost:.4f} ({input_tokens}i, {output_tokens}o)")
        
        return cost
    
    def _calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0
    ) -> float:
        """Calculate cost for API call"""
        
        # Find pricing
        for provider, models in self.PRICING.items():
            if model in models:
                pricing = models[model]
                
                # Cached tokens cost less (usually 90% discount)
                cached_cost = (cached_tokens * pricing["input"]) * 0.1
                input_cost = ((input_tokens - cached_tokens) * pricing["input"])
                output_cost = (output_tokens * pricing["output"])
                
                return (input_cost + output_cost + cached_cost) / 1_000_000
        
        logger.warning(f"Unknown model {model} - returning $0")
        return 0.0
    
    def _update_metrics(
        self,
        agent_id: str,
        model: str,
        operation: str,
        cost: float,
        success: bool
    ) -> None:
        """Update metrics for agent"""
        
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = CostMetrics(agent_id=agent_id)
        
        metrics = self.agent_metrics[agent_id]
        metrics.total_cost += cost
        metrics.total_calls += 1
        
        if success:
            metrics.successful_calls += 1
        else:
            metrics.failed_calls += 1
        
        # By model
        if model not in metrics.by_model:
            metrics.by_model[model] = 0.0
        metrics.by_model[model] += cost
        
        # By operation
        if operation not in metrics.by_operation:
            metrics.by_operation[operation] = 0.0
        metrics.by_operation[operation] += cost
        
        # Calculate averages
        metrics.avg_cost_per_call = metrics.total_cost / metrics.total_calls if metrics.total_calls > 0 else 0
        metrics.cost_per_successful_call = metrics.total_cost / metrics.successful_calls if metrics.successful_calls > 0 else 0
        
        # Last 24h and 30d
        cutoff_24h = datetime.now() - timedelta(hours=24)
        cutoff_30d = datetime.now() - timedelta(days=30)
        
        metrics.last_24h_cost = sum(
            c["cost"] for c in self.calls 
            if c["agent_id"] == agent_id and datetime.fromisoformat(c["timestamp"]) > cutoff_24h
        )
        
        metrics.last_30d_cost = sum(
            c["cost"] for c in self.calls 
            if c["agent_id"] == agent_id and datetime.fromisoformat(c["timestamp"]) > cutoff_30d
        )
    
    def get_metrics(self, agent_id: str) -> Optional[CostMetrics]:
        """Get cost metrics for agent"""
        return self.agent_metrics.get(agent_id)
    
    def get_all_metrics(self) -> Dict[str, CostMetrics]:
        """Get metrics for all agents"""
        return self.agent_metrics
    
    def set_daily_budget(self, amount: float) -> None:
        """Set daily budget limit"""
        self.daily_budget = amount
        logger.info(f"Daily budget set to ${amount:.2f}")
    
    def set_monthly_budget(self, amount: float) -> None:
        """Set monthly budget limit"""
        self.monthly_budget = amount
        logger.info(f"Monthly budget set to ${amount:.2f}")
    
    def _check_budget_alerts(self) -> None:
        """Check if budgets exceeded"""
        
        today_cost = sum(
            c["cost"] for c in self.calls
            if datetime.fromisoformat(c["timestamp"]).date() == datetime.now().date()
        )
        
        if self.daily_budget:
            utilization = today_cost / self.daily_budget
            
            if utilization >= 0.99:
                logger.critical(f"⚠️ Daily budget exceeded: ${today_cost:.2f} / ${self.daily_budget:.2f}")
            elif utilization >= 0.80:
                logger.warning(f"⚠️ Daily budget 80% used: ${today_cost:.2f} / ${self.daily_budget:.2f}")
            elif utilization >= 0.50:
                logger.info(f"Daily budget 50% used: ${today_cost:.2f} / ${self.daily_budget:.2f}")
    
    def get_summary(self) -> Dict:
        """Get cost summary for all agents"""
        
        total_cost = sum(m.total_cost for m in self.agent_metrics.values())
        total_calls = sum(m.total_calls for m in self.agent_metrics.values())
        
        return {
            "total_cost": f"${total_cost:.2f}",
            "total_calls": total_calls,
            "avg_cost_per_call": f"${total_cost/total_calls:.4f}" if total_calls > 0 else "$0",
            "by_agent": {
                agent_id: {
                    "cost": f"${m.total_cost:.2f}",
                    "calls": m.total_calls,
                    "successful": m.successful_calls,
                    "failed": m.failed_calls,
                    "cost_per_successful": f"${m.cost_per_successful_call:.4f}",
                }
                for agent_id, m in self.agent_metrics.items()
            }
        }
    
    def get_optimization_suggestions(self) -> List[str]:
        """Get suggestions to reduce costs"""
        
        suggestions = []
        
        # Find expensive models
        model_costs = {}
        for call in self.calls:
            model = call["model"]
            if model not in model_costs:
                model_costs[model] = 0
            model_costs[model] += call["cost"]
        
        # Suggest cheaper alternatives
        for model, cost in sorted(model_costs.items(), key=lambda x: x[1], reverse=True)[:3]:
            if "gpt-4" in model.lower():
                suggestions.append(f"Use gpt-4o-mini instead of {model}: could save 50%+")
            elif "opus" in model.lower():
                suggestions.append(f"Use claude-haiku for simple tasks instead of {model}: could save 95%+")
        
        # Suggest batch API for large workloads
        if sum(c["cost"] for c in self.calls) > 10:
            suggestions.append("Use batch API for non-time-sensitive tasks: saves 50% on tokens")
        
        # Suggest prompt caching
        total_input_tokens = sum(c["input_tokens"] for c in self.calls)
        if total_input_tokens > 100000:
            suggestions.append("Enable prompt caching: saves 90% on repeated context tokens")
        
        return suggestions