from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from itertools import combinations
from typing import Iterable

import pandas as pd


DEFAULT_FEE_RATE = 0.02
FEE_TOLERANCE_PCT = 0.025
DEFAULT_SETTLEMENT_WINDOW = (0, 2)


@dataclass(frozen=True)
class Match:
	order_ids: tuple[str, ...]
	utr: str
	gateway_amount: float
	bank_amount: float
	confidence: float
	strategy: str
	reason: str

	@property
	def order_id(self) -> str:
		"""Return the order ID for a one-to-one match."""
		if len(self.order_ids) != 1:
			raise AttributeError("A batch match has multiple order_ids")
		return self.order_ids[0]


def _date_series(frame: pd.DataFrame, column: str) -> pd.Series:
	return pd.to_datetime(frame[column], errors="coerce").dt.normalize()


def _within_settlement_window(
	gateway_date: pd.Timestamp,
	bank_date: pd.Timestamp,
	settlement_window: tuple[int, int],
) -> bool:
	if pd.isna(gateway_date) or pd.isna(bank_date):
		return False
	difference = (bank_date - gateway_date).days
	return settlement_window[0] <= difference <= settlement_window[1]


def _unmatched_ids(
	gateway: pd.DataFrame,
	matches: Iterable[Match],
) -> set[str]:
	matched = {order_id for match in matches for order_id in match.order_ids}
	return set(gateway["order_id"]) - matched


def exact_match(
	gateway: pd.DataFrame,
	bank: pd.DataFrame,
	settlement_window: tuple[int, int] = DEFAULT_SETTLEMENT_WINDOW,
	excluded_order_ids: Iterable[str] = (),
	excluded_utrs: Iterable[str] = (),
) -> list[Match]:
	"""Match one gateway order to one bank row by reference and exact amount."""
	excluded_orders = set(excluded_order_ids)
	excluded_bank = set(excluded_utrs)
	gateway_dates = _date_series(gateway, "created_at")
	bank_dates = _date_series(bank, "settlement_date")
	matches: list[Match] = []

	for gateway_index, gateway_row in gateway.iterrows():
		order_id = str(gateway_row["order_id"])
		if order_id in excluded_orders:
			continue
		candidates = bank[
			(bank["batch_reference"].astype(str) == order_id)
			& (~bank["utr"].astype(str).isin(excluded_bank))
		]
		for bank_index, bank_row in candidates.iterrows():
			if float(gateway_row["amount"]) != float(bank_row["settled_amount"]):
				continue
			if not _within_settlement_window(
				gateway_dates.loc[gateway_index],
				bank_dates.loc[bank_index],
				settlement_window,
			):
				continue
			matches.append(
				Match(
					order_ids=(order_id,),
					utr=str(bank_row["utr"]),
					gateway_amount=float(gateway_row["amount"]),
					bank_amount=float(bank_row["settled_amount"]),
					confidence=1.0,
					strategy="exact_match",
					reason="Order reference and amount match within the settlement window.",
				)
			)
			break
	return matches


def fee_adjusted_match(
	gateway: pd.DataFrame,
	bank: pd.DataFrame,
	fee_rate: float = DEFAULT_FEE_RATE,
	tolerance: float | None = None,
	settlement_window: tuple[int, int] = DEFAULT_SETTLEMENT_WINDOW,
	excluded_order_ids: Iterable[str] = (),
	excluded_utrs: Iterable[str] = (),
) -> list[Match]:
	"""Match one order after applying the configured percentage fee."""
	excluded_orders = set(excluded_order_ids)
	excluded_bank = set(excluded_utrs)
	gateway_dates = _date_series(gateway, "created_at")
	bank_dates = _date_series(bank, "settlement_date")
	matches: list[Match] = []

	for gateway_index, gateway_row in gateway.iterrows():
		order_id = str(gateway_row["order_id"])
		if order_id in excluded_orders:
			continue
		expected_amount = float(gateway_row["amount"]) * (1 - fee_rate)
		candidates = bank[~bank["utr"].astype(str).isin(excluded_bank)].copy()
		candidates["difference"] = (
			candidates["settled_amount"].astype(float) - expected_amount
		).abs()
		candidates = candidates.sort_values("difference")
		amount_tolerance = float(gateway_row["amount"]) * FEE_TOLERANCE_PCT
		for bank_index, bank_row in candidates.iterrows():
			if float(bank_row["difference"]) > amount_tolerance:
				break
			if not _within_settlement_window(
				gateway_dates.loc[gateway_index],
				bank_dates.loc[bank_index],
				settlement_window,
			):
				continue
			matches.append(
				Match(
					order_ids=(order_id,),
					utr=str(bank_row["utr"]),
					gateway_amount=float(gateway_row["amount"]),
					bank_amount=float(bank_row["settled_amount"]),
					confidence=0.9,
					strategy="fee_adjusted_match",
					reason=f"Bank amount matches gateway amount after a {fee_rate:.2%} fee adjustment.",
				)
			)
			break
	return matches


