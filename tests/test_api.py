"""API smoke tests via FastAPI TestClient."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["LFA_DB_PATH"] = str(Path(__file__).parent / "_api_test.db")

from fastapi.testclient import TestClient

from apps.api.main import app


@pytest.fixture()
def client(tmp_path):
    os.environ["LFA_DB_PATH"] = str(tmp_path / "api_test.db")
    # rebind the module-level DB constant (bound at import time)
    import apps.api.main as api_main
    api_main.DB = os.environ["LFA_DB_PATH"]
    return TestClient(app)


def test_health(client):
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_demo_flow(client):
    assert client.post("/api/demo-data").status_code == 200

    now = client.get("/api/healthz")  # ensure server works post-import
    assert now.status_code == 200

    import datetime
    today = datetime.date.today()
    s = client.get(f"/api/summary/{today.year}/{today.month}")
    assert s.status_code == 200
    body = s.json()
    assert "total_inflow" in body and "net" in body

    rec = client.get("/api/recurring").json()["items"]
    assert isinstance(rec, list) and len(rec) > 0

    rep = client.get(f"/api/report/{today.year}/{today.month}")
    assert rep.status_code == 200
    assert "Monatsbericht" in rep.json()["markdown"]


def test_summary_bad_month(client):
    assert client.get("/api/summary/2026/13").status_code == 400


def test_import_missing_file(client):
    r = client.post("/api/import", json={"path": "Z:/nope/missing.csv"})
    assert r.status_code == 404
