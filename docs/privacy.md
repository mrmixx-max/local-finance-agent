# Datenschutz-Modell

## Grundprinzipien

1. **Lokal by default.** Alle Daten liegen in einer SQLite-Datei auf deiner Maschine.
2. **Kein Netzwerkverkehr** außer einem explizit konfigurierten Ollama-Endpoint (ab 0.2).
3. **Keine Telemetrie.** Es gibt keinen Code, der nach Hause telefoniert.
4. **Kein Account.** Keine Registrierung, keine Kennung, nichts.

## Wo deine Daten liegen

| Daten | Ort | Git? |
|---|---|---|
| Ledger-Datenbank | `data/db/ledger.db` (konfigurierbar via `LFA_DB_PATH`) | nein (`*.db` in `.gitignore`) |
| Rohe CSVs | wo immer du sie hinlegst; der Pfad wird nur als Provenance-Eintrag gespeichert | nein |
| Reports | `data/processed/` | nein |
| Demo-Daten | `examples/synthetic-ledger/` | ja (synthetisch, keine echten Beträge) |

## Was beim Import gespeichert wird

- Transaktionsdatum, Betrag (Integer Cents), Rohbeschreibung
- SHA256 der Quelldatei (Provenance) — **nicht die Datei selbst**
- Kanonischer Merchant + Kategorie + Confidence

## Threat Model (Kurzfassung)

| Bedrohung | Mitigation |
|---|---|
| Ledger-Datei wird gestohlen | Dateisystemverschlüsselung nutzen (BitLocker/LUKS); optionale DB-Verschlüsselung ist Roadmap (packages/security) |
| Accidental commit echter Finanzdaten | `.gitignore` blockt `*.db` und `data/raw/*`; Secret-Scan vor Push |
| Dashboard aus dem Netz erreichbar | Server bindet ausschließlich auf 127.0.0.1 |
| Prompt-Injection über Bankbeschreibungen (ab 0.2 relevant) | LLM sieht nur Redaction-Layer-Auszug; Antworten müssen auf Ledger-Zeilen verweisen (AnswerTrace) |

## Cloud-Routing (ab 0.2)

Standardmäßig aus. Wenn aktiviert, gilt:

- Nur der Redaction-Layer-Auszug geht raus — nie Rohdaten oder vollständige Beschreibungen.
- Jede Cloud-Anfrage wird im Log mit Zielmodell markiert.
- Ein Schalter genügt, um dauerhaft offline zu bleiben.
