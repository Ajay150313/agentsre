"""
Cost Optimizer Example - v0.5.0

Author: Ajay Devineni
License: MIT
"""

from agentsre.cost_optimizer import CostTracker, CostOptimizer


def main():
    print("=" * 80)
    print("AGENTSRE v0.5.0 - COST OPTIMIZER EXAMPLE")
    print("=" * 80)
    
    # Initialize tracker
    tracker = CostTracker()
    
    # Simulate some calls
    print("\nTracking API calls...")
    
    for i in range(5):
        cost = tracker.track_api_call(
            agent_id="payment-router",
            model="claude-opus",
            input_tokens=1000,
            output_tokens=500,
            success=True,
            operation="route_transaction"
        )
        print(f"  Call {i+1}: ${cost:.4f}")
    
    # Get metrics
    metrics = tracker.get_metrics("payment-router")
    print(f"\nMetrics:")
    print(f"  Total cost: ${metrics.total_cost:.2f}")
    print(f"  Total calls: {metrics.total_calls}")
    print(f"  Cost per call: ${metrics.cost_per_call():.4f}")
    print(f"  Successful calls: {metrics.successful_calls}")
    
    # Get summary
    summary = tracker.get_summary()
    print(f"\nSummary:")
    print(f"  Total cost: ${summary['total_cost']:.2f}")
    print(f"  Total calls: {summary['total_calls']}")
    
    # Get suggestions
    optimizer = CostOptimizer(tracker)
    suggestions = optimizer.analyze()
    
    print(f"\nOptimization Suggestions:")
    for suggestion in suggestions:
        print(f"  • {suggestion.title}")
        print(f"    Savings: {suggestion.estimated_savings}")
        print(f"    Effort: {suggestion.effort}")
    
    print("\n✅ Example completed successfully!")


if __name__ == "__main__":
    main()
