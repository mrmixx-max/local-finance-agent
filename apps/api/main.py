"""FastAPI backend — local-only by default (binds 127.0.0.1).

Run: uvicorn apps.api.main:app --host 127.0.0.1 --port 8321
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from packages.agents.recurring import detect_recurring
from packages.demo import generate as generate_demo
from packages.ingest.csv_import import import_csv
from packages.ledger.engine import Ledger
from packages.reports.monthly import export_month_csv, fmt_eur, monthly_report
from packages.rules.engine import RulesEngine

app = FastAPI(title="Local Finance Agent", version="0.1.0")
DB = os.environ.get("LFA_DB_PATH", "./data/db/ledger.db")


def get_ledger() -> Ledger:
    return Ledger(DB)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")


class ImportRequest(BaseModel):
    path: str
    account: str | None = None


@app.post("/api/import")
def api_import(req: ImportRequest):
    p = Path(req.path)
    if not p.exists():
        raise HTTPException(404, f"File not found: {p}")
    ledger = get_ledger()
    report = import_csv(ledger, p, req.account)
    rules = RulesEngine()
    report["categorization"] = rules.apply_to_ledger(ledger)
    report["recurring_found"] = len(detect_recurring(ledger))
    return report


@app.post("/api/demo-data")
def api_demo():
    csv_path = "./examples/synthetic-ledger/demo_statement.csv"
    generate_demo(csv_path)
    return api_import(ImportRequest(path=csv_path, account="Demo-Konto"))


@app.get("/api/summary/{year}/{month}")
def api_summary(year: int, month: int):
    if not 1 <= month <= 12:
        raise HTTPException(400, "month must be 1-12")
    ledger = get_ledger()
    s = ledger.month_summary(year, month)
    s["total_inflow"] = fmt_eur(s["total_inflow_cents"])
    s["total_outflow"] = fmt_eur(s["total_outflow_cents"])
    s["net"] = fmt_eur(s["net_cents"])
    return s


@app.get("/api/recurring")
def api_recurring():
    return {"items": detect_recurring(get_ledger())}


@app.get("/api/review")
def api_review():
    return {"items": [dict(r) for r in get_ledger().pending_review()]}


@app.get("/api/report/{year}/{month}")
def api_report(year: int, month: int):
    ledger = get_ledger()
    md = monthly_report(ledger, year, month, detect_recurring(ledger))
    csv_out = export_month_csv(
        ledger, year, month,
        f"./data/processed/report-{year}-{month:02d}.csv",
    )
    return {"markdown": md, "csv_path": str(csv_out)}


@app.get("/api/report/{year}/{month}/download", response_class=FileResponse)
def api_report_download(year: int, month: int):
    path = Path(f"./data/processed/report-{year}-{month:02d}.csv")
    if not path.exists():
        raise HTTPException(404, "Report not generated yet — call /api/report first.")
    return FileResponse(path, filename=path.name, media_type="text/csv")


@app.get("/api/healthz")
def health():
    return {"status": "ok", "db": DB}
