import pandas as pd

from src.matching.deterministic import run_deterministic_matching


def test_unexplainable_amount_difference_is_not_force_matched():
	gateway = pd.DataFrame(
		[{"order_id": "ORD-1", "amount": 1000.0, "created_at": "2026-01-01"}]
	)
	bank = pd.DataFrame(
		[{"utr": "UTR-1", "settled_amount": 937.0, "settlement_date": "2026-01-02", "batch_reference": "ORD-1"}]
	)

	assert run_deterministic_matching(gateway, bank) == []
