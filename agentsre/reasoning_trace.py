# agentsre/reasoning_trace.py
"""
Reasoning Trace Depth (RTD) — Layer 3 observability for autonomous agents.

Traditional OTel traces instrument infrastructure execution.
This module instruments reasoning behavior — re-planning cycles,
decision sequences, and the earliest signal of silent agent degradation.

Emit one AgentDecisionTrace per task (not per tool call).
RTD = number of re-planning cycles before completion or escalation.

Author: Ajay Devineni
License: MIT
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Literal


DecisionType = Literal["CONTINUE", "REPLAN", "COMPLETE", "ESCALATE"]

RTD_NORMAL_MAX = 1
RTD_WARNING_THRESHOLD = 3
RTD_CRITICAL_THRESHOLD = 5


@dataclass
class ReplanEvent:
    """
    A single re-planning event within an agent task execution.

    Attributes:
        reason: Why the agent decided to re-plan
        tool_that_failed: Which tool or data source triggered re-planning
        new_plan: What the agent decided to try instead
    """
    reason: str
    tool_that_failed: Optional[str] = None
    new_plan: Optional[str] = None


@dataclass
class AgentDecisionTrace:
    """
    Structured reasoning trace for a single agent task execution.

    Emitted ONCE per task — not once per tool call.
    This is your Layer 3 (reasoning) observability record.

    RTD = len(replan_events)
    RTD > RTD_WARNING_THRESHOLD → agent encountering unexpected state
    RTD > RTD_CRITICAL_THRESHOLD → agent in re-planning loop

    Attributes:
        agent_id: Identifier of the agent being traced
        task_id: Unique identifier for this task execution
        session_id: Session grouping multiple related tasks
        initial_plan: The agent's first-pass plan for the task
        tools_called: Ordered list of tools invoked during execution
        replan_events: List of re-planning events (RTD = len of this)
        final_decision: How the task resolved
        human_escalated: Whether this task resulted in a HER event
        total_tool_calls: Total tool invocations including re-planned calls
        latency_ms: Total task execution time in milliseconds
        confidence_proxy: Optional output quality signal (0.0–1.0)
    """
    agent_id: str
    task_id: str
    session_id: str
    initial_plan: str
    tools_called: List[str] = field(default_factory=list)
    replan_events: List[ReplanEvent] = field(default_factory=list)
    final_decision: DecisionType = "COMPLETE"
    human_escalated: bool = False
    total_tool_calls: int = 0
    latency_ms: int = 0
    confidence_proxy: Optional[float] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def rtd(self) -> int:
        """
        Reasoning Trace Depth — number of re-planning cycles.
        Core Layer 3 SLI. RTD > 3 is warning, > 5 is critical.
        """
        return len(self.replan_events)

    @property
    def rtd_status(self) -> str:
        """Categorize current RTD against production thresholds."""
        if self.rtd <= RTD_NORMAL_MAX:
            return "OK"
        elif self.rtd <= RTD_WARNING_THRESHOLD:
            return "WARNING"
        return "CRITICAL"

    def add_replan(self, reason: str,
                   tool_that_failed: Optional[str] = None,
                   new_plan: Optional[str] = None) -> None:
        """
        Record a re-planning event during task execution.
        Call this each time the agent decides to re-plan mid-task.

        Args:
            reason: Why the re-plan was triggered
            tool_that_failed: Tool or data source that caused it
            new_plan: What the agent plans to try next
        """
        self.replan_events.append(ReplanEvent(
            reason=reason,
            tool_that_failed=tool_that_failed,
            new_plan=new_plan
        ))

    def to_structured_log(self) -> dict:
        """
        Serialize to structured log format for CloudWatch Logs / Datadog.
        Index on agent_id + rtd_status for alert queries.
        """
        record = {
            "trace_type": "agent_decision_trace",
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "reasoning": {
                "initial_plan": self.initial_plan,
                "rtd": self.rtd,
                "rtd_status": self.rtd_status,
                "replan_events": [
                    {
                        "reason": e.reason,
                        "tool_that_failed": e.tool_that_failed,
                        "new_plan": e.new_plan
                    }
                    for e in self.replan_events
                ],
                "tools_sequence": self.tools_called,
            },
            "outcome": {
                "final_decision": self.final_decision,
                "human_escalated": self.human_escalated,
            },
            "cost": {
                "total_tool_calls": self.total_tool_calls,
                "latency_ms": self.latency_ms,
            }
        }
        if self.confidence_proxy is not None:
            record["quality"] = {"confidence_proxy": self.confidence_proxy}
        return record

    def to_json(self) -> str:
        """Serialize to JSON string for log emission."""
        return json.dumps(self.to_structured_log())