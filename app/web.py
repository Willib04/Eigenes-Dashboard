"""FastAPI-Backend fuer das Dashboard (Phase 5).

Liefert eine JSON-API fuer den taeglichen Bericht (reine Lesefunktion aus
der lokalen DB, kein Garmin-API-Zugriff - beliebig oft aufrufbar/reload-bar)
und die statische Frontend-Seite unter web/.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app import db, metrics_config as mc
from app.report import build_daily_report

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Eigenes Dashboard")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/api/report")
def api_report(date: str | None = None) -> dict:
    try:
        target = dt.date.fromisoformat(date) if date else dt.date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Datum muss im Format YYYY-MM-DD sein")

    with db.connect() as conn:
        return build_daily_report(conn, target)


@app.get("/api/config")
def api_config() -> dict:
    """Konfigurationswerte, die das Frontend fuer die Info-Texte braucht."""
    return {
        "recovery_weights": mc.RECOVERY_WEIGHTS,
        "recovery_green_min": mc.RECOVERY_GREEN_MIN,
        "recovery_yellow_min": mc.RECOVERY_YELLOW_MIN,
        "hf_max": mc.HF_MAX,
        "strain_scale_max": mc.STRAIN_SCALE_MAX,
        "acwr_high_warning": mc.ACWR_HIGH_WARNING,
        "acwr_low_hint": mc.ACWR_LOW_HINT,
        "base_sleep_need_hours": mc.BASE_SLEEP_NEED_HOURS,
    }


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")
