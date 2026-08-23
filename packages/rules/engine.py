"""Categorization rules engine — deterministic, explainable, review-queue aware."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from packages.ledger.engine import Ledger


class RulesEngine:
    def __init__(self, rules_path: str | Path | None = None):
        self.rules_path = Path(rules_path or Path(__file__).parent / "default_rules.yaml")
        cfg = yaml.safe_load(self.rules_path.read_text(encoding="utf-8"))
        self.rules = cfg.get("rules", [])
        self.review_threshold = float(cfg.get("review_threshold", 0.6))
        self.fallback_category = cfg.get("uncategorized_category", "Uncategorized")
        # precompile regexes
        for rule in self.rules:
            rule["_patterns"] = [re.compile(p, re.IGNORECASE) for p in rule.get("match_any", [])]

    def classify(self, raw_description: str) -> tuple[str | None, float]:
        """Return (category_name|None, confidence). None = no rule matched."""
        desc = raw_description.lower()
        for rule in self.rules:
            for pat in rule["_patterns"]:
                if pat.search(desc):
                    return rule["category"], float(rule.get("confidence", 0.5))
        return None, 0.0

    def classify_with_merchant(self, raw_description: str) -> tuple[str | None, str | None, float]:
        """Return (category_name, canonical_merchant, confidence)."""
        desc = raw_description.lower()
        for rule in self.rules:
            for pat, pattern_src in zip(rule["_patterns"], rule["match_any"]):
                if pat.search(desc):
                    return rule["category"], pattern_src.title(), float(rule.get("confidence", 0.5))
        return None, None, 0.0

    def apply_to_ledger(self, ledger: Ledger) -> dict:
        """Classify all uncategorized transactions; route low confidence to review queue."""
        rows = ledger.conn.execute(
            """SELECT id, raw_description FROM transactions
               WHERE category_id IS NULL ORDER BY txn_date"""
        ).fetchall()
        stats = {"categorized": 0, "review": 0, "uncategorized": 0}
        cat_cache: dict[str, int] = {}

        def cat_id(name: str) -> int:
            if name not in cat_cache:
                cat_cache[name] = ledger.ensure_category(name)
            return cat_cache[name]

        for row in rows:
            category, merchant, confidence = self.classify_with_merchant(row["raw_description"])
            if merchant is not None:
                mid = ledger.ensure_merchant(merchant, alias=row["raw_description"][:80])
                ledger.conn.execute(
                    "UPDATE transactions SET merchant_id=? WHERE id=?",
                    (mid, row["id"]),
                )
                ledger.conn.commit()
            if category is None:
                # no rule hit — leave uncategorized but flag new merchants for review
                ledger.set_category(
                    row["id"], cat_id(self.fallback_category), 0.0,
                    review_reason="low_confidence",
                )
                stats["review"] += 1
            elif confidence < self.review_threshold:
                ledger.set_category(row["id"], cat_id(category), confidence,
                                    review_reason="low_confidence")
                stats["review"] += 1
            else:
                ledger.set_category(row["id"], cat_id(category), confidence)
                stats["categorized"] += 1
        stats["total"] = len(rows)
        return stats
