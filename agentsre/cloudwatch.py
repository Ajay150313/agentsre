"""
agentsre.cloudwatch
~~~~~~~~~~~~~~~~~~~
Publish SLI results to AWS CloudWatch custom metrics.

Namespace : AgentReliability  (configurable)
Dimensions: AgentId, TaskClass
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from .metrics import SLIResult

logger = logging.getLogger(__name__)

_UNITS = {
    "%": "Percent",
    " calls/task": "Count",
    " pending": "Count",
}


class CloudWatchPublisher:
    """
    Publish SLI results to CloudWatch custom metrics.

    Requires boto3 and appropriate IAM permissions::

        cloudwatch:PutMetricData

    Usage::

        from agentsre import AgentSLICollector
        from agentsre.cloudwatch import CloudWatchPublisher

        collector = AgentSLICollector()
        publisher = CloudWatchPublisher(agent_id="financial-processor")

        results = collector.collect("payment-routing")
        publisher.publish(results)
    """

    def __init__(
        self,
        agent_id: str,
        namespace: str = "AgentReliability",
        region_name: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.agent_id = agent_id
        self.namespace = namespace
        self.dry_run = dry_run
        self._client = None

        if not dry_run:
            try:
                import boto3  # type: ignore
                kwargs = {"service_name": "cloudwatch"}
                if region_name:
                    kwargs["region_name"] = region_name
                self._client = boto3.client(**kwargs)
            except ImportError:
                logger.warning(
                    "boto3 not installed. Install with: pip install agentsre[aws]"
                )

    def publish(self, results: Sequence[SLIResult]) -> None:
        """Publish a list of SLIResult objects to CloudWatch."""
        metric_data = []
        for r in results:
            unit = _UNITS.get(r.unit, "None")
            metric_data.append(
                {
                    "MetricName": r.name,
                    "Dimensions": [
                        {"Name": "AgentId", "Value": self.agent_id},
                        {"Name": "TaskClass", "Value": r.task_class},
                    ],
                    "Timestamp": r.timestamp,
                    "Value": r.value,
                    "Unit": unit,
                }
            )

        if self.dry_run:
            for m in metric_data:
                logger.info("[DRY RUN] Would publish: %s", m)
            return

        if not self._client:
            logger.error("CloudWatch client not available — skipping publish.")
            return

        # CloudWatch accepts max 20 metric data points per call
        for i in range(0, len(metric_data), 20):
            chunk = metric_data[i : i + 20]
            try:
                self._client.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=chunk,
                )
                logger.debug("Published %d metrics to CloudWatch.", len(chunk))
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to publish metrics: %s", exc)

    def publish_breach_alarm(self, result: SLIResult) -> None:
        """
        Helper: publish a dedicated breach event metric (value=1.0)
        so CloudWatch alarms can trigger immediately on a breach.
        """
        if self.dry_run:
            logger.info("[DRY RUN] Breach alarm: %s / %s", result.name, result.task_class)
            return
        self.publish(
            [
                SLIResult(
                    name=f"{result.name}Breach",
                    value=1.0,
                    unit="",
                    task_class=result.task_class,
                    window_seconds=result.window_seconds,
                    sample_count=result.sample_count,
                    baseline=result.baseline,
                    drift_ratio=result.drift_ratio,
                    breached=True,
                    threshold=result.threshold,
                    timestamp=result.timestamp,
                )
            ]
        )
