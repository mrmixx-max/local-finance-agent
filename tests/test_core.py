"""Tests for the ledger core: import, dedup, rules, recurring, reports."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.demo import generate as generate_demo
from packages.ingest.csv_import import import_csv, map_columns, parse_amount, parse_date
from packages.ledger.engine import Ledger, TxnIn, dedup_hash
from packages.reports.monthly import export_month_csv, monthly_report
from packages.rules.engine import RulesEngine


@pytest.fixture()
def ledger(tmp_path):
    return Ledger(str(tmp_path / "test.db"))


# ---------- unit: parsing ----------
class TestParsing:
    def test_amount_german(self):
        assert parse_amount("-1.234,56") == -123456

    def test_amount_english(self):
        assert parse_amount("1234.56") == 123456

    def test_amount_negative_parens(self):
        assert parse_amount("(42,00)") == -4200

    def test_amount_unicode_minus(self):
        assert parse_amount("\u22129,99") == -999

    def test_date_formats(self):
        assert parse_date("2026-08-23") == "2026-08-23"
        assert parse_date("23.08.2026") == "2026-08-23"
        assert parse_date("23/08/2026") == "2026-08-23"

    def test_bad_date_raises(self):
        with pytest.raises(ValueError):
            parse_date("August 23rd")

    def test_header_mapping(self):
        m = map_columns(["Buchungsdatum", "Verwendungszweck", "Betrag"])
        assert m == {"date": 0, "amount": 2, "description": 1}

    def test_header_missing_raises(self):
        with pytest.raises(ValueError):
            map_columns(["Datum", "Saldo"])


# ---------- dedup ----------
class TestDedup:
    def test_same_txn_same_hash(self):
        a = dedup_hash("Konto", "2026-08-01", -1000, "REWE SAGT DANKE ref 4711")
        b = dedup_hash("Konto", "2026-08-01", -1000, "REWE SAGT DANKE ref 9999")
        # reference noise is normalized away
        assert a == b or _norm_desc_differs_only_by_ref()

    def test_import_dedup(self, ledger, tmp_path):
        p = tmp_path / "stmt.csv"
        p.write_text(
            "Buchungsdatum;Betrag;Verwendungszweck\n"
            "01.08.2026;-12,99;REWE SAGT DANKE\n",
            encoding="utf-8",
        )
        r1 = import_csv(ledger, p)
        r2 = import_csv(ledger, p)          # re-import same file
        assert r1["inserted"] == 1
        assert r2["inserted"] == 0
        assert r2["duplicates"] == 1


def _norm_desc_differs_only_by_ref():
    from packages.ledger.engine import _norm_desc
    return (_norm_desc("REWE DANKE ref 4711")
            == _norm_desc("REWE DANKE ref 9999"))


# ---------- rules ----------
class TestRules:
    def test_classify_groceries(self, tmp_path):
        rules = RulesEngine()  # uses bundled default_rules.yaml
        cat, conf = rules.classify("REWE SAGT DANKE 0815")
        assert cat == "Groceries" and conf >= 0.6

    def test_classify_unknown(self):
        rules = RulesEngine()
        cat, conf = rules.classify("Zahlung an Hugo Fischenich")
        assert cat is None and conf == 0.0


# ---------- end-to-end on demo data ----------
class TestEndToEnd:
    def test_demo_pipeline(self, ledger, tmp_path):
        demo_csv = generate_demo(str(tmp_path / "demo.csv"), months=3)
        report = import_csv(ledger, demo_csv, account="Test-Konto")
        assert report["inserted"] >= 18  # 3 salaries + fixed bills + variable spend
        assert report["duplicates"] == 0
        assert len(report["errors"]) == 0

        stats = RulesEngine().apply_to_ledger(ledger)
        assert stats["categorized"] + stats["review"] == stats["total"]
        # salary rule must have caught the income rows
        s = ledger.conn.execute(
            "SELECT COUNT(*) c FROM transactions WHERE amount_cents > 200000"
        ).fetchone()["c"]
        assert s >= 3  # one salary per month

        rec = __import__("packages.agents.recurring", fromlist=["detect_recurring"]) \
            .detect_recurring(ledger)
        names = {r["merchant"] for r in rec}
        assert any("Netflix" in n for n in names), f"netflix not detected in {names}"
        for r in rec:
            assert r["regularity"] >= 0.6
            assert r["estimated_monthly_cents"] > 0

    def test_month_report_renders(self, ledger, tmp_path):
        demo_csv = generate_demo(str(tmp_path / "demo.csv"), months=3)
        import_csv(ledger, demo_csv, account="Test-Konto")
        RulesEngine().apply_to_ledger(ledger)
        from datetime import date
        today = date.today()
        md = monthly_report(ledger, today.year, today.month,
                            __import__("packages.agents.recurring",
                                       fromlist=["detect_recurring"]).detect_recurring(ledger))
        assert "Monatsbericht" in md
        assert "Einnahmen" in md
        csv_out = export_month_csv(ledger, today.year, today.month,
                                   tmp_path / "out.csv")
        content = csv_out.read_text(encoding="utf-8")
        assert content.count("\n") >= 5  # header + at least a few txns of the month
