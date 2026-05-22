# agentsre/context_budget.py
"""
Context Budget Tracking — reliability SLI for agent working memory utilization.

The model's advertised token limit is not your operational limit.
Your operational limit is the token count at which DQR (Decision Quality Rate)
starts degrading for this agent on this task class. That number is always lower
than the advertised limit, and you find it in shadow mode — same protocol
as HER and RTD baselines.

CUR (Context Utilization Rate) = current_tokens / operational_ceiling
CUR > 0.75 → WARNING: compress
CUR >= 1.0 → CRITICAL: DQR actively degrading, escalate or end session

CUR is the earliest signal in context-driven failure:
CUR breach → DQR drop → RTD climb → HER spike

Author: Ajay Devineni
License: MIT
Repository: github.com/Ajay150313/agentsre
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional


CUR_WARNING_THRESHOLD = 0.75
CUR_CRITICAL_THRESHOLD = 1.0


@dataclass
class ContextBudgetTracker:
    """
    Track context window utilization against the operational DQR ceiling.

    Use one tracker per agent session. Update after each tool call
    or model response. Emit the status record to CloudWatch Logs.

    Attributes:
        agent_id: Agent identifier — must match ARO and Sprawl Registry
        task_class: Task type (operational ceiling varies by complexity)
        operational_ceiling_tokens: Token count where DQR degrades for
            this agent/task combination. Establish in shadow mode.
            NOT the model's advertised max tokens.
        session_id: Current session identifier
        warning_threshold_pct: CUR fraction triggering WARNING status
        critical_threshold_pct: CUR fraction triggering CRITICAL status
    """
    agent_id: str
    task_class: str
    operational_ceiling_tokens: int
    session_id: str = ""
    warning_threshold_pct: float = CUR_WARNING_THRESHOLD
    critical_threshold_pct: float = CUR_CRITICAL_THRESHOLD
    current_tokens: int = 0
    compression_events: int = 0
    peak_tokens: int = 0
    _history: List[Dict] = field(default_factory=list, repr=False)

    @property
    def cur(self) -> float:
        """
        Context Utilization Rate.
        Fraction of operational DQR ceiling currently consumed.
        > 0.75 = WARNING. >= 1.0 = CRITICAL (DQR degrading).
        """
        if self.operational_ceiling_tokens == 0:
            return 0.0
        return self.current_tokens / self.operational_ceiling_tokens

    @property
    def status(self) -> str:
        """OK / WARNING / CRITICAL based on CUR thresholds."""
        if self.cur >= self.critical_threshold_pct:
            return "CRITICAL"
        elif self.cur >= self.warning_threshold_pct:
            return "WARNING"
        return "OK"

    def update(self, current_tokens: int) -> Dict:
        """
        Update context utilization after each tool call or model turn.

        Args:
            current_tokens: Current total tokens in context window

        Returns:
            Status record for CloudWatch Logs emission.
        """
        self.current_tokens = current_tokens
        self.peak_tokens = max(self.peak_tokens, current_tokens)

        record = {
            "trace_type": "context_budget",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "task_class": self.task_class,
            "current_tokens": self.current_tokens,
            "operational_ceiling": self.operational_ceiling_tokens,
            "cur": round(self.cur, 3),
            "status": self.status,
            "compression_events": self.compression_events,
            "peak_tokens_this_session": self.peak_tokens,
        }
        self._history.append(record)
        return record

    def should_compress(self) -> bool:
        """
        True when approaching DQR degradation ceiling.
        Trigger context compression, summarization, or page-out.
        """
        return self.cur >= self.warning_threshold_pct

    def should_escalate(self) -> bool:
        """
        True when at or above operational ceiling.
        DQR is actively degrading. Escalate to human or end session.
        Do not continue with full context — accuracy is compromised.
        """
        return self.cur >= self.critical_threshold_pct

    def record_compression(self,
                           tokens_before: int,
                           tokens_after: int) -> Dict:
        """
        Record a context compression or summarization event.

        Args:
            tokens_before: Token count before compression
            tokens_after: Token count after compression

        Returns:
            Compression event record for audit log.
        """
        self.compression_events += 1
        self.current_tokens = tokens_after
        return {
            "event": "context_compression",
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "compression_event_number": self.compression_events,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "tokens_saved": tokens_before - tokens_after,
            "cur_after": round(self.cur, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def session_summary(self) -> Dict:
        """
        End-of-session summary for postmortem and baseline calibration.
        Use this data to refine your operational ceiling estimate over time.
        """
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "task_class": self.task_class,
            "operational_ceiling": self.operational_ceiling_tokens,
            "peak_tokens": self.peak_tokens,
            "peak_cur": round(self.peak_tokens / self.operational_ceiling_tokens, 3),
            "compression_events": self.compression_events,
            "status_at_end": self.status,
            "total_updates": len(self._history),
        }