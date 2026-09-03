from __future__ import annotations

import os
from typing import Any

import requests

from src.matching.deterministic import Match
from src.matching.exceptions import ExceptionRecord


def send_webhook(message: str, webhook_url: str | None = None, timeout: float = 10.0) -> bool:
	"""Send one Discord-compatible webhook message, skipping cleanly when unset."""
	url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
	if not url:
		return False
	response = requests.post(url, json={"content": message}, timeout=timeout)
	response.raise_for_status()
	return True


def notify_exception(exception: ExceptionRecord, webhook_url: str | None = None) -> bool:
	message = (
		f"Exception Flagged: Order #{exception.record_id} - "
		f"{exception.human_readable_reason} Reason: {exception.reason_code}. "
		"Escalated for human review."
	)
	return send_webhook(message, webhook_url)


def notify_match(match: Match, webhook_url: str | None = None) -> bool:
	order_label = ", ".join(match.order_ids)
	message = (
		f"Matched: Order #{order_label} <-> UTR {match.utr} "
		f"(confidence: {match.confidence:.2f}, resolved by: {match.strategy})"
	)
	return send_webhook(message, webhook_url)


def notify_summary(report: dict[str, Any], webhook_url: str | None = None) -> bool:
	message = (
		f"Batch complete: {report['match_rate']:.1%} matched "
		f"(Layer 1: {report['layer_1_matched'] / report['total_records']:.1%}, "
		f"Layer 2: {report['layer_2_matched'] / report['total_records']:.1%}), "
		f"{report['exceptions'] / report['total_records']:.1%} exceptions."
		if report["total_records"]
		else "Batch complete: no records processed."
	)
	return send_webhook(message, webhook_url)
