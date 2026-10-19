"""
agentsre - SRE reliability for AI agents
Author: Ajay Devineni
License: MIT
"""

__version__ = "0.5.1"

from .metrics import AgentSLICollector, TaskRecord
from .cloudwatch import CloudWatchPublisher
from .validators import A2ASemanticValidator
from .circuit_breaker import AgentChainCircuitBreaker, CircuitState, CircuitStatus
from .cost_optimizer import CostTracker, CostMetrics, CostOptimizer
from .tool_evaluation import ToolEvaluationScore, QuestionScore
from .eval_pipeline import EvalPipeline, EvalRun, EvalCase
from .aos_reliability import (
    AuditCompletenessTracker,
    AOSCircuitBreaker,
    AuditRecord,
    GateFailureMode,
    CircuitState as AOSCircuitState,
)
from .automation_complacency import (
    ACRTracker,
    VerificationRecord,
    VerificationStatus,
    Severity,
)
from .idempotency import IdempotencyGuard, GuardDecision, action_key
