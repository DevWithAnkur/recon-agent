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


def test_batch_match_uses_percentage_tolerance_of_gateway_total():
	gateway = pd.DataFrame(
		[
			{"order_id": "ORD-1", "amount": 1000.0, "created_at": "2026-01-01"},
			{"order_id": "ORD-2", "amount": 1000.0, "created_at": "2026-01-01"},
		]
	)
	bank = pd.DataFrame(
		[{"utr": "UTR-BATCH", "settled_amount": 2008.0, "settlement_date": "2026-01-02", "batch_reference": "BATCH-1"}]
	)

	assert len(many_to_one_batch_match(gateway, bank)) == 1
