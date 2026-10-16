"""Block a retried payment write that already succeeded."""

from agentsre.idempotency import IdempotencyGuard

guard = IdempotencyGuard(window_seconds=300, max_repeats=1)

first = guard.check("post_payment", {"amount": 250.00, "dest": "acct-88"}, scope="txn-1001")
retry = guard.check("post_payment", {"dest": "acct-88", "amount": 250.00}, scope="txn-1001")

print(first)   # allowed=True
print(retry)   # allowed=False, reason=duplicate_within_window
print(f"DuplicateActionRate={guard.duplicate_action_rate:.0%}")
