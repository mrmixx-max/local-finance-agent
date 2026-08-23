# Roadmap

## 0.1 — Core Ledger ✅ (dieser Stand)

- [x] CSV-Importer (DE/EN Formate, Fehler-Toleranz)
- [x] SQLite-Ledger mit Provenance
- [x] Deduplizierung (deterministisch, idempotent)
- [x] Rules Engine + Review Queue
- [x] Recurring-Cost-Detector
- [x] Monatsreport (Markdown) + CSV-Export
- [x] FastAPI-Dashboard (127.0.0.1)
- [x] Synthetischer Demo-Datensatz
- [x] Test-Suite (18 Tests)

## 0.2 — AI Query Layer

- [ ] Ollama-Provider-Abstraktion (`packages/models`)
- [ ] Tool-basiertes Q&A: Fragen → deterministische SQL/Query-Ausführung → Antwort mit Belegen
- [ ] AnswerTrace befüllen (Frage → Filter → Ledger-Zeilen → Antwort)
- [ ] Merchant-Vorschläge via LLM (Confidence < Regel-Matches, immer nur Vorschlag)
- [ ] Optionaler Cloud-Fallback mit Redaction-Layer + explizitem Opt-in

## 0.3 — Real World Documents

- [ ] PDF-Statement-Parsing (Interface in `packages/parsers`)
- [ ] Receipt OCR (Tesseract lokal)
- [ ] Anomaly Detection (Ausreißer, Sprünge)
- [ ] Transfers zwischen eigenen Konten erkennen und neutralisieren

## 0.4 — Ecosystem

- [ ] Region Packs: Deutschland/EU (Kategorie-Konventionen, Exportformate)
- [ ] Freelancer-Modus (USt-relevante Flags, Belegzuordnung)
- [ ] DuckDB als optionales Analyse-Backend
- [ ] MCP-Server für Agent-Ökosystem-Zugriff (read-only default)

## Offene Entscheidungen

- **Lizenz**: MIT vs. Apache-2.0 vs. GPL — vor dem ersten Public-Release klären.
- **UI-Framework** fürs Dashboard jenseits der Single-File-Version.
- Namensrechtlichkeit "Local Finance Agent" prüfen vor Public-Launch.
