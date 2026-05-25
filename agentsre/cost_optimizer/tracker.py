"""
Cost tracking for AI agents

Author: Ajay Devineni
License: MIT
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class CostMetrics:
    """Cost metrics for an agent"""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.total_cost = 0.0
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.by_model = {}
        self.by_operation = {}
    
    def add_call(self, cost: float, model: str, operation: str = "default", success: bool = True):
        """Record a cost"""
        self.total_cost += cost
        self.total_calls += 1
        
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
        
        if model not in self.by_model:
            self.by_model[model] = 0.0
        self.by_model[model] += cost
        
        if operation not in self.by_operation:
            self.by_operation[operation] = 0.0
        self.by_operation[operation] += cost
    
    def cost_per_call(self) -> float:
        """Average cost per call"""
        if self.total_calls == 0:
            return 0.0
        return self.total_cost / self.total_calls
    
    def cost_per_successful_call(self) -> float:
        """Average cost per successful call"""
        if self.successful_calls == 0:
            return 0.0
        return self.total_cost / self.successful_calls


class CostTracker:
    """Track costs for AI agents"""
    
    # Pricing for major models (May 2026)
    PRICING = {
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "claude-opus": {"input": 0.015, "output": 0.075},
        "claude-sonnet": {"input": 0.003, "output": 0.015},
        "claude-haiku": {"input": 0.00080, "output": 0.0024},
    }
    
    def __init__(self):
        self.calls: List[Dict] = []
        self.agent_metrics: Dict[str, CostMetrics] = {}
        self.daily_budget: Optional[float] = None
        self.monthly_budget: Optional[float] = None
    
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
        """Track an API call and return cost"""
        
        # Calculate cost
        cost = self._calculate_cost(model, input_tokens, output_tokens, cached_tokens)
        
        # Record
        call_record = {
            "agent_id": agent_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "success": success,
            "operation": operation,
            "timestamp": datetime.now().isoformat()
        }
        self.calls.append(call_record)
        
        # Update metrics
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = CostMetrics(agent_id)
        
        self.agent_metrics[agent_id].add_call(cost, model, operation, success)
        
        logger.info(f"Tracked {agent_id}: {model} - ${cost:.4f}")
        return cost
    
    def _calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0
    ) -> float:
        """Calculate cost for API call"""
        
        if model not in self.PRICING:
            logger.warning(f"Unknown model {model}")
            return 0.0
        
        pricing = self.PRICING[model]
        
        # Basic calculation
        input_cost = (input_tokens * pricing["input"]) / 1_000_000
        output_cost = (output_tokens * pricing["output"]) / 1_000_000
        
        return input_cost + output_cost
    
    def get_metrics(self, agent_id: str) -> Optional[CostMetrics]:
        """Get metrics for agent"""
        return self.agent_metrics.get(agent_id)
    
    def get_all_metrics(self) -> Dict[str, CostMetrics]:
        """Get all metrics"""
        return self.agent_metrics
    
    def set_daily_budget(self, amount: float):
        """Set daily budget"""
        self.daily_budget = amount
    
    def set_monthly_budget(self, amount: float):
        """Set monthly budget"""
        self.monthly_budget = amount
    
    def get_summary(self) -> Dict:
        """Get cost summary"""
        total_cost = sum(m.total_cost for m in self.agent_metrics.values())
        total_calls = sum(m.total_calls for m in self.agent_metrics.values())
        
        return {
            "total_cost": total_cost,
            "total_calls": total_calls,
            "by_agent": {
                agent_id: {
                    "cost": m.total_cost,
                    "calls": m.total_calls,
                    "cost_per_call": m.cost_per_call(),
                }
                for agent_id, m in self.agent_metrics.items()
            }
        }
