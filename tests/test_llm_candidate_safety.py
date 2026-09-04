import pandas as pd

from src.matching.llm_resolver import LLMResolution, resolve_ambiguous_record


def test_llm_cannot_match_entry_outside_supplied_candidates(monkeypatch):
	gateway = pd.Series({"order_id": "ORD-1", "amount": 1000.0, "currency": "INR"})
	candidates = pd.DataFrame(
		[{"utr": "UTR-1", "settled_amount": 980.0, "batch_reference": "ORD-1"}]
	)
	resolution = LLMResolution(
		match_found=True,
		matched_entry_id="UTR-INVENTED",
		confidence=0.99,
		reasoning="The records appear related.",
		discrepancy_amount=20.0,
	)
	monkeypatch.setattr(
		"src.matching.llm_resolver.resolve_with_llm",
		lambda *args, **kwargs: resolution,
	)

	result = resolve_ambiguous_record(gateway, candidates)

	assert result.reason_code == "fee_calculation_mismatch"
	assert "not among the supplied candidates" in result.human_readable_reason