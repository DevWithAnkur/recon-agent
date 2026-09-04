from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import pandas as pd


REASON_CODES = {
	"missing_settlement",
	"fee_calculation_mismatch",
	"duplicate_entry",
	"currency_rounding",
	"refund_not_netted",
	"timing_gap",
}


@dataclass(frozen=True)
class ExceptionRecord:
	record_id: str
	reason_code: str
	human_readable_reason: str
	confidence_at_failure: float
	candidates_considered: list[dict[str, Any]]


def _records(candidates: pd.DataFrame | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
	if isinstance(candidates, pd.DataFrame):
		return [row.astype(object).where(pd.notna(row), None).to_dict() for _, row in candidates.iterrows()]
	return [dict(candidate) for candidate in candidates]


def _candidate_amount(candidate: Mapping[str, Any]) -> float | None:
	value = candidate.get("settled_amount", candidate.get("recorded_amount"))
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def classify_exception(
	gateway_record: Mapping[str, Any] | pd.Series,
	candidates: pd.DataFrame | Sequence[Mapping[str, Any]],
	confidence_at_failure: float,
	llm_reasoning: str | None = None,
	tolerance: float = 1.0,
) -> ExceptionRecord:
	"""Classify an unresolved record conservatively using evidence available locally."""
	gateway = gateway_record.to_dict() if isinstance(gateway_record, pd.Series) else dict(gateway_record)
	candidate_records = _records(candidates)
	record_id = str(gateway.get("order_id", gateway.get("ledger_entry_id", "unknown")))
	amount = float(gateway.get("amount", 0))
	status = str(gateway.get("status", "")).lower()

	if gateway.get("currency") not in (None, "INR"):
		reason_code = "currency_rounding"
		reason = "The gateway currency is outside the supported INR reconciliation scope."
	elif status == "refund":
		reason_code = "refund_not_netted"
		reason = "The gateway refund is not reflected in the settlement amount."
	elif not candidate_records:
		reason_code = "missing_settlement"
		reason = "No corresponding bank or ledger entry was found."
	elif len(candidate_records) > 1:
		amounts = [_candidate_amount(candidate) for candidate in candidate_records]
		expected_fee_amount = amount * (1 - 0.02)
		close_candidates = [
			value
			for value in amounts
			if value is not None
			and (
				abs(value - amount) <= tolerance
				or abs(value - expected_fee_amount) <= tolerance
			)
		]
		if len(close_candidates) > 1:
			reason_code = "duplicate_entry"
			reason = "Multiple candidate entries plausibly match this transaction."
		else:
			reason_code = "fee_calculation_mismatch"
			reason = "Candidate amounts do not match a supported fee calculation."
	else:
		candidate = candidate_records[0]
		candidate_amount_value = _candidate_amount(candidate)
		if candidate_amount_value is not None and abs(candidate_amount_value - amount) <= tolerance:
			reason_code = "timing_gap"
			reason = "Amounts match, but the settlement timing is outside the expected window."
		elif candidate.get("currency") not in (None, gateway.get("currency")):
			reason_code = "currency_rounding"
			reason = "The candidate uses a different currency and cannot be safely reconciled."
		else:
			reason_code = "fee_calculation_mismatch"
			reason = "The amount difference exceeds the configured fee tolerance."

	if llm_reasoning:
		reason = f"{reason} LLM reasoning: {llm_reasoning}"
	assert reason_code in REASON_CODES
	return ExceptionRecord(
		record_id=record_id,
		reason_code=reason_code,
		human_readable_reason=reason,
		confidence_at_failure=confidence_at_failure,
		candidates_considered=candidate_records,
	)
