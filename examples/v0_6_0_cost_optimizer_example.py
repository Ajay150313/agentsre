"""
Example: Cost Optimizer with agentsre

Shows how to track agent costs in real-time and get optimization suggestions.

Author: Ajay Devineni
License: MIT
"""

from agentsre.cost_optimizer import CostTracker, CostOptimizer
import json


def demo_cost_tracking():
    """Demonstrate cost tracking"""
    
    print("=" * 80)
    print("AGENTSRE v0.5.0 - COST OPTIMIZER DEMO")
    print("=" * 80)
    
    # Initialize tracker
    tracker = CostTracker()
    tracker.set_daily_budget(50)
    tracker.set_monthly_budget(1000)
    
    # Simulate agent calls
    print("\n" + "=" * 80)
    print("SCENARIO 1: Payment Processing Agent")
    print("=" * 80)
    
    # 10 calls with claude-opus
    for i in range(10):
        cost = tracker.track_api_call(
            agent_id="payment-router",
            model="claude-opus",
            input_tokens=1000,
            output_tokens=500,
            success=(i < 9),  # 1 failure
            operation="route_transaction"
        )
        print(f"  Call {i+1}: ${cost:.4f}")
    
    # Get metrics
    metrics = tracker.get_metrics("payment-router")
    print(f"\n✅ Payment Router Metrics:")
    print(f"   Total cost: ${metrics.total_cost:.2f}")
    print(f"   Total calls: {metrics.total_calls}")
    print(f"   Successful: {metrics.successful_calls}")
    print(f"   Failed: {metrics.failed_calls}")
    print(f"   Cost per successful call: ${metrics.cost_per_successful_call:.4f}")
    
    # Scenario 2: Classification agent
    print("\n" + "=" * 80)
    print("SCENARIO 2: Classification Agent")
    print("=" * 80)
    
    # Mix of expensive (opus) and cheap (haiku) calls
    for i in range(5):
        cost = tracker.track_api_call(
            agent_id="classifier",
            model="claude-opus",
            input_tokens=2000,
            output_tokens=100,
            operation="complex_analysis"
        )
        print(f"  Opus call {i+1}: ${cost:.4f}")
    
    for i in range(15):
        cost = tracker.track_api_call(
            agent_id="classifier",
            model="claude-haiku",
            input_tokens=500,
            output_tokens=50,
            operation="simple_check"
        )
        print(f"  Haiku call {i+1}: ${cost:.6f}")
    
    # Cost summary
    print("\n" + "=" * 80)
    print("COST SUMMARY")
    print("=" * 80)
    
    summary = tracker.get_summary()
    print(json.dumps(summary, indent=2))
    
    # Optimization suggestions
    print("\n" + "=" * 80)
    print("OPTIMIZATION SUGGESTIONS")
    print("=" * 80)
    
    optimizer = CostOptimizer(tracker)
    suggestions = optimizer.analyze()
    
    for i, suggestion in enumerate(suggestions[:5], 1):
        print(f"\n{i}. {suggestion.title}")
        print(f"   Type: {suggestion.type.value}")
        print(f"   Description: {suggestion.description}")
        print(f"   Estimated savings: {suggestion.estimated_savings}")
        print(f"   Implementation effort: {suggestion.implementation_effort}")
        print(f"   Current: ${suggestion.current_cost:.2f} → Projected: ${suggestion.projected_cost:.2f}")
    
    # What we learned
    print("\n" + "=" * 80)
    print("KEY INSIGHT")
    print("=" * 80)
    
    total_cost = summary["total_cost"].replace("$", "").replace(",", "")
    print(f"""
The classifier agent spent ${total_cost} for:
- 5 complex queries with Claude Opus (expensive)
- 15 simple queries with Claude Haiku (cheap)

By routing simple queries to Haiku instead of Opus:
- Keep 5 Opus calls: ~${5 * 0.0225:.2f} (complex work)
- Switch 15 calls to Haiku: ~${15 * 0.0008:.4f} (simple work)
- Savings: ~70% on classification costs

This is model routing in action.
""")


if __name__ == "__main__":
    demo_cost_tracking()
