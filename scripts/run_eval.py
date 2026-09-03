from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.matching.deterministic import run_deterministic_matching


def score_predictions(gateway: pd.DataFrame, mapping: pd.DataFrame, matches: list) -> dict[str, float | int]:
	predictions = {
		order_id: match.utr
		for match in matches
		for order_id in match.order_ids
	}
	truth = {str(row.order_id): row for row in mapping.itertuples()}
	true_positive = sum(
		row.is_resolvable and predictions.get(order_id) == row.correct_utr
		for order_id, row in truth.items()
	)
	false_positive = sum(
		predictions.get(order_id) is not None
		and (not row.is_resolvable or predictions[order_id] != row.correct_utr)
		for order_id, row in truth.items()
	)
	false_negative = sum(
		row.is_resolvable and predictions.get(order_id) != row.correct_utr
		for order_id, row in truth.items()
	)
	precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
	recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
	f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
	return {
		"total": len(gateway),
		"true_positive": true_positive,
		"false_positive": false_positive,
		"false_negative": false_negative,
		"precision": precision,
		"recall": recall,
		"f1": f1,
	}


def main() -> None:
	root = Path(__file__).resolve().parents[1]
	gateway = pd.read_csv(root / "data/gateway.csv")
	bank = pd.read_csv(root / "data/bank_settlement.csv")
	mapping = pd.read_csv(root / "data/batch_mapping.csv")
	matches = run_deterministic_matching(gateway, bank)
	scores = score_predictions(gateway, mapping, matches)
	print(f"Confusion matrix: TP={scores['true_positive']} FP={scores['false_positive']} FN={scores['false_negative']}")
	print(f"Precision: {scores['precision']:.2f}")
	print(f"Recall: {scores['recall']:.2f}")
	print(f"F1: {scores['f1']:.2f}")


if __name__ == "__main__":
	main()
