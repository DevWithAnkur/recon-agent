# Recon-Agent: AI Finance Controller

**Razorpay AI Buildathon - Track 04 (AI Finance Controller)**

Recon-Agent is a hybrid financial reconciliation engine designed to solve the "Verification vs. Generation" bottleneck. Instead of throwing an LLM at an entire dataset, Recon-Agent uses a deterministic Pandas engine to process standard matches, routing only highly ambiguous edge cases to a strictly validated LLM layer.

In financial infrastructure, safety is paramount. Recon-Agent is intentionally designed to be ruthlessly conservative: it optimizes for **Precision** over Recall, ensuring that uncertain matches are safely routed to a human exception queue rather than hallucinated.

## Performance Metrics (Ground Truth Evaluation)

| Metric               | Score                            | Impact                                                                                     |
| -------------------- | --------------------------------- | ------------------------------------------------------------------------------------------ |
| **Precision**        | **0.92**                         | 92% accuracy on positive matches, reducing the risk of silently misallocating funds.       |
| **Recall**           | **0.85**                         | Fee-adjusted and batch matches now correctly resolve in Layer 1 instead of falling through.|
| **F1 Score**         | **0.88**                         | Balance of automation and financial safety.                                                |
| **Confusion Matrix** | **TP: 322 \| FP: 28 \| FN: 58**  | Ground-truth evaluation across the synthetic dataset.                                      |

**Baseline vs. current:** the original flat fee-tolerance logic scored Precision 0.96 / Recall 0.79 / F1 0.87 (TP:300 FP:12 FN:80). Switching to a percentage-based fee tolerance (`FEE_TOLERANCE_PCT = 0.025`) recovered 22 false negatives but introduced 16 new false positives, trading some precision for meaningfully higher recall. F1 held roughly flat (+0.01), and this tradeoff is being actively tightened — see Known Limitations.

**Layer breakdown (current dataset):** 350/400 records (87.5%) resolved in Layer 1 — 216 exact matches, 127 fee-adjusted matches, 2 many-to-one batch groups (covering the remainder). 50 records escalated to the LLM layer; 0 cleared the 0.85 confidence threshold, so all 50 correctly became exceptions rather than being force-matched.

## Architecture

```text
gateway.csv + bank_settlement.csv + merchant_ledger.csv
						 |
						 v
	   Layer 1: Deterministic Matching Engine
	   Pandas exact, fee-adjusted, and batch matching
						 |
		  unresolved or low-confidence records
						 v
	   Layer 2: LLM Reasoning Layer
	   OpenAI gpt-5.4-mini + Pydantic Structured Outputs
						 |
						 v
	   Layer 3: Exception Classifier
	   Conservative reason codes and human review queue
						 |
						 v
	   Layer 4: Audit, Reporting, and Webhooks
	   JSONL audit trail, batch summary, optional Discord alerts
```

### Layer 1: Deterministic Engine

The Pandas-based engine runs first and does not require an LLM. It applies these strategies in order:

1. **Exact match**: Matches order reference, amount, and settlement date within the expected T+0 to T+2 window. Confidence is `1.0`.
2. **Fee-adjusted match**: Matches the expected settlement amount after the configurable default 2% fee, within a configurable tolerance. Confidence is `0.9`.
3. **Many-to-one batch match**: Finds groups of gateway transactions whose fee-adjusted values sum to one bank UTR. Confidence is `0.85`.

### Layer 2: LLM Resolver

Only unresolved records reach the LLM layer. The resolver:

- Uses OpenAI `gpt-5.4-mini`.
- Selects the three closest bank or ledger candidates by amount proximity.
- Uses `client.responses.parse` with a strict Pydantic schema.
- Requires `match_found`, `matched_entry_id`, `confidence`, `reasoning`, and `discrepancy_amount`.
- Uses a 15-second client timeout with one retry.
- Never commits a match below the `0.85` confidence threshold.

### Layer 3: Exception Classification

Any unresolved or below-threshold record becomes an exception rather than a guessed match. Exceptions include:

- `missing_settlement`
- `fee_calculation_mismatch`
- `duplicate_entry`
- `currency_rounding`
- `refund_not_netted`
- `timing_gap`

Each exception retains its record ID, reason code, human-readable explanation, confidence at failure, and candidates considered.

**System Resilience:** If the OpenAI API times out or fails mid-batch, the system safely downgrades. Instead of crashing, it routes all remaining unresolved records directly to the Layer 3 JSONL exception queue for human review.

### Layer 4: Audit and Notifications

The reporting layer writes one JSON object per line to `output/audit_log.jsonl` for every match and exception. Each event includes its resolution, resolving layer, confidence, reasoning, and supporting evidence. Optional Discord webhook notifications can report exceptions, selected successful matches, and the final batch summary.

## Sample Output (Exception Log)

```json
{
	"timestamp": "2026-09-04T22:10:00Z",
	"record_id": "ORD_00388",
	"status": "EXCEPTION",
	"reason": "LLM Confidence Threshold Missed",
	"details": {
		"gateway_amount": 1050.00,
		"bank_amount": 1020.50,
		"discrepancy_pct": 0.028
	},
	"action_required": "Human Review"
}
```

