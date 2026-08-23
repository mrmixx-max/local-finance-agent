# Local Finance Agent

A privacy-first, local-first AI finance copilot.

Import bank statements, categorize transactions, detect recurring costs,
ask questions about your money, and generate monthly reports — all on your
machine by default.

No account required.
No telemetry by default.
Optional cloud routing only when explicitly enabled (Milestone 0.2).

## Features (v0.1.0 — Core Ledger)

- **CSV import** with auto column-mapping (German & English exports), German/English
  number formats, per-row error recovery
- **Local ledger** on SQLite: accounts, merchants, categories, provenance per transaction
- **Deterministic deduplication** — re-importing the same statement changes nothing
- **Rules-based categorization** (YAML rules, editable) with confidence scores and a
  **review queue** for low-confidence matches
- **Recurring cost detection** — subscriptions and regular bills with interval,
  regularity score, and estimated monthly cost
- **Monthly reports** in Markdown + CSV export
- **Web dashboard** (FastAPI + single-file HTML, binds 127.0.0.1 only)
- **Synthetic demo ledger** for risk-free onboarding

## Schnellstart

```bash
# clone + install
git clone <repo-url> local-finance-agent && cd local-finance-agent
pip install -e ".[dev]"

# try it with synthetic demo data (no real money involved)
python -m packages.cli demo        # generates + imports 3 months of demo data
python -m packages.cli recurring    # shows detected subscriptions
python -m packages.cli report       # prints this month's report
```

Or start the dashboard:

```bash
uvicorn apps.api.main:app --host 127.0.0.1 --port 8321
# open http://127.0.0.1:8321 → click "Demo-Daten laden"
```

## Importing your own statements

Export a CSV from your bank (most German banks support this) and run:

```bash
python -m packages.cli import ./downloads/kontoauszug.csv --account Hauptkonto
python -m packages.cli categorize
```

Supported headers include: `Buchungsdatum/Datum/date`, `Betrag/Umsatz/amount`,
`Verwendungszweck/Buchungstext/description`. Amounts may use `1.234,56` or
`1,234.56` formats; minus signs, parentheses, and unicode minus are handled.
Rows that fail to parse are reported and skipped, not silently dropped.

## CLI reference

| Command | What it does |
|---|---|
| `lfa demo` | generate + import the synthetic ledger |
| `lfa import FILE [--account NAME]` | import a CSV statement |
| `lfa categorize` | apply category rules to uncategorized transactions |
| `lfa recurring` | list detected recurring costs |
| `lfa report [YEAR MONTH]` | print a monthly report (default: current month) |
| `lfa review` | show transactions awaiting review |

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Purpose |
|---|---|---|
| `LFA_DB_PATH` | `./data/db/ledger.db` | where the SQLite ledger lives |
| `OLLAMA_BASE_URL` | *(unset = offline)* | LLM endpoint (Milestone 0.2) |

## Architecture

```text
CSV / manual input
      ↓
Ingestion (parse, normalize, dedup)
      ↓
SQLite Ledger ← Rules Engine (categories, confidence, review queue)
      ↓
Agents: Recurring · Reports · (Q&A in 0.2)
      ↓
CLI / FastAPI Dashboard / CSV+MD Reports
```

See `docs/architecture.md` for details and `docs/privacy.md` for the data-handling model.

## Adding categorization rules

Edit `packages/rules/default_rules.yaml` (or point a custom file at `RulesEngine`):

```yaml
rules:
  - category: Groceries
    match_any: [rewe, edeka, aldi]
    confidence: 0.9
review_threshold: 0.6     # below this → review queue
```

## Market module (descriptive analytics)

Track a portfolio and compute descriptive statistics — **no predictions,
no signals, no recommendations**, by explicit scope decision.

```bash
python -m packages.market_cli demo            # sample portfolio + 1y synthetic prices
python -m packages.market_cli import-prices prices.csv IWDA   # CSV with [date,close]
python -m packages.market_cli add-position IWDA 12.5 82.40
python -m packages.market_cli portfolio       # value, cost, P/L per position
python -m packages.market_cli vol BTC-EUR     # annualized volatility of past returns
```

Market data lives in its own SQLite file (`LFA_MARKET_DB`, default
`data/db/market.db`) — it never mixes with the transaction ledger.
A test (`test_scope_guard_no_prediction_api`) enforces that the module
surface stays free of prediction/recommendation functions.

## Tests

```bash
pytest tests/ -q
```

Covers: amount/date parsing (DE+EN formats), header mapping, dedup behavior,
rule classification, the full demo pipeline (import → categorize → recurring →
report), market module (positions, price upsert, volatility), and API smoke tests.

## Security

- The dashboard binds to `127.0.0.1` only — not reachable from your network.
- `.env`, databases (`*.db`), and everything under `data/raw` are gitignored;
  real financial data should never be committed.
- No telemetry, no outbound calls except an explicitly configured Ollama endpoint.

## Roadmap

- **0.1 ✅ Core Ledger** — CSV import, SQLite, rules engine, monthly report
- **0.2 AI Query Layer** — Ollama integration, tool-based Q&A with answer provenance
- **0.3 Real World Documents** — PDF statements, receipt OCR, anomaly detection
- **0.4 Ecosystem** — region packs (DE/EU), freelancer mode, MCP server

## Contributing

Parser contributions and region packs are the most valuable contributions.
Open an issue describing your bank's CSV format (with redacted sample rows)
before submitting a parser PR.

## License

Not yet decided — see `docs/roadmap.md`. Until a license is added, all rights reserved.

## Grenzen (read before trusting it)

This is a bookkeeping aid, not financial advice. Categorization is rule-based
and can be wrong; the review queue exists precisely because of that. Amounts
are stored as integer cents; no rounding magic. Bank-specific quirks (booking
dates vs. value dates, chargebacks, partial refunds) are not yet modeled.
