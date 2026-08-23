# Architektur

## Schichten

```text
Input Layer      CSV-Dateien, manuelle Eingaben (0.1) · PDFs/Belege (0.3)
Processing Layer Parsing, Feld-Mapping, Betrags-Normalisierung, Dedup, Merchant-Mapping
Storage Layer    SQLite (data/db/ledger.db), integer cents, Provenance-Spalten
Agent Layer      Recurring-Detector, Report-Generator (Q&A-Agent ab 0.2 über Ollama)
Interface Layer  CLI (packages/cli.py), FastAPI + Single-File-Dashboard
```

## Datenmodell

| Tabelle | Zweck |
|---|---|
| `accounts` | Konten (checking/credit/cash) |
| `transactions` | Kernobjekt: Datum, Betrag in Cents, Rohbeschreibung, Merchant, Kategorie, **Confidence**, `dedup_hash` (UNIQUE) |
| `merchants` | Kanonische Händlernamen + Alias-Liste (JSON) |
| `categories` | Hierarchische Kategorien |
| `documents` | Importierte Dateien mit SHA256 — jede Transaktion zeigt auf ihr Quelldokument |
| `review_items` | Buchungen mit niedriger Confidence, mit Grund (`low_confidence`, `new_merchant`, `ambiguous`) |
| `recurring_patterns` | Erkannte Wiederkehrmuster (abgeleitet; Detector ist stateless, Tabelle für 0.2+ Caching) |
| `answer_traces` | Frage → Antwort → verwendete Filter + Ledger-Zeilen (Provenance, ab 0.2 befüllt) |

## Deduplizierung

Deterministisch: SHA256 über `account | date | amount_cents | normalized_description`.
Die Beschreibungs-Normalisierung entfernt Referenznummern und eingebettete Daten,
damit Bankrauschen den Hash nicht bricht. Re-Imports derselben Datei sind idempotent.

## Kategorisierung

Regelbasiert (YAML): Regex-Matches auf die Rohbeschreibung → Kategorie + Confidence.
Unter `review_threshold` (Default 0.6) landet die Buchung in der Review-Queue statt
stillschweigend falsch kategorisiert zu werden. Kein LLM im Pfad — deterministisch
und nachvollziehbar. LLM-Assist kommt in 0.2 als *Vorschlag* mit Confidence,
nicht als Auto-Write.

## Recurring-Detector

Stateless-Heuristik pro Merchant:
1. ≥ N Outflows (Default 3)
2. ≥ 85 % der Beträge innerhalb ±15 % des Medians
3. Median-Intervall zwischen 5 und 400 Tagen
4. ≥ 60 % der Abstände innerhalb ±5 Tagen des Medians

Output: typischer Betrag, Intervall, Regularity-Score, geschätzte Monatskosten.

## Warum SQLite zuerst

Single-File, zero-config, transaktional, überall verfügbar. DuckDB kommt als
optionales Analyse-Backend in 0.4, wenn Zeitreihen-Aggregationen über Jahre groß
werden — das Schema bleibt identisch.
