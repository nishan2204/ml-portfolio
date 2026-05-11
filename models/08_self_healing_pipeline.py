"""
Self-Healing Pipeline Agent
Monitoring agent wired into Airflow DAGs that detects, classifies, and remediates
data pipeline failures. Auto-remediates known patterns; escalates novel failures
with Claude-generated incident reports.
"""

import json
import time
import boto3
import anthropic
import great_expectations as gx
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime, timedelta
from airflow.models import DagRun, TaskInstance
from airflow.utils.state import State
from airflow.hooks.base import BaseHook


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FAILURE_CLASSES = [
    "schema_drift",
    "upstream_data_issue",
    "compute_failure",
    "dependency_timeout",
    "data_volume_anomaly",
    "data_quality_violation",
    "unknown",
]

SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:ACCOUNT_ID:pipeline-alerts"
LAMBDA_REMEDIATION_ARN = "arn:aws:lambda:us-east-1:ACCOUNT_ID:pipeline-remediation"
MAX_AUTO_REMEDIATION_ATTEMPTS = 3
ALERT_COOLDOWN_MINUTES = 15
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PipelineFailure:
    dag_id: str
    task_id: str
    run_id: str
    failure_timestamp: str
    error_message: str
    error_traceback: str
    upstream_tasks: list[str]
    execution_duration_seconds: float
    expected_duration_seconds: float
    input_row_count: Optional[int] = None
    expected_row_count: Optional[int] = None
    schema_actual: Optional[dict] = None
    schema_expected: Optional[dict] = None

@dataclass
class FailureClassification:
    failure_class: str
    confidence: float
    evidence: list[str]
    auto_remediable: bool
    remediation_action: Optional[str] = None

@dataclass
class IncidentReport:
    incident_id: str
    failure: PipelineFailure
    classification: FailureClassification
    downstream_impact: list[str]
    estimated_data_loss_rows: int
    remediation_applied: Optional[str]
    remediation_succeeded: Optional[bool]
    narrative: str
    severity: str              # "P1" | "P2" | "P3"
    created_at: str


# ---------------------------------------------------------------------------
# Failure classifier (rule-based)
# ---------------------------------------------------------------------------

class FailureClassifier:
    """
    Rule-based classifier covering known failure patterns.
    Falls through to 'unknown' for novel failures, which triggers LLM escalation.
    """

    def classify(self, failure: PipelineFailure) -> FailureClassification:
        evidence = []

        # Schema drift detection
        if failure.schema_actual and failure.schema_expected:
            added = set(failure.schema_actual) - set(failure.schema_expected)
            removed = set(failure.schema_expected) - set(failure.schema_actual)
            type_changes = {
                col for col in (set(failure.schema_actual) & set(failure.schema_expected))
                if failure.schema_actual[col] != failure.schema_expected[col]
            }
            if added or removed or type_changes:
                evidence.append(f"Schema changed: +{added} -{removed} ~{type_changes}")
                return FailureClassification(
                    failure_class="schema_drift",
                    confidence=0.95,
                    evidence=evidence,
                    auto_remediable=True,
                    remediation_action="evolve_schema",
                )

        # Data volume anomaly
        if failure.input_row_count is not None and failure.expected_row_count:
            ratio = failure.input_row_count / max(failure.expected_row_count, 1)
            if ratio < 0.5 or ratio > 2.0:
                evidence.append(f"Row count ratio {ratio:.2f} (got {failure.input_row_count}, "
                                 f"expected ~{failure.expected_row_count})")
                return FailureClassification(
                    failure_class="upstream_data_issue" if ratio < 0.5 else "data_volume_anomaly",
                    confidence=0.88,
                    evidence=evidence,
                    auto_remediable=ratio < 0.5,
                    remediation_action="rerun_upstream_dag" if ratio < 0.5 else None,
                )

        # Compute failure patterns
        compute_keywords = ["OutOfMemoryError", "MemoryError", "KilledWorkerError",
                            "BrokenPipeError", "ResourceExhausted", "SIGKILL"]
        if any(kw in failure.error_traceback for kw in compute_keywords):
            evidence.append(f"Compute failure keyword detected in traceback")
            return FailureClassification(
                failure_class="compute_failure",
                confidence=0.90,
                evidence=evidence,
                auto_remediable=True,
                remediation_action="scale_up_worker",
            )

        # Dependency timeout
        timeout_keywords = ["TimeoutError", "ConnectionTimeout", "socket.timeout",
                             "ReadTimeoutError", "TaskDeferred"]
        duration_ratio = (failure.execution_duration_seconds /
                          max(failure.expected_duration_seconds, 1))
        if any(kw in failure.error_traceback for kw in timeout_keywords) or duration_ratio > 3.0:
            evidence.append(f"Duration ratio: {duration_ratio:.1f}x expected")
            return FailureClassification(
                failure_class="dependency_timeout",
                confidence=0.85,
                evidence=evidence,
                auto_remediable=True,
                remediation_action="retry_with_backoff",
            )

        # Data quality violation
        if "GreatExpectationsValidationError" in failure.error_traceback:
            evidence.append("Great Expectations validation suite failed")
            return FailureClassification(
                failure_class="data_quality_violation",
                confidence=0.97,
                evidence=evidence,
                auto_remediable=False,
                remediation_action=None,
            )

        return FailureClassification(
            failure_class="unknown",
            confidence=0.40,
            evidence=["No matching rule patterns found"],
            auto_remediable=False,
        )


