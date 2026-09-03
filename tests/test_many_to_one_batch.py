import pandas as pd

from src.matching.deterministic import many_to_one_batch_match


def test_five_gateway_transactions_match_one_bank_utr():
	gateway = pd.DataFrame(
		[
			{"order_id": f"ORD-{index}", "amount": 1000.0, "created_at": "2026-01-01"}
			for index in range(1, 6)
		]
	)
	bank = pd.DataFrame(
		[{"utr": "UTR-BATCH", "settled_amount": 4900.0, "settlement_date": "2026-01-02", "batch_reference": "BATCH-1"}]
	)

	matches = many_to_one_batch_match(gateway, bank)

	assert len(matches) == 1
	assert len(matches[0].order_ids) == 5
	assert matches[0].confidence == 0.85
