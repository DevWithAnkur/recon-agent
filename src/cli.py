from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.matching.deterministic import Match, run_deterministic_matching
from src.matching.exceptions import ExceptionRecord, classify_exception
from src.matching.llm_resolver import resolve_ambiguous_record
from src.reporting.audit import build_match_rate_report, write_audit_log
from src.reporting.webhook import notify_exception, notify_match, notify_summary


def _candidate_rows(gateway_row: pd.Series, bank: pd.DataFrame) -> pd.DataFrame:
	amount = float(gateway_row["amount"])
	candidates = bank.copy()
	candidates["_distance"] = (candidates["settled_amount"].astype(float) - amount).abs()
	return candidates.sort_values("_distance").head(3).drop(columns="_distance")


def reconcile(
	gateway_path: str | Path,
	bank_path: str | Path,
	ledger_path: str | Path | None = None,
	dry_run: bool = False,
	fee_rate: float = 0.02,
	confidence_threshold: float = 0.85,
	no_webhook: bool = False,
) -> tuple[list[Match], list[ExceptionRecord], dict[str, object]]:
	load_dotenv()
	gateway = pd.read_csv(gateway_path)
	bank = pd.read_csv(bank_path)
	matches = run_deterministic_matching(gateway, bank, fee_rate=fee_rate)
	matched_orders = {order_id for match in matches for order_id in match.order_ids}
	matched_utrs = {match.utr for match in matches}
	llm_matches: list[Match] = []
	exceptions: list[ExceptionRecord] = []
	for _, gateway_row in gateway.iterrows():
		order_id = str(gateway_row["order_id"])
		if order_id in matched_orders:
			continue
		candidates = _candidate_rows(gateway_row, bank)
		try:
			resolution = resolve_ambiguous_record(
				gateway_row,
				candidates,
				confidence_threshold=confidence_threshold,
			)
		except Exception as error:
			resolution = classify_exception(
				gateway_row,
				candidates,
				confidence_at_failure=0.0,
				llm_reasoning=f"LLM resolution unavailable: {error}",
			)
		if isinstance(resolution, Match) and resolution.utr not in matched_utrs:
			llm_matches.append(resolution)
			matched_orders.update(resolution.order_ids)
			matched_utrs.add(resolution.utr)
		else:
			exceptions.append(resolution)
	matches.extend(llm_matches)
	report = build_match_rate_report(len(gateway), matches, exceptions)
	if not dry_run:
		write_audit_log(matches, exceptions)
	if not no_webhook:
		for exception in exceptions:
			notify_exception(exception)
		for match in matches:
			if match.confidence >= 0.97 or match.order_ids[-1].endswith("0"):
				notify_match(match)
		notify_summary(report)
	return matches, exceptions, report


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Autonomous settlement reconciliation engine")
	subparsers = parser.add_subparsers(dest="command", required=True)
	reconcile_parser = subparsers.add_parser("reconcile")
	reconcile_parser.add_argument("--gateway", default="data/gateway.csv")
	reconcile_parser.add_argument("--bank", default="data/bank_settlement.csv")
	reconcile_parser.add_argument("--ledger", default="data/merchant_ledger.csv")
	reconcile_parser.add_argument("--dry-run", action="store_true")
	reconcile_parser.add_argument("--fee-rate", type=float, default=0.02)
	reconcile_parser.add_argument("--confidence-threshold", type=float, default=0.85)
	reconcile_parser.add_argument("--no-webhook", action="store_true")
	return parser


def main() -> None:
	args = _build_parser().parse_args()
	if args.command == "reconcile":
		_, exceptions, report = reconcile(
			args.gateway,
			args.bank,
			args.ledger,
			args.dry_run,
			args.fee_rate,
			args.confidence_threshold,
			args.no_webhook,
		)
		prefix = "[DRY-RUN] " if args.dry_run else ""
		print(f"{prefix}{report['matched_records']} matched, {len(exceptions)} exceptions.")
		print(f"{prefix}Match rate: {report['match_rate']:.1%}")
		if args.dry_run:
			print(f"{prefix}No records committed.")


if __name__ == "__main__":
	main()
