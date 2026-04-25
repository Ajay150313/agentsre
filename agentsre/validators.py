"""
agentsre.validators
~~~~~~~~~~~~~~~~~~~
A2A Semantic Boundary Validator

Validates incoming A2A task results BEFORE the orchestrator acts on them.
Catches the failure mode CloudWatch misses:
  HTTP 200, syntactically valid — but semantically wrong output.

Three validation layers (applied in order):
  1. Schema    — does the result match expected structure?
  2. Completeness — are all required fields populated?
  3. Behavioral bounds — does the result match the sub-agent's baseline?
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ValidationFailureReason(str, Enum):
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    BEHAVIORAL_DRIFT = "BEHAVIORAL_DRIFT"
    EMPTY_OUTPUT = "EMPTY_OUTPUT"


@dataclass
class ValidationResult:
    valid: bool
    confidence: float          # 0.0 – 1.0
    sub_agent_id: str
    task_class: str
    failure_reason: Optional[ValidationFailureReason] = None
    details: str = ""
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        status = "✓ VALID" if self.valid else f"✗ INVALID ({self.failure_reason})"
        return (
            f"[A2A Validation] {self.sub_agent_id}/{self.task_class}: "
            f"{status}  confidence={self.confidence:.2f}  {self.details}"
        )


class A2ASemanticValidator:
    """
    Validates A2A task results at the orchestrator's ingestion boundary.

    Usage::

        validator = A2ASemanticValidator()

        # Define expected schema per task class
        validator.register_schema("risk-assessment", {
            "required_fields": ["risk_score", "confidence", "factors"],
            "field_types": {"risk_score": (int, float), "confidence": float},
        })

        # Validate incoming result
        result = validator.validate(
            task_result={"risk_score": 7.2, "confidence": 0.88, "factors": [...]},
            sub_agent_id="risk-agent-v2",
            task_class="risk-assessment",
        )
        if not result.valid:
            # Route to escalation — do NOT pass to orchestrator
            escalate(result)
    """

    def __init__(self, behavioral_threshold: float = 0.75):
        self.behavioral_threshold = behavioral_threshold
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._baselines: Dict[str, List[float]] = {}   # sub_agent_id:task_class → [confidence scores]
        self._custom_validators: Dict[str, Callable[[Any], float]] = {}

    # ── Registration ──────────────────────────────────────────

    def register_schema(self, task_class: str, schema: Dict[str, Any]) -> None:
        """
        Register expected schema for a task class.

        schema keys:
          required_fields  List[str]            — must be present in result["output"]
          field_types      Dict[str, type|tuple] — optional type checks
        """
        self._schemas[task_class] = schema

    def register_custom_validator(
        self,
        task_class: str,
        fn: Callable[[Any], float],
    ) -> None:
        """
        Register a custom behavioral validator for a task class.
        `fn` receives the raw task result dict and returns confidence 0.0–1.0.
        """
        self._custom_validators[task_class] = fn

    # ── Validation pipeline ───────────────────────────────────

    def validate(
        self,
        task_result: Dict[str, Any],
        sub_agent_id: str,
        task_class: str,
    ) -> ValidationResult:
        """Run all three validation layers and return a ValidationResult."""

        # Layer 1: empty output guard
        if not task_result or not task_result.get("output"):
            return ValidationResult(
                valid=False,
                confidence=0.0,
                sub_agent_id=sub_agent_id,
                task_class=task_class,
                failure_reason=ValidationFailureReason.EMPTY_OUTPUT,
                details="task_result or task_result['output'] is empty",
            )

        output = task_result["output"]

        # Layer 2: schema validation
        schema = self._schemas.get(task_class)
        if schema:
            missing = [
                f for f in schema.get("required_fields", [])
                if f not in output
            ]
            if missing:
                return ValidationResult(
                    valid=False,
                    confidence=0.0,
                    sub_agent_id=sub_agent_id,
                    task_class=task_class,
                    failure_reason=ValidationFailureReason.MISSING_REQUIRED_FIELDS,
                    details=f"missing fields: {missing}",
                )

            type_errors = []
            for fld, expected_type in schema.get("field_types", {}).items():
                if fld in output and not isinstance(output[fld], expected_type):
                    type_errors.append(
                        f"{fld}: expected {expected_type}, got {type(output[fld])}"
                    )
            if type_errors:
                return ValidationResult(
                    valid=False,
                    confidence=0.0,
                    sub_agent_id=sub_agent_id,
                    task_class=task_class,
                    failure_reason=ValidationFailureReason.SCHEMA_MISMATCH,
                    details=f"type errors: {type_errors}",
                )

        # Layer 3: behavioral bound check
        confidence = self._behavioral_confidence(
            task_result, sub_agent_id, task_class
        )
        key = f"{sub_agent_id}:{task_class}"
        self._baselines.setdefault(key, []).append(confidence)

        if confidence < self.behavioral_threshold:
            return ValidationResult(
                valid=False,
                confidence=confidence,
                sub_agent_id=sub_agent_id,
                task_class=task_class,
                failure_reason=ValidationFailureReason.BEHAVIORAL_DRIFT,
                details=(
                    f"confidence {confidence:.2f} below threshold "
                    f"{self.behavioral_threshold:.2f}"
                ),
            )

        return ValidationResult(
            valid=True,
            confidence=confidence,
            sub_agent_id=sub_agent_id,
            task_class=task_class,
        )

    def _behavioral_confidence(
        self,
        task_result: Dict[str, Any],
        sub_agent_id: str,
        task_class: str,
    ) -> float:
        """
        Returns a 0.0–1.0 confidence score.

        Priority:
          1. Custom validator if registered
          2. Model-reported confidence field if present
          3. Output completeness ratio vs. schema
          4. Fallback: 1.0 (pass-through — schema validation already ran)
        """
        # Custom validator takes priority
        custom = self._custom_validators.get(task_class)
        if custom:
            try:
                return float(custom(task_result))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Custom validator error for %s: %s", task_class, exc)

        output = task_result.get("output", {})

        # Use model-reported confidence if present
        for conf_key in ("confidence", "score", "certainty", "quality_score"):
            if conf_key in output:
                try:
                    return max(0.0, min(1.0, float(output[conf_key])))
                except (TypeError, ValueError):
                    pass

        # Completeness ratio vs registered schema
        schema = self._schemas.get(task_class)
        if schema:
            required = schema.get("required_fields", [])
            if required:
                present = sum(1 for f in required if f in output)
                return present / len(required)

        return 1.0  # No schema, no custom validator — pass through

    def semantic_validation_rate(self, sub_agent_id: str, task_class: str) -> Optional[float]:
        """
        Returns the rolling semantic validation success rate (0–100 %) for a sub-agent.
        Use this to feed your CloudWatch circuit breaker alarm.
        """
        key = f"{sub_agent_id}:{task_class}"
        scores = self._baselines.get(key, [])
        if not scores:
            return None
        passing = sum(1 for s in scores if s >= self.behavioral_threshold)
        return (passing / len(scores)) * 100
