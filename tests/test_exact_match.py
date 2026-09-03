import pandas as pd

from src.matching.deterministic import exact_match


def test_exact_match_returns_full_confidence_match():
	gateway = pd.DataFrame(
		[{"order_id": "ORD-1", "amount": 1000.0, "created_at": "2026-01-01"}]
	)
	bank = pd.DataFrame(
		[{"utr": "UTR-1", "settled_amount": 1000.0, "settlement_date": "2026-01-02", "batch_reference": "ORD-1"}]
	)

	matches = exact_match(gateway, bank)

	assert len(matches) == 1
	assert matches[0].order_id == "ORD-1"
	assert matches[0].utr == "UTR-1"
	assert matches[0].confidence == 1.0
