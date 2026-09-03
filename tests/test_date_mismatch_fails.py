import pandas as pd

from src.matching.deterministic import exact_match


def test_date_outside_settlement_window_does_not_match():
	gateway = pd.DataFrame(
		[{"order_id": "ORD-1", "amount": 1000.0, "created_at": "2026-01-01"}]
	)
	bank = pd.DataFrame(
		[{"utr": "UTR-1", "settled_amount": 1000.0, "settlement_date": "2026-01-05", "batch_reference": "ORD-1"}]
	)

	assert exact_match(gateway, bank) == []