# ---------------------------------------------------------------------------
# Great Expectations — data contract validation
# ---------------------------------------------------------------------------

class DataContractValidator:
    def __init__(self, expectation_suite_name: str, data_source_name: str):
        self.context = gx.get_context()
        self.suite_name = expectation_suite_name
        self.datasource_name = data_source_name

    def validate(self, df: pd.DataFrame) -> tuple[bool, list[str]]:
        validator = self.context.get_validator(
            batch_request=self.context.get_datasource(self.datasource_name)
                .get_asset("runtime_asset")
                .build_batch_request(dataframe=df),
            expectation_suite_name=self.suite_name,
        )
        results = validator.validate()
        failures = [
            r["expectation_config"]["expectation_type"] + ": " +
            str(r["result"])
            for r in results["results"]
            if not r["success"]
        ]
        return results["success"], failures

    def build_standard_suite(self, reference_df: pd.DataFrame):
        """Auto-generate expectations from a reference dataset."""
        validator = self.context.get_validator(
            batch_request=self.context.get_datasource(self.datasource_name)
                .get_asset("runtime_asset")
                .build_batch_request(dataframe=reference_df),
            expectation_suite_name=self.suite_name,
        )
        for col in reference_df.columns:
            validator.expect_column_to_exist(col)
            if reference_df[col].dtype in ["int64", "float64"]:
                validator.expect_column_values_to_not_be_null(col, mostly=0.95)
                low, high = reference_df[col].quantile(0.01), reference_df[col].quantile(0.99)
                validator.expect_column_values_to_be_between(col, min_value=low, max_value=high)
        validator.save_expectation_suite()


# ---------------------------------------------------------------------------
# Auto-remediation actions
# ---------------------------------------------------------------------------

