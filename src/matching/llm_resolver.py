from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.matching.deterministic import Match
from src.matching.exceptions import ExceptionRecord, classify_exception


DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_CONFIDENCE_THRESHOLD = 0.85


class LLMResolution(BaseModel):
	"""Structured response accepted from the LLM reasoning layer."""

	model_config = ConfigDict(extra="forbid")

	match_found: bool
	matched_entry_id: str | None
	confidence: float = Field(ge=0.0, le=1.0)
	reasoning: str = Field(min_length=1)
	discrepancy_amount: float = Field(ge=0.0)

	@model_validator(mode="after")
	def validate_match_reference(self) -> "LLMResolution":
		if self.match_found and not self.matched_entry_id:
			raise ValueError("matched_entry_id is required when match_found is true")
		return self


def _as_record(record: Mapping[str, Any] | pd.Series) -> dict[str, Any]:
	return {str(key): value.item() if hasattr(value, "item") else value for key, value in record.items()}


def select_top_candidates(
	gateway_record: Mapping[str, Any] | pd.Series,
	candidates: pd.DataFrame | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
	"""Return at most three bank/ledger candidates ordered by amount proximity."""
	gateway_amount = float(gateway_record["amount"])
	if isinstance(candidates, pd.DataFrame):
		candidate_records = [_as_record(row) for _, row in candidates.iterrows()]
	else:
		candidate_records = [_as_record(candidate) for candidate in candidates]
	return sorted(
		candidate_records,
		key=lambda candidate: abs(
			float(candidate.get("settled_amount", candidate.get("recorded_amount", 0)))
			- gateway_amount
		),
	)[:3]


def build_prompt(
	gateway_record: Mapping[str, Any] | pd.Series,
	top_candidates: Sequence[Mapping[str, Any]],
) -> str:
	"""Build the auditable input payload sent to the structured-output model."""
	return (
		"Reconcile this unmatched payment transaction. Consider the gateway record "
		"and the three closest bank or ledger candidates. Return only the fields "
		"defined by the supplied response schema. Do not invent a match when the "
		"evidence is insufficient.\n\n"
		f"Gateway transaction:\n{json.dumps(_as_record(gateway_record), default=str, indent=2)}\n\n"
		f"Candidate entries:\n{json.dumps(list(top_candidates), default=str, indent=2)}"
	)


def _default_client() -> Any:
	from openai import OpenAI

	load_dotenv()
	return OpenAI(timeout=15.0, max_retries=1)


def resolve_with_llm(
	gateway_record: Mapping[str, Any] | pd.Series,
	candidates: pd.DataFrame | Sequence[Mapping[str, Any]],
	client: Any | None = None,
	model: str = DEFAULT_MODEL,
) -> LLMResolution:
	"""Ask OpenAI for a strictly validated resolution of one ambiguous record."""
	client = client or _default_client()
	top_candidates = select_top_candidates(gateway_record, candidates)
	response = client.responses.parse(
		model=model,
		input=[
			{
				"role": "system",
				"content": "You are a conservative financial reconciliation analyst.",
			},
			{"role": "user", "content": build_prompt(gateway_record, top_candidates)},
		],
		text_format=LLMResolution,
	)
	if response.output_parsed is None:
		raise ValueError("OpenAI returned no structured reconciliation result")
	return response.output_parsed


def resolve_ambiguous_record(
	gateway_record: Mapping[str, Any] | pd.Series,
	candidates: pd.DataFrame | Sequence[Mapping[str, Any]],
	client: Any | None = None,
	model: str = DEFAULT_MODEL,
	confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Match | ExceptionRecord:
	"""Route every below-threshold LLM result to Layer 3 instead of matching it."""
	print(f"Resolving with LLM: {gateway_record.get('order_id', 'Unknown')}")
	resolution = resolve_with_llm(gateway_record, candidates, client, model)
	if (
		resolution.match_found
		and resolution.confidence >= confidence_threshold
		and resolution.matched_entry_id
	):
		candidate_ids = {
			str(candidate.get("utr", candidate.get("ledger_entry_id", "")))
			for candidate in select_top_candidates(gateway_record, candidates)
		}
		if resolution.matched_entry_id not in candidate_ids:
			return classify_exception(
				gateway_record,
				candidates,
				confidence_at_failure=resolution.confidence,
				llm_reasoning="The model returned an entry that was not among the supplied candidates.",
			)
		amount = float(gateway_record["amount"])
		return Match(
			order_ids=(str(gateway_record["order_id"]),),
			utr=resolution.matched_entry_id,
			gateway_amount=amount,
			bank_amount=amount - resolution.discrepancy_amount,
			confidence=resolution.confidence,
			strategy="llm_resolver",
			reason=resolution.reasoning,
		)

	return classify_exception(
		gateway_record,
		candidates,
		confidence_at_failure=resolution.confidence,
		llm_reasoning=resolution.reasoning,
	)
