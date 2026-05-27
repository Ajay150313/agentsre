"""
SLI metrics collection for AI agents.

Implements Decision Quality Rate (DQR), Tool Invocation Efficiency (TIE),
Human Escalation Rate (HER), and Approval Queue Depth Drift (AQDD).

Author: Ajay Devineni
License: MIT
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class TaskRecord:
    """Record of a single agent task execution."""
    
    task_id: str
    task_class: str
    tool_calls: int
    required_escalation: bool
    pending_approval: bool
    decision_confidence: float
    completed: bool
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate task record."""
        if not 0 <= self.decision_confidence <= 1:
            raise ValueError("decision_confidence must be between 0 and 1")
        
        if self.timestamp is None:
            self.timestamp = datetime.now()


class AgentSLICollector:
    """Collect and analyze agent SLI metrics."""
    
    def __init__(self):
        """Initialize the collector."""
        self.tasks: Dict[str, List[TaskRecord]] = {}
        self.baselines: Dict[str, Dict[str, float]] = {}
    
    def record(self, task: TaskRecord) -> None:
        """
        Record a task execution.
        
        Args:
            task: TaskRecord with execution details
        """
        if task.task_class not in self.tasks:
            self.tasks[task.task_class] = []
        
        self.tasks[task.task_class].append(task)
        logger.info(f"Recorded task {task.task_id} for {task.task_class}")
    
    def collect(self, task_class: str) -> List[Dict]:
        """
        Calculate SLIs for a task class.
        
        Args:
            task_class: The task class to analyze
            
        Returns:
            List of SLI results
        """
        if task_class not in self.tasks:
            return []
        
        tasks = self.tasks[task_class]
        
        # Calculate DQR (Decision Quality Rate)
        dqr = sum(1 for t in tasks if t.decision_confidence > 0.8) / len(tasks) * 100
        
        # Calculate TIE (Tool Invocation Efficiency)
        avg_calls = sum(t.tool_calls for t in tasks) / len(tasks)
        tie = avg_calls / 2.0  # Normalized to 2 as baseline
        
        # Calculate HER (Human Escalation Rate)
        her = sum(1 for t in tasks if t.required_escalation) / len(tasks) * 100
        
        # Calculate AQDD (Approval Queue Depth Drift)
        pending = sum(1 for t in tasks if t.pending_approval)
        
        return [
            {"metric": "DQR", "value": dqr, "status": "healthy" if dqr > 85 else "warning"},
            {"metric": "TIE", "value": tie, "status": "healthy" if tie < 1.5 else "warning"},
            {"metric": "HER", "value": her, "status": "healthy" if her < 5 else "warning"},
            {"metric": "AQDD", "value": pending, "status": "healthy" if pending < 20 else "warning"},
        ]
    
    def breached(self, task_class: str) -> bool:
        """
        Check if any SLI has breached threshold.
        
        Args:
            task_class: The task class to check
            
        Returns:
            True if any SLI has breached
        """
        results = self.collect(task_class)
        return any(r["status"] == "warning" for r in results)
