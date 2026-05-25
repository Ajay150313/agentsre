"""
Cost optimization recommendations engine

Author: Ajay Devineni
License: MIT
"""

from dataclasses import dataclass
from typing import List, Dict
from enum import Enum


class OptimizationType(Enum):
    MODEL_ROUTING = "model_routing"
    BATCH_API = "batch_api"
    CACHING = "caching"
    CONTEXT_PRUNING = "context_pruning"
    MONITORING = "monitoring"


@dataclass
class OptimizationSuggestion:
    """Optimization recommendation"""
    type: OptimizationType
    title: str
    description: str
    estimated_savings: str  # "50%" or "$500/month"
    implementation_effort: str  # "easy", "medium", "hard"
    current_cost: float
    projected_cost: float


class CostOptimizer:
    """Generate optimization suggestions based on usage patterns"""
    
    def __init__(self, tracker):
        self.tracker = tracker
    
    def analyze(self) -> List[OptimizationSuggestion]:
        """Analyze costs and return suggestions"""
        
        suggestions = []
        
        # 1. Model routing
        suggestions.extend(self._suggest_model_routing())
        
        # 2. Batch API
        suggestions.extend(self._suggest_batch_api())
        
        # 3. Caching
        suggestions.extend(self._suggest_caching())
        
        # Sort by savings
        suggestions.sort(
            key=lambda x: float(x.estimated_savings.replace("%", "").replace("$", "").split("/")[0]),
            reverse=True
        )
        
        return suggestions
    
    def _suggest_model_routing(self) -> List[OptimizationSuggestion]:
        """Suggest cheaper models for simple tasks"""
        
        suggestions = []
        model_costs = {}
        
        for call in self.tracker.calls:
            model = call["model"]
            if model not in model_costs:
                model_costs[model] = 0
            model_costs[model] += call["cost"]
        
        # Find expensive models
        for model, cost in sorted(model_costs.items(), key=lambda x: x[1], reverse=True)[:2]:
            if "gpt-4" in model.lower() and cost > 5:
                projected = cost * 0.3  # 70% savings
                suggestions.append(OptimizationSuggestion(
                    type=OptimizationType.MODEL_ROUTING,
                    title=f"Switch from {model} to cheaper alternative",
                    description=f"Use gpt-4o or gpt-4o-mini for 70% cost reduction",
                    estimated_savings=f"${cost - projected:.2f}/month",
                    implementation_effort="easy",
                    current_cost=cost,
                    projected_cost=projected
                ))
            elif "opus" in model.lower() and cost > 5:
                projected = cost * 0.05  # 95% savings with haiku
                suggestions.append(OptimizationSuggestion(
                    type=OptimizationType.MODEL_ROUTING,
                    title=f"Classify tasks for {model}",
                    description="Use Claude Haiku for simple tasks (95% cheaper)",
                    estimated_savings=f"${cost - projected:.2f}/month",
                    implementation_effort="medium",
                    current_cost=cost,
                    projected_cost=projected
                ))
        
        return suggestions
    
    def _suggest_batch_api(self) -> List[OptimizationSuggestion]:
        """Suggest batch API for non-time-sensitive work"""
        
        suggestions = []
        
        total_cost = sum(m.total_cost for m in self.tracker.agent_metrics.values())
        
        if total_cost > 10:
            projected_savings = total_cost * 0.5  # 50% with batch API
            suggestions.append(OptimizationSuggestion(
                type=OptimizationType.BATCH_API,
                title="Use Batch API for background tasks",
                description="Send non-urgent requests via batch API (50% discount)",
                estimated_savings=f"${projected_savings:.2f}/month",
                implementation_effort="easy",
                current_cost=total_cost,
                projected_cost=total_cost - projected_savings
            ))
        
        return suggestions
    
    def _suggest_caching(self) -> List[OptimizationSuggestion]:
        """Suggest prompt caching for repeated contexts"""
        
        suggestions = []
        
        total_input_tokens = sum(c["input_tokens"] for c in self.tracker.calls)
        
        if total_input_tokens > 100000:
            projected_savings = total_input_tokens * 0.0008 * 0.9  # 90% savings on cached
            suggestions.append(OptimizationSuggestion(
                type=OptimizationType.CACHING,
                title="Enable prompt caching",
                description="Cache system prompts and repeated context (90% savings on cached)",
                estimated_savings="30-50% on context",
                implementation_effort="medium",
                current_cost=0,
                projected_cost=0
            ))
        
        return suggestions
