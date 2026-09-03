from pathlib import Path

import pandas as pd

from src.matching.deterministic import run_deterministic_matching


def test_layer_one_does_not_write_audit_log(tmp_path: Path):
	gateway = pd.DataFrame(
		[{"order_id": "ORD-1", "amount": 1000.0, "created_at": "2026-01-01"}]
	)
	bank = pd.DataFrame(
		[{"utr": "UTR-1", "settled_amount": 1000.0, "settlement_date": "2026-01-02", "batch_reference": "ORD-1"}]
	)

	run_deterministic_matching(gateway, bank)

	assert not (tmp_path / "audit_log.jsonl").exists()