def _find_combination(
	candidates: list[tuple[str, float, pd.Timestamp, float]],
	target: float,
	maximum_size: int = 20,
) -> list[tuple[str, float, pd.Timestamp, float]] | None:
	for size in range(2, min(maximum_size, len(candidates)) + 1):
		for combination in combinations(candidates, size):
			gateway_amount = sum(item[3] for item in combination)
			tolerance = gateway_amount * FEE_TOLERANCE_PCT
			if abs(sum(item[1] for item in combination) - target) <= tolerance:
				return list(combination)
	return None


def many_to_one_batch_match(
	gateway: pd.DataFrame,
	bank: pd.DataFrame,
	fee_rate: float = DEFAULT_FEE_RATE,
	tolerance: float | None = None,
	settlement_window: tuple[int, int] = DEFAULT_SETTLEMENT_WINDOW,
	excluded_order_ids: Iterable[str] = (),
	excluded_utrs: Iterable[str] = (),
) -> list[Match]:
	"""Match multiple gateway orders whose fee-adjusted amounts form one UTR."""
	excluded_orders = set(excluded_order_ids)
	excluded_bank = set(excluded_utrs)
	gateway_dates = _date_series(gateway, "created_at")
	bank_dates = _date_series(bank, "settlement_date")
	candidates = [
		(
			str(row["order_id"]),
			round(float(row["amount"]) * (1 - fee_rate), 2),
			gateway_dates.loc[index],
			float(row["amount"]),
		)
		for index, row in gateway.iterrows()
		if str(row["order_id"]) not in excluded_orders
	]
	matches: list[Match] = []

	for bank_index, bank_row in bank.iterrows():
		utr = str(bank_row["utr"])
		if utr in excluded_bank:
			continue
		bank_date = bank_dates.loc[bank_index]
		eligible = [
			item
			for item in candidates
			if _within_settlement_window(item[2], bank_date, settlement_window)
		]
		combination = _find_combination(
			eligible,
			float(bank_row["settled_amount"]),
		)
		if combination is None:
			continue
		order_ids = tuple(item[0] for item in combination)
		gateway_amount = round(sum(float(gateway.loc[gateway["order_id"] == order_id, "amount"].iloc[0]) for order_id in order_ids), 2)
		matches.append(
			Match(
				order_ids=order_ids,
				utr=utr,
				gateway_amount=gateway_amount,
				bank_amount=float(bank_row["settled_amount"]),
				confidence=0.85,
				strategy="many_to_one_batch_match",
				reason=f"{len(order_ids)} gateway transactions sum to the bank UTR after fee adjustment.",
			)
		)
		excluded_bank.add(utr)
		excluded_orders.update(order_ids)
		candidates = [item for item in candidates if item[0] not in excluded_orders]
	return matches


def run_deterministic_matching(
	gateway: pd.DataFrame,
	bank: pd.DataFrame,
	fee_rate: float = DEFAULT_FEE_RATE,
	tolerance: float | None = None,
	settlement_window: tuple[int, int] = DEFAULT_SETTLEMENT_WINDOW,
) -> list[Match]:
	"""Run Layer 1 strategies in the PRD-prescribed order."""
	matches = exact_match(gateway, bank, settlement_window)
	matched_orders = _unmatched_ids(gateway, matches)
	matched_utrs = {match.utr for match in matches}
	fee_matches = fee_adjusted_match(
		gateway,
		bank,
		fee_rate,
		tolerance,
		settlement_window,
		excluded_order_ids=set(gateway["order_id"]) - matched_orders,
		excluded_utrs=matched_utrs,
	)
	matches.extend(fee_matches)
	matched_orders = {order_id for match in matches for order_id in match.order_ids}
	matched_utrs = {match.utr for match in matches}
	matches.extend(
		many_to_one_batch_match(
			gateway,
			bank,
			fee_rate,
			tolerance,
			settlement_window,
			excluded_order_ids=matched_orders,
			excluded_utrs=matched_utrs,
		)
	)
	return matches
