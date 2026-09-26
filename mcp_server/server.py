#!/usr/bin/env python3
"""Garmin-Dashboard MCP-Server.

Liest AUSSCHLIESSLICH aus der lokalen SQLite-Datenbank (nie live von Garmin),
damit Claude im Chat ueber deine Daten sprechen kann, ohne zusaetzliche
Garmin-API-Aufrufe und damit ohne Rate-Limit-Risiko auszuloesen.

Voraussetzung: scripts/backfill.py bzw. scripts/sync_daily.py wurden bereits
mindestens einmal ausgefuehrt, damit Daten in der DB liegen.

In Claude Desktop/Code einbinden (siehe README fuer den genauen Config-Eintrag).
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from app import config, db
from app.report import build_daily_report

mcp = FastMCP("garmin-dashboard")

_NO_DATA = "keine Daten"


def _today() -> str:
    return dt.date.today().isoformat()


@mcp.tool()
def get_daily_summary(date: str | None = None) -> dict[str, Any]:
    """Tageswerte (Ruhepuls, HRV, Body Battery, Stress, Schritte, VO2max, ...) fuer ein Datum.

    date: YYYY-MM-DD, Standard: heute.
    """
    date = date or _today()
    with db.connect() as conn:
        row = db.fetch_one(conn, "daily_metrics", "date", date)
    if not row:
        return {"date": date, "status": _NO_DATA}
    row.pop("raw_json", None)
    return row


@mcp.tool()
def get_sleep(date: str | None = None) -> dict[str, Any]:
    """Schlafdaten (Dauer, Phasen, Score, Ein-/Aufwachzeit) fuer ein Datum.

    date: YYYY-MM-DD (Kalendertag des Aufwachens), Standard: heute.
    """
    date = date or _today()
    with db.connect() as conn:
        row = db.fetch_one(conn, "sleep", "date", date)
    if not row:
        return {"date": date, "status": _NO_DATA}
    row.pop("raw_json", None)
    return row


@mcp.tool()
def get_activities(date_from: str, date_to: str | None = None) -> list[dict[str, Any]]:
    """Aktivitaeten (Laufen, Radfahren, Kraft, ...) in einem Zeitraum.

    date_from / date_to: YYYY-MM-DD. date_to Standard: heute.
    """
    date_to = date_to or _today()
    with db.connect() as conn:
        rows = db.fetch_range(conn, "activities", "date", date_from, date_to, order_by="date, start_time_utc")
    for row in rows:
        row.pop("raw_json", None)
    return rows or [{"date_from": date_from, "date_to": date_to, "status": _NO_DATA}]


@mcp.tool()
def get_trend(metric: str, days: int = 28) -> list[dict[str, Any]]:
    """Verlauf einer Kennzahl aus daily_metrics ueber die letzten N Tage.

    metric: Spaltenname, z.B. 'resting_hr', 'hrv_avg_ms', 'vo2max_running', 'steps'.
    """
    valid_columns = {
        "resting_hr", "hrv_avg_ms", "hrv_status", "body_battery_max", "body_battery_min",
        "stress_avg", "respiration_avg", "spo2_avg", "steps", "vo2max_running",
        "vo2max_cycling", "training_readiness_score", "weight_kg",
    }
    if metric not in valid_columns:
        return [{"error": f"Unbekannte Kennzahl '{metric}'. Erlaubt: {sorted(valid_columns)}"}]

    date_to = dt.date.today()
    date_from = date_to - dt.timedelta(days=days - 1)
    with db.connect() as conn:
        cur = conn.execute(
            f"SELECT date, {metric} FROM daily_metrics WHERE date BETWEEN ? AND ? ORDER BY date",
            (date_from.isoformat(), date_to.isoformat()),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return rows or [{"status": _NO_DATA}]


@mcp.tool()
def get_race_predictions(date: str | None = None) -> dict[str, Any]:
    """Garmins Wettkampfprognosen (5km/10km/Halbmarathon/Marathon) fuer ein Datum.

    date: YYYY-MM-DD, Standard: heute.
    """
    date = date or _today()
    with db.connect() as conn:
        row = db.fetch_one(conn, "race_predictions", "date", date)
    if not row:
        return {"date": date, "status": _NO_DATA}
    row.pop("raw_json", None)
    return row


@mcp.tool()
def get_computed_report(date: str | None = None) -> dict[str, Any]:
    """Berechnete Kennzahlen fuer ein Datum: Recovery-Score (+ Ampel und
    Teilbewertungen), Strain (0-21), CTL/ATL/TSB, ACWR, Schlafbedarf fuer
    heute Nacht mit Zubettgehzeit-Empfehlung, Trainingsempfehlung fuer den
    Tag und ein vorsichtiger Ueberlastungs-Hinweis.

    Reine lokale Berechnung aus der Datenbank (siehe app/metrics.py und
    app/metrics_config.py fuer die Formeln und einstellbaren Gewichtungen) -
    kein Garmin-API-Aufruf.

    date: YYYY-MM-DD, Standard: heute.
    """
    target = dt.date.fromisoformat(date) if date else dt.date.today()
    with db.connect() as conn:
        return build_daily_report(conn, target)


@mcp.tool()
def get_last_sync_status() -> dict[str, Any]:
    """Wann der letzte Sync lief und ob er erfolgreich war."""
    with db.connect() as conn:
        cur = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
    if not row:
        return {"status": "noch nie synchronisiert"}
    return dict(row)


if __name__ == "__main__":
    db.init_db(config.DASHBOARD_DB_PATH)
    mcp.run(transport="stdio")