class RemediationEngine:
    def __init__(self):
        self.lambda_client = boto3.client("lambda")
        self.airflow_conn = BaseHook.get_connection("airflow_api")
        self._attempt_counts: dict[str, int] = {}

    def _check_attempt_limit(self, failure_key: str) -> bool:
        count = self._attempt_counts.get(failure_key, 0)
        if count >= MAX_AUTO_REMEDIATION_ATTEMPTS:
            return False
        self._attempt_counts[failure_key] = count + 1
        return True

    def remediate(self, failure: PipelineFailure,
                  classification: FailureClassification) -> tuple[bool, str]:
        key = f"{failure.dag_id}.{failure.task_id}"
        if not self._check_attempt_limit(key):
            return False, "Max auto-remediation attempts exceeded"

        action = classification.remediation_action
        if action == "evolve_schema":
            return self._evolve_schema(failure)
        elif action == "retry_with_backoff":
            return self._retry_task(failure, delay_seconds=60)
        elif action == "scale_up_worker":
            return self._scale_worker(failure)
        elif action == "rerun_upstream_dag":
            return self._rerun_upstream(failure)
        return False, f"No handler for action: {action}"

    def _retry_task(self, failure: PipelineFailure,
                    delay_seconds: int = 60) -> tuple[bool, str]:
        time.sleep(delay_seconds)
        payload = {"dag_id": failure.dag_id, "task_id": failure.task_id,
                   "run_id": failure.run_id, "action": "clear_task"}
        self.lambda_client.invoke(
            FunctionName=LAMBDA_REMEDIATION_ARN,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        return True, f"Task {failure.task_id} cleared for retry after {delay_seconds}s backoff"

    def _evolve_schema(self, failure: PipelineFailure) -> tuple[bool, str]:
        added = (set(failure.schema_actual or {}) - set(failure.schema_expected or {}))
        removed = (set(failure.schema_expected or {}) - set(failure.schema_actual or {}))
        changes = {"added": list(added), "removed": list(removed)}
        payload = {"action": "evolve_schema", "dag_id": failure.dag_id, "changes": changes}
        self.lambda_client.invoke(
            FunctionName=LAMBDA_REMEDIATION_ARN,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        return True, f"Schema evolved: added {added}, removed {removed}"

    def _scale_worker(self, failure: PipelineFailure) -> tuple[bool, str]:
        payload = {"action": "scale_up", "dag_id": failure.dag_id,
                   "resource_multiplier": 2.0}
        self.lambda_client.invoke(
            FunctionName=LAMBDA_REMEDIATION_ARN,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        return True, "Worker resources scaled up 2x, retrying task"

    def _rerun_upstream(self, failure: PipelineFailure) -> tuple[bool, str]:
        payload = {"action": "trigger_dag", "dag_id": failure.upstream_tasks[0]}
        self.lambda_client.invoke(
            FunctionName=LAMBDA_REMEDIATION_ARN,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        return True, f"Triggered upstream DAG: {failure.upstream_tasks[0]}"


# ---------------------------------------------------------------------------
# Claude API — incident report generation for novel/unresolved failures
# ---------------------------------------------------------------------------

INCIDENT_PROMPT = """You are a data engineering incident response system.
Given a pipeline failure and its context, generate a structured incident report
for the on-call team. Be precise about downstream impact and remediation options.

Return valid JSON:
{
  "narrative": "2-3 sentence description of what happened and likely cause",
  "downstream_impact": ["impacted system 1", "impacted system 2"],
  "estimated_data_loss_rows": 0,
  "severity": "P1|P2|P3",
  "recommended_actions": ["action 1", "action 2"]
}

Severity: P1 = production data loss or SLA breach, P2 = delayed reporting, P3 = non-critical."""

def generate_incident_report(failure: PipelineFailure,
                              classification: FailureClassification) -> dict:
    client = anthropic.Anthropic()
    user_content = (
        f"DAG: {failure.dag_id} | Task: {failure.task_id}\n"
        f"Error: {failure.error_message}\n"
        f"Classification: {classification.failure_class} "
        f"(confidence={classification.confidence:.0%})\n"
        f"Evidence: {', '.join(classification.evidence)}\n"
        f"Duration: {failure.execution_duration_seconds:.0f}s "
        f"(expected: {failure.expected_duration_seconds:.0f}s)\n"
        f"Upstream tasks: {', '.join(failure.upstream_tasks)}"
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        system=INCIDENT_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text.strip().lstrip("```json").rstrip("```").strip()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# SNS alerting
# ---------------------------------------------------------------------------

def send_alert(report: IncidentReport):
    sns = boto3.client("sns")
    message = (
        f"[{report.severity}] Pipeline Failure — {report.failure.dag_id}.{report.failure.task_id}\n\n"
        f"Classification: {report.classification.failure_class}\n"
        f"Narrative: {report.narrative}\n"
        f"Downstream impact: {', '.join(report.downstream_impact)}\n"
        f"Remediation: {report.remediation_applied or 'manual intervention required'}\n"
        f"Incident ID: {report.incident_id}"
    )
    sns.publish(TopicArn=SNS_TOPIC_ARN, Message=message,
                Subject=f"[{report.severity}] Pipeline Alert: {report.failure.dag_id}")


# ---------------------------------------------------------------------------
# Main monitoring agent
# ---------------------------------------------------------------------------

class PipelineMonitorAgent:
    def __init__(self):
        self.classifier = FailureClassifier()
        self.remediation = RemediationEngine()
        self._alert_timestamps: dict[str, datetime] = {}

    def _cooldown_ok(self, key: str) -> bool:
        last = self._alert_timestamps.get(key)
        if last and (datetime.utcnow() - last) < timedelta(minutes=ALERT_COOLDOWN_MINUTES):
            return False
        self._alert_timestamps[key] = datetime.utcnow()
        return True

    def handle_failure(self, failure: PipelineFailure) -> IncidentReport:
        classification = self.classifier.classify(failure)

        remediation_applied = None
        remediation_succeeded = None
        if classification.auto_remediable:
            success, message = self.remediation.remediate(failure, classification)
            remediation_applied = message
            remediation_succeeded = success

        incident_data = generate_incident_report(failure, classification)

        report = IncidentReport(
            incident_id=f"INC-{int(time.time())}",
            failure=failure,
            classification=classification,
            downstream_impact=incident_data.get("downstream_impact", []),
            estimated_data_loss_rows=incident_data.get("estimated_data_loss_rows", 0),
            remediation_applied=remediation_applied,
            remediation_succeeded=remediation_succeeded,
            narrative=incident_data.get("narrative", ""),
            severity=incident_data.get("severity", "P2"),
            created_at=datetime.utcnow().isoformat(),
        )

        alert_key = f"{failure.dag_id}.{failure.task_id}"
        if self._cooldown_ok(alert_key):
            send_alert(report)

        return report


if __name__ == "__main__":
    failure = PipelineFailure(
        dag_id="nightly_claims_etl",
        task_id="transform_denial_features",
        run_id="scheduled__2025-03-14T02:00:00+00:00",
        failure_timestamp="2025-03-14T02:47:33Z",
        error_message="Column 'payer_network_tier' not found in source schema",
        error_traceback="KeyError: 'payer_network_tier'\n  at transform.py:142",
        upstream_tasks=["extract_claims_raw", "extract_payer_ref"],
        execution_duration_seconds=1820,
        expected_duration_seconds=600,
        schema_actual={"claim_id": "str", "payer_id": "str", "amount": "float"},
        schema_expected={"claim_id": "str", "payer_id": "str", "amount": "float",
                         "payer_network_tier": "str"},
        input_row_count=42000,
        expected_row_count=45000,
    )

    agent = PipelineMonitorAgent()
    classification = agent.classifier.classify(failure)
    print(f"Classification: {classification.failure_class} ({classification.confidence:.0%})")
    print(f"Auto-remediable: {classification.auto_remediable}")
    print(f"Evidence: {classification.evidence}")
    print("Incident report generation requires AWS credentials and Claude API key.")