## Project Structure

```text
recon-agent/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── data/
│   ├── gateway.csv              # Gateway transaction records
│   ├── bank_settlement.csv      # Bank settlement and UTR records
│   ├── merchant_ledger.csv      # Merchant ledger records
│   └── batch_mapping.csv        # Ground truth used only for evaluation
├── scripts/
│   ├── generate_synthetic_data.py
│   └── run_eval.py               # Precision, recall, and F1 harness
├── src/
│   ├── cli.py                    # Pipeline entry point
│   ├── matching/
│   │   ├── deterministic.py      # Layer 1
│   │   ├── llm_resolver.py       # Layer 2
│   │   └── exceptions.py         # Layer 3
│   └── reporting/
│       ├── audit.py              # Layer 4 audit log and report
│       └── webhook.py            # Layer 4 Discord notifications
├── tests/
│   ├── conftest.py
│   ├── test_exact_match.py
│   ├── test_fee_variance.py
│   ├── test_date_mismatch_fails.py
│   ├── test_many_to_one_batch.py
│   ├── test_ambiguous_goes_to_exception.py
│   └── test_dry_run_no_commit.py
└── output/
	└── audit_log.jsonl           # Generated at runtime and gitignored
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and add credentials locally:

```dotenv
OPENAI_API_KEY=your_api_key_here
DISCORD_WEBHOOK_URL=
```

Never commit `.env` or API keys. Webhook notifications are optional; the pipeline continues without a configured webhook.

### 3. Generate synthetic data

```bash
python scripts/generate_synthetic_data.py
```

The generator uses a fixed seed and produces 400 records distributed as:

- 70% clean one-to-one matches
- 15% many-to-one batches
- 10% partial settlement and fee edge cases
- 5% genuinely broken records

### 4. Run the pipeline in dry-run mode

```bash
python -m src.cli reconcile --gateway data/gateway.csv --bank data/bank_settlement.csv --ledger data/merchant_ledger.csv --dry-run
```

Dry-run executes reconciliation, exception classification, and reporting, but does not write `output/audit_log.jsonl` or commit any records.

### 5. Run a committed reconciliation

```bash
python -m src.cli reconcile --gateway data/gateway.csv --bank data/bank_settlement.csv --ledger data/merchant_ledger.csv
```

Useful overrides:

```text
--fee-rate 0.02
--confidence-threshold 0.85
--no-webhook
```

### 6. Run tests

```bash
pytest tests/ -v
```

### 7. Run the evaluation harness

```bash
python scripts/run_eval.py
```

The evaluation compares predicted UTRs with `data/batch_mapping.csv` and prints the confusion matrix, precision, recall, and F1 score.

## Safety and Design Principles

- Deterministic matching is preferred wherever evidence is sufficient.
- The LLM is used only for residual ambiguous cases.
- Structured outputs prevent unvalidated free-form model responses from entering the pipeline.
- Confidence thresholds prevent low-confidence matches from being silently committed.
- Every decision carries evidence and reasoning in the audit trail.
- Dry-run mode allows finance operations teams to preview a batch safely.
- Unresolved records are visible exceptions, not hidden guesses.

## Security & Data Privacy

Environment variables and API keys are strictly scoped locally via `.env`. To prevent financial data leakage, the Layer 2 LLM resolver only receives sanitized numerical amounts, date deltas, and internal UUIDs. No Personally Identifiable Information (PII) or raw webhook payloads are ever transmitted to third-party AI endpoints.

## Known Limitations

- Version 1 assumes INR and does not provide full multi-currency reconciliation.
- The LLM fallback depends on OpenAI availability and API latency.
- Many-to-one matching is bounded to combinations of up to 20 gateway transactions. This ≤20 transaction bound is not a performance limitation, but a deliberate risk boundary designed to prevent unbounded recursion and runaway compute costs on heavily fragmented ledgers.
- Fee handling currently uses a flat 2.5% percentage tolerance rather than a tiered or capped schedule; this recovers more true matches but has increased false positives, and is a planned area for refinement (e.g., capping absolute tolerance for large-value batches).
- The generated dataset is synthetic; real bank statement formats and production integrations are out of scope.
- Webhook delivery depends on the configured Discord endpoint and network availability.

## What I Would Build Next

- Multi-currency support with explicit exchange-rate and currency validation.
- A fee-tier lookup table for merchant-specific and volume-based schedules.
- Parsers for real bank statement formats and settlement file variants.
- A production dashboard for batch summaries, exception review, and audit exploration.

## Roadmap to Production: Razorpay Integration

**Handling Domain-Specific Quirks:** While this prototype evaluates synthetic flat-fee ledgers, the modular Layer 1 engine is designed to scale into Razorpay's actual settlement mechanics, specifically handling multi-UTR batch patterns, partial captures, and refund-linked adjustments.

**Constrained Agentic Depth:** In financial ledgers, unbounded agentic reasoning is a compliance liability. Layer 2 operates strictly as a routing and evaluation agent to prevent hallucinated mutations. Future iterations will introduce deterministic Tool-Calling, allowing the agent to query external banking APIs for missing context without mutating the state autonomously.

## Author

**Ankur Verma**
ankur.theconqueror@gmail.com