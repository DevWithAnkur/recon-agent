import pandas as pd

from src.matching.deterministic import fee_adjusted_match


def test_fee_adjusted_match_accepts_configured_fee():
	gateway = pd.DataFrame(
		[{"order_id": "ORD-1", "amount": 1000.0, "created_at": "2026-01-01"}]
	)
	bank = pd.DataFrame(
		[{"utr": "UTR-1", "settled_amount": 980.0, "settlement_date": "2026-01-02", "batch_reference": "ORD-1"}]
	)

	matches = fee_adjusted_match(gateway, bank)

	assert len(matches) == 1
	assert matches[0].confidence == 0.9
	assert matches[0].strategy == "fee_adjusted_match"
