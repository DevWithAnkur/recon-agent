import csv
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


SEED = 42
TOTAL_RECORDS = 400
FEE_RATE = 0.02
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

GATEWAY_FIELDS = [
	"order_id",
	"amount",
	"currency",
	"status",
	"created_at",
	"merchant_id",
]
BANK_FIELDS = ["utr", "settled_amount", "settlement_date", "batch_reference"]
LEDGER_FIELDS = [
	"ledger_entry_id",
	"recorded_amount",
	"recorded_date",
	"order_id_ref",
]
MAPPING_FIELDS = ["order_id", "correct_utr", "is_resolvable", "expected_reason_code"]


def money(value: float) -> str:
	return f"{value:.2f}"


def settlement_amount(amount: float, fee_rate: float = FEE_RATE) -> float:
	return round(amount - (amount * fee_rate), 2)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
	with path.open("w", newline="", encoding="utf-8") as file_handle:
		writer = csv.DictWriter(file_handle, fieldnames=fields)
		writer.writeheader()
		writer.writerows(rows)


def build_dataset() -> tuple[
	list[dict[str, str]],
	list[dict[str, str]],
	list[dict[str, str]],
	list[dict[str, str]],
]:
	random.seed(SEED)
	gateway_rows: list[dict[str, str]] = []
	bank_rows: list[dict[str, str]] = []
	ledger_rows: list[dict[str, str]] = []
	mapping_rows: list[dict[str, str]] = []
	cohort_labels: list[str] = []
	start_date = date(2026, 1, 1)

	def add_gateway(
		index: int,
		cohort: str,
		amount: float,
		status: str = "success",
		currency: str = "INR",
	) -> tuple[str, date]:
		order_id = f"ORD_{index:05d}"
		created_at = start_date + timedelta(days=random.randrange(30))
		merchant_id = f"MERCHANT_{random.randrange(1, 6):03d}"
		gateway_rows.append(
			{
				"order_id": order_id,
				"amount": money(amount),
				"currency": currency,
				"status": status,
				"created_at": created_at.isoformat(),
				"merchant_id": merchant_id,
			}
		)
		ledger_rows.append(
			{
				"ledger_entry_id": f"LEDGER_{index:05d}",
				"recorded_amount": money(amount),
				"recorded_date": created_at.isoformat(),
				"order_id_ref": order_id,
			}
		)
		cohort_labels.append(cohort)
		return order_id, created_at

	def add_mapping(
		order_id: str,
		correct_utr: str,
		is_resolvable: bool,
		expected_reason_code: str = "",
	) -> None:
		mapping_rows.append(
			{
				"order_id": order_id,
				"correct_utr": correct_utr,
				"is_resolvable": str(is_resolvable).lower(),
				"expected_reason_code": expected_reason_code,
			}
		)

	next_index = 1

	for _ in range(196):
		amount = float(random.randint(500, 100000))
		order_id, created_at = add_gateway(next_index, "clean", amount)
		utr = f"UTR_{next_index:06d}"
		bank_rows.append(
			{
				"utr": utr,
				"settled_amount": money(amount),
				"settlement_date": (created_at + timedelta(days=random.randint(0, 2))).isoformat(),
				"batch_reference": order_id,
			}
		)
		add_mapping(order_id, utr, True)
		next_index += 1

	for _ in range(84):
		amount = float(random.randint(500, 100000))
		order_id, created_at = add_gateway(next_index, "clean", amount)
		utr = f"UTR_{next_index:06d}"
		bank_rows.append(
			{
				"utr": utr,
				"settled_amount": money(settlement_amount(amount)),
				"settlement_date": (created_at + timedelta(days=random.randint(0, 2))).isoformat(),
				"batch_reference": order_id,
			}
		)
		add_mapping(order_id, utr, True)
		next_index += 1

	batch_count = 12
	for batch_number in range(1, batch_count + 1):
		batch_reference = f"BATCH_{batch_number:03d}"
		batch_amount = 0.0
		batch_orders: list[str] = []
		batch_dates: list[date] = []
		for _ in range(5):
			amount = float(random.randint(500, 100000))
			order_id, created_at = add_gateway(next_index, "batch", amount)
			batch_orders.append(order_id)
			batch_dates.append(created_at)
			batch_amount += settlement_amount(amount)
			next_index += 1
		utr = f"UTR_BATCH_{batch_number:03d}"
		bank_rows.append(
			{
				"utr": utr,
				"settled_amount": money(batch_amount),
				"settlement_date": (max(batch_dates) + timedelta(days=1)).isoformat(),
				"batch_reference": batch_reference,
			}
		)
		for order_id in batch_orders:
			add_mapping(order_id, utr, True)

	for edge_number in range(1, 41):
		amount = float(random.randint(500, 100000))
		order_id, created_at = add_gateway(next_index, "edge", amount)
		utr = f"UTR_EDGE_{edge_number:03d}"
		fee_rate = 0.0 if edge_number <= 20 else 0.025
		bank_rows.append(
			{
				"utr": utr,
				"settled_amount": money(settlement_amount(amount, fee_rate)),
				"settlement_date": (created_at + timedelta(days=random.randint(0, 2))).isoformat(),
				"batch_reference": order_id,
			}
		)
		add_mapping(order_id, utr, True)
		next_index += 1

	for broken_number in range(1, 21):
		amount = float(random.randint(500, 100000))
		if broken_number <= 8:
			cohort = "broken_missing_settlement"
			reason_code = "missing_settlement"
			status = "success"
		elif broken_number <= 12:
			cohort = "broken_duplicate_entry"
			reason_code = "duplicate_entry"
			status = "success"
		elif broken_number <= 16:
			cohort = "broken_refund"
			reason_code = "refund_not_netted"
			status = "refund"
		else:
			cohort = "broken_currency"
			reason_code = "currency_rounding"
			status = "success"
		currency = "USD" if cohort == "broken_currency" else "INR"
		order_id, created_at = add_gateway(next_index, cohort, amount, status, currency)

		if cohort == "broken_duplicate_entry":
			for duplicate_number in range(2):
				bank_rows.append(
					{
						"utr": f"UTR_DUP_{broken_number:03d}_{duplicate_number + 1}",
						"settled_amount": money(settlement_amount(amount)),
						"settlement_date": (created_at + timedelta(days=1)).isoformat(),
						"batch_reference": order_id,
					}
				)
		elif cohort == "broken_refund":
			bank_rows.append(
				{
					"utr": f"UTR_REFUND_{broken_number:03d}",
					"settled_amount": money(settlement_amount(amount)),
					"settlement_date": (created_at + timedelta(days=1)).isoformat(),
					"batch_reference": order_id,
				}
			)
		elif cohort == "broken_currency":
			bank_rows.append(
				{
					"utr": f"UTR_CURRENCY_{broken_number:03d}",
					"settled_amount": money(settlement_amount(amount)),
					"settlement_date": (created_at + timedelta(days=1)).isoformat(),
					"batch_reference": order_id,
				}
			)
		add_mapping(order_id, "", False, reason_code)
		next_index += 1

	distribution = Counter(cohort_labels)
	expected_distribution = {
		"clean": 280,
		"batch": 60,
		"edge": 40,
		"broken_missing_settlement": 8,
		"broken_duplicate_entry": 4,
		"broken_refund": 4,
		"broken_currency": 4,
	}
	assert distribution == expected_distribution
	assert len(gateway_rows) == TOTAL_RECORDS
	assert len(mapping_rows) == TOTAL_RECORDS
	return gateway_rows, bank_rows, ledger_rows, mapping_rows


def main() -> None:
	DATA_DIR.mkdir(parents=True, exist_ok=True)
	gateway_rows, bank_rows, ledger_rows, mapping_rows = build_dataset()
	write_csv(DATA_DIR / "gateway.csv", GATEWAY_FIELDS, gateway_rows)
	write_csv(DATA_DIR / "bank_settlement.csv", BANK_FIELDS, bank_rows)
	write_csv(DATA_DIR / "merchant_ledger.csv", LEDGER_FIELDS, ledger_rows)
	write_csv(DATA_DIR / "batch_mapping.csv", MAPPING_FIELDS, mapping_rows)
	print(f"Generated {len(gateway_rows)} gateway records in {DATA_DIR}")
	print("Distribution: 70% clean, 15% many-to-one batches, 10% edge cases, 5% broken records")


if __name__ == "__main__":
	main()
