from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.matching.deterministic import Match
from src.matching.exceptions import ExceptionRecord


def _json_value(value: Any) -> Any:
	if is_dataclass(value):
		return {key: _json_value(item) for key, item in asdict(value).items()}
	if isinstance(value, (list, tuple)):
		return [_json_value(item) for item in value]
	if isinstance(value, dict):
		return {str(key): _json_value(item) for key, item in value.items()}
	return value


def audit_events(
	matches: Iterable[Match],
	exceptions: Iterable[ExceptionRecord],
) -> list[dict[str, Any]]:
	"""Create one audit event per reconciled order or unresolved record."""
	timestamp = datetime.now(timezone.utc).isoformat()
	events: list[dict[str, Any]] = []
	for match in matches:
		layer = 2 if match.strategy == "llm_resolver" else 1
		for order_id in match.order_ids:
			events.append(
				{
					"timestamp": timestamp,
					"record_id": order_id,
					"resolution": "matched",
					"layer_that_resolved_it": layer,
					"confidence": match.confidence,
					"reasoning": match.reason,
					"evidence": {"utr": match.utr, "strategy": match.strategy},
				}
			)
	for exception in exceptions:
		events.append(
			{
				"timestamp": timestamp,
				"record_id": exception.record_id,
				"resolution": "exception",
				"layer_that_resolved_it": 3,
				"confidence": exception.confidence_at_failure,
				"reasoning": exception.human_readable_reason,
				"evidence": {"reason_code": exception.reason_code, "candidates": exception.candidates_considered},
			}
		)
	return events


def write_audit_log(
	matches: Iterable[Match],
	exceptions: Iterable[ExceptionRecord],
	path: str | Path = "output/audit_log.jsonl",
) -> Path:
	"""Append the current batch's audit events to a JSONL file."""
	log_path = Path(path)
	log_path.parent.mkdir(parents=True, exist_ok=True)
	with log_path.open("a", encoding="utf-8") as file_handle:
		for event in audit_events(matches, exceptions):
			file_handle.write(json.dumps(_json_value(event), default=str) + "\n")
	return log_path


def build_match_rate_report(
	total_records: int,
	matches: Iterable[Match],
	exceptions: Iterable[ExceptionRecord],
) -> dict[str, Any]:
	"""Return a serializable summary of the current reconciliation batch."""
	match_list = list(matches)
	exception_list = list(exceptions)
	matched_records = sum(len(match.order_ids) for match in match_list)
	layer_one_records = sum(
		len(match.order_ids) for match in match_list if match.strategy != "llm_resolver"
	)
	layer_two_records = matched_records - layer_one_records
	reason_counts: dict[str, int] = {}
	for exception in exception_list:
		reason_counts[exception.reason_code] = reason_counts.get(exception.reason_code, 0) + 1
	return {
		"total_records": total_records,
		"matched_records": matched_records,
		"layer_1_matched": layer_one_records,
		"layer_2_matched": layer_two_records,
		"exceptions": len(exception_list),
		"match_rate": matched_records / total_records if total_records else 0.0,
		"exceptions_by_reason": reason_counts,
	}
