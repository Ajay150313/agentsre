# Changelog

## 0.5.1

### Fixed
- Package layout: `metrics`, `cloudwatch`, `validators` and `circuit_breaker` now live
  at the package root, so `from agentsre import AgentSLICollector` works as documented.
  `agentsre.sprawl` (fleet inventory, framework governance) is now part of the package.
- Build backend in `pyproject.toml` pointed at a module that does not exist, so
  `pip install .` failed. It now uses `setuptools.build_meta`.
- `__init__` no longer swallows import errors with bare `except: pass`.
- Baseline drift (DQR, TIE, HER, AQDD) is now measured against the baseline from previous
  windows. Previously the current window was folded in first and diluted the spike.
- `A2ASemanticValidator.semantic_validation_rate` now counts empty-output, missing-field
  and type-mismatch failures. Previously only behavioral scores were counted, so the rate
  stayed at 100% while structural failures piled up.
- `CircuitState` from the circuit breaker is exported from the package root; the audit
  gate enum is exported as `AOSCircuitState`.
- Cost optimizer example called methods as properties.

### Removed
- `agentsre.orchestration` and its two examples: the source file was truncated and did not
  import. It will return as a rewritten module.

### Added

### Added
- `IdempotencyGuard` and `DuplicateActionRate` for irreversible agent actions
- Example: `examples/idempotency_guard.py`

## 0.1.0 - April 22, 2025

First release. Reliability instrumentation for AI agents in production.

What's included:
- Four SLIs designed specifically for agents (DQR, TIE, HER, AQDD)
- A2A semantic validator (catches bad decisions between agents)
- Circuit breaker for agent chains
- AWS CloudWatch integration
- Framework examples (LangChain, CrewAI, Bedrock)

What's next:
- GCP Cloud Monitoring
- Azure Application Insights
- Prometheus exporter
- More framework integrations
