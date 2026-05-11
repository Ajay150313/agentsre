#Hard token budget enforcement for production AI agent sessions.

#The retry loop failure mode: Agent calls a failing tool → gets ambiguous response → retries  → no limit → cost spike → first signal is the AWS bill. This module enforces a hard ceiling at the infrastructure layer. When the budget is exhausted, the agent routes to escalation — it does not loop and bill.
#Author: Ajay Devineni 

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class BudgetStatus(str, Enum):
    WITHIN_BUDGET = "WITHIN_BUDGET"
    WARNING = "WARNING"            # > 70% consumed
    CRITICAL = "CRITICAL"          # > 90% consumed
    EXHAUSTED = "EXHAUSTED"        # 100% — stop and escalate


@dataclass
class BudgetSnapshot:
    session_id: str
    tokens_used: int
    tokens_budget: int
    tool_calls: int
    status: BudgetStatus
    pct_consumed: float
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        bar = "█" * int(self.pct_consumed / 10) + "░" * (10 - int(self.pct_consumed / 10))
        return (
            f"[Budget {self.session_id}] [{bar}] "
            f"{self.tokens_used}/{self.tokens_budget} tokens "
            f"({self.pct_consumed:.0f}%) — {self.status.value}"
        )


class TokenBudgetEnforcer:
    """
    Hard token budget enforcement per agent session.

    Not a prompt instruction. A hard infrastructure ceiling.
    When budget is exhausted, the agent stops and routes to escalation.

    Usage::

        from agentsre.budgets import TokenBudgetEnforcer, BudgetStatus

        enforcer = TokenBudgetEnforcer(
            session_id="incident-2026-05-05-001",
            token_budget=6000,          # 3x your P95 task token usage
            tool_call_limit=15,         # hard cap on tool calls per session
            on_exhausted=lambda s: page_oncall(s),
        )

        # Before each model call:
        status = enforcer.consume(tokens=450, tool_calls=1)
        if status == BudgetStatus.EXHAUSTED:
            return route_to_escalation()

        # Check anytime:
        snapshot = enforcer.snapshot()
        print(snapshot)
    """

    def __init__(
        self,
        session_id: str,
        token_budget: int,
        tool_call_limit: int = 20,
        warning_threshold: float = 0.70,
        critical_threshold: float = 0.90,
        on_warning: Optional[Callable[[BudgetSnapshot], None]] = None,
        on_exhausted: Optional[Callable[[BudgetSnapshot], None]] = None,
    ):
        self.session_id = session_id
        self.token_budget = token_budget
        self.tool_call_limit = tool_call_limit
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.on_warning = on_warning
        self.on_exhausted = on_exhausted

        self._tokens_used: int = 0
        self._tool_calls: int = 0
        self._exhausted: bool = False
        self._warning_fired: bool = False

    def consume(self, tokens: int, tool_calls: int = 0) -> BudgetStatus:
        """
        Record token and tool call consumption.
        Returns current BudgetStatus — check before continuing agent execution.
        """
        if self._exhausted:
            return BudgetStatus.EXHAUSTED

        self._tokens_used += tokens
        self._tool_calls += tool_calls

        pct = self._tokens_used / self.token_budget
        tool_exhausted = self._tool_calls >= self.tool_call_limit

        if pct >= 1.0 or tool_exhausted:
            self._exhausted = True
            snap = self.snapshot()
            if self.on_exhausted:
                try:
                    self.on_exhausted(snap)
                except Exception:
                    pass
            return BudgetStatus.EXHAUSTED

        if pct >= self.critical_threshold:
            return BudgetStatus.CRITICAL

        if pct >= self.warning_threshold:
            if not self._warning_fired:
                self._warning_fired = True
                if self.on_warning:
                    try:
                        self.on_warning(self.snapshot())
                    except Exception:
                        pass
            return BudgetStatus.WARNING

        return BudgetStatus.WITHIN_BUDGET

    def snapshot(self) -> BudgetSnapshot:
        pct = min((self._tokens_used / self.token_budget) * 100, 100.0)
        if self._exhausted:
            status = BudgetStatus.EXHAUSTED
        elif pct >= self.critical_threshold * 100:
            status = BudgetStatus.CRITICAL
        elif pct >= self.warning_threshold * 100:
            status = BudgetStatus.WARNING
        else:
            status = BudgetStatus.WITHIN_BUDGET
        return BudgetSnapshot(
            session_id=self.session_id,
            tokens_used=self._tokens_used,
            tokens_budget=self.token_budget,
            tool_calls=self._tool_calls,
            status=status,
            pct_consumed=round(pct, 1),
        )

    def remaining(self) -> int:
        return max(0, self.token_budget - self._tokens_used)

    def is_exhausted(self) -> bool:
        return self._exhausted

    def reset(self) -> None:
        """Reset for a new session. Does not change budget limits."""
        self._tokens_used = 0
        self._tool_calls = 0
        self._exhausted = False
        self._warning_fired = False