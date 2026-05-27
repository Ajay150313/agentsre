"""Tests for metrics module."""

import pytest
from agentsre.metrics import AgentSLICollector, TaskRecord


def test_task_record_creation():
    """Test creating a task record."""
    task = TaskRecord(
        task_id="t-001",
        task_class="payment",
        tool_calls=2,
        required_escalation=False,
        pending_approval=False,
        decision_confidence=0.95,
        completed=True,
    )
    assert task.task_id == "t-001"
    assert task.decision_confidence == 0.95


def test_task_record_invalid_confidence():
    """Test invalid confidence value."""
    with pytest.raises(ValueError):
        TaskRecord(
            task_id="t-001",
            task_class="payment",
            tool_calls=2,
            required_escalation=False,
            pending_approval=False,
            decision_confidence=1.5,  # Invalid
            completed=True,
        )


def test_collector_record():
    """Test recording tasks."""
    collector = AgentSLICollector()
    
    task = TaskRecord(
        task_id="t-001",
        task_class="payment",
        tool_calls=2,
        required_escalation=False,
        pending_approval=False,
        decision_confidence=0.95,
        completed=True,
    )
    
    collector.record(task)
    assert "payment" in collector.tasks
    assert len(collector.tasks["payment"]) == 1


def test_collector_metrics():
    """Test calculating SLI metrics."""
    collector = AgentSLICollector()
    
    for i in range(5):
        task = TaskRecord(
            task_id=f"t-{i:03d}",
            task_class="payment",
            tool_calls=2,
            required_escalation=False,
            pending_approval=False,
            decision_confidence=0.90,
            completed=True,
        )
        collector.record(task)
    
    results = collector.collect("payment")
    assert len(results) == 4  # DQR, TIE, HER, AQDD
    assert results[0]["metric"] == "DQR"


def test_collector_breached():
    """Test breach detection."""
    collector = AgentSLICollector()
    
    # Add healthy tasks
    for i in range(5):
        task = TaskRecord(
            task_id=f"t-{i:03d}",
            task_class="payment",
            tool_calls=2,
            required_escalation=False,
            pending_approval=False,
            decision_confidence=0.90,
            completed=True,
        )
        collector.record(task)
    
    assert not collector.breached("payment")
