"""
Cost optimization recommendations

Author: Ajay Devineni
License: MIT
"""


class OptimizationSuggestion:
    """Cost optimization suggestion"""
    
    def __init__(
        self,
        title: str,
        description: str,
        estimated_savings: str,
        effort: str
    ):
        self.title = title
        self.description = description
        self.estimated_savings = estimated_savings
        self.effort = effort
    
    def __repr__(self):
        return f"OptimizationSuggestion('{self.title}', {self.estimated_savings})"


class CostOptimizer:
    """Generate optimization suggestions"""
    
    def __init__(self, tracker):
        self.tracker = tracker
    
    def analyze(self) -> list:
        """Analyze and return suggestions"""
        
        suggestions = []
        
        # Get total cost
        total_cost = sum(m.total_cost for m in self.tracker.agent_metrics.values())
        
        if total_cost > 10:
            suggestions.append(OptimizationSuggestion(
                title="Use Batch API for background tasks",
                description="50% discount on non-urgent requests",
                estimated_savings=f"${total_cost * 0.5:.2f}/month",
                effort="Easy"
            ))
        
        # Check for expensive models
        all_models = {}
        for call in self.tracker.calls:
            model = call["model"]
            cost = call["cost"]
            if model not in all_models:
                all_models[model] = 0.0
            all_models[model] += cost
        
        for model, cost in sorted(all_models.items(), key=lambda x: x[1], reverse=True)[:2]:
            if "gpt-4" in model.lower() and cost > 5:
                suggestions.append(OptimizationSuggestion(
                    title=f"Switch from {model} to gpt-4o",
                    description="70% cheaper for most tasks",
                    estimated_savings=f"${cost * 0.7:.2f}/month",
                    effort="Medium"
                ))
        
        return suggestions
