"""Tests for agentsre — run with: pytest tests/ -v"""

import time
import pytest
from agentsre import (
    AgentSLICollector,
    TaskRecord,
    A2ASemanticValidator,
    AgentChainCircuitBreaker,
    CircuitState,
)
from agentsre.metrics import DecisionQualityRate, _WindowStore, BaselineStore


# ── Fixtures ──────────────────────────────────────────────────

def make_task(
    task_class="payment-routing",
    tool_calls=3,
    escalated=False,
    pending=False,
    confidence=0.90,
    completed=True,
    task_id=None,
):
    return TaskRecord(
        task_id=task_id or f"t-{time.time_ns()}",
        task_class=task_class,
        tool_calls=tool_calls,
        required_escalation=escalated,
        pending_approval=pending,
        decision_confidence=confidence,
        completed=completed,
    )


# ── AgentSLICollector ─────────────────────────────────────────

class TestAgentSLICollector:

    def test_collect_returns_four_slis(self):
        c = AgentSLICollector()
        for _ in range(5):
            c.record(make_task())
        results = c.collect("payment-routing")
        assert len(results) == 4
        names = {r.name for r in results}
        assert "DecisionQualityRate" in names
        assert "ToolInvocationEfficiency" in names
        assert "HumanEscalationRate" in names
        assert "ApprovalQueueDepthDrift" in names

    def test_no_records_no_breach(self):
        c = AgentSLICollector()
        breaches = c.breached("payment-routing")
        assert breaches == []

    def test_her_breach_when_escalation_rate_high(self):
        c = AgentSLICollector()
        # Seed a low baseline first
        for _ in range(20):
            c.record(make_task(escalated=False))
        # Force high escalation
        for _ in range(10):
            c.record(make_task(escalated=True))
        results = c.collect("payment-routing")
        her = next(r for r in results if r.name == "HumanEscalationRate")
        assert her.value > 5.0  # above 5% default threshold
        assert her.breached

    def test_dqr_breach_on_low_confidence(self):
        c = AgentSLICollector()
        for _ in range(10):
            c.record(make_task(confidence=0.40))
        results = c.collect("payment-routing")
        dqr = next(r for r in results if r.name == "DecisionQualityRate")
        assert dqr.value < 85.0
        assert dqr.breached

    def test_tie_drift_detected(self):
        c = AgentSLICollector()
        # Establish baseline of 2 tool calls
        for _ in range(20):
            c.record(make_task(tool_calls=2))
        # Spike to 4 tool calls (2x baseline)
        for _ in range(10):
            c.record(make_task(tool_calls=4))
        results = c.collect("payment-routing")
        tie = next(r for r in results if r.name == "ToolInvocationEfficiency")
        assert tie.drift_ratio is not None
        assert tie.drift_ratio >= 1.5

    def test_collect_all_returns_all_task_classes(self):
        c = AgentSLICollector()
        c.record(make_task(task_class="payment-routing"))
        c.record(make_task(task_class="fraud-detection"))
        all_results = c.collect_all()
        assert "payment-routing" in all_results
        assert "fraud-detection" in all_results


# ── AQDD ──────────────────────────────────────────────────────

class TestApprovalQueueDepthDrift:

    def test_pending_tasks_counted(self):
        c = AgentSLICollector()
        for _ in range(3):
            c.record(make_task(pending=True, completed=False))
        results = c.collect("payment-routing")
        aqdd = next(r for r in results if r.name == "ApprovalQueueDepthDrift")
        assert aqdd.value == 3.0

    def test_completed_pending_not_counted(self):
        c = AgentSLICollector()
        # Approved and completed — should not count
        for _ in range(3):
            c.record(make_task(pending=True, completed=True))
        results = c.collect("payment-routing")
        aqdd = next(r for r in results if r.name == "ApprovalQueueDepthDrift")
        assert aqdd.value == 0.0


# ── A2ASemanticValidator ──────────────────────────────────────

class TestA2ASemanticValidator:

    def test_valid_result_passes(self):
        v = A2ASemanticValidator()
        v.register_schema("risk", {"required_fields": ["score", "confidence"]})
        result = v.validate(
            {"output": {"score": 7.2, "confidence": 0.88}},
            "risk-agent",
            "risk",
        )
        assert result.valid

    def test_missing_field_fails(self):
        v = A2ASemanticValidator()
        v.register_schema("risk", {"required_fields": ["score", "confidence"]})
        result = v.validate(
            {"output": {"score": 7.2}},   # confidence missing
            "risk-agent",
            "risk",
        )
        assert not result.valid
        assert result.failure_reason.value == "MISSING_REQUIRED_FIELDS"

    def test_empty_output_fails(self):
        v = A2ASemanticValidator()
        result = v.validate({}, "risk-agent", "risk")
        assert not result.valid
        assert result.failure_reason.value == "EMPTY_OUTPUT"

    def test_behavioral_drift_detected(self):
        v = A2ASemanticValidator(behavioral_threshold=0.75)
        result = v.validate(
            {"output": {"confidence": 0.30}},  # well below threshold
            "risk-agent",
            "risk",
        )
        assert not result.valid
        assert result.failure_reason.value == "BEHAVIORAL_DRIFT"

    def test_custom_validator_used(self):
        v = A2ASemanticValidator()
        v.register_custom_validator("special", lambda r: 0.20)  # always low
        result = v.validate({"output": {"x": 1}}, "agent", "special")
        assert not result.valid

    def test_semantic_validation_rate_calculated(self):
        v = A2ASemanticValidator()
        v.register_schema("task", {"required_fields": ["result"]})
        for _ in range(8):
            v.validate({"output": {"result": "ok", "confidence": 0.95}}, "agent", "task")
        for _ in range(2):
            v.validate({"output": {}}, "agent", "task")
        rate = v.semantic_validation_rate("agent", "task")
        assert rate is not None
        assert rate == 80.0


# ── AgentChainCircuitBreaker ──────────────────────────────────

class TestAgentChainCircuitBreaker:

    def test_starts_closed(self):
        cb = AgentChainCircuitBreaker()
        assert cb.allow_request("agent", "task")
        assert cb.status("agent", "task").state == CircuitState.CLOSED

    def test_opens_on_failures(self):
        cb = AgentChainCircuitBreaker(open_threshold=85.0, window_size=10)
        # 3 successes, 7 failures → 30% success rate
        for _ in range(3):
            cb.record_result("agent", "task", success=True)
        for _ in range(7):
            cb.record_result("agent", "task", success=False)
        assert cb.status("agent", "task").state == CircuitState.OPEN
        assert not cb.allow_request("agent", "task")

    def test_manual_reset(self):
        cb = AgentChainCircuitBreaker(open_threshold=85.0, window_size=10)
        for _ in range(10):
            cb.record_result("agent", "task", success=False)
        assert cb.status("agent", "task").state == CircuitState.OPEN
        cb.reset("agent", "task")
        assert cb.status("agent", "task").state == CircuitState.CLOSED
        assert cb.allow_request("agent", "task")

    def test_on_state_change_callback_fires(self):
        events = []
        cb = AgentChainCircuitBreaker(
            open_threshold=85.0,
            window_size=5,
            on_state_change=lambda s: events.append(s.state),
        )
        for _ in range(5):
            cb.record_result("agent", "task", success=False)
        assert CircuitState.OPEN in events

    def test_does_not_block_different_task_class(self):
        cb = AgentChainCircuitBreaker(open_threshold=85.0, window_size=5)
        for _ in range(5):
            cb.record_result("agent", "task-a", success=False)
        # task-b should be unaffected
        assert cb.allow_request("agent", "task-b")
