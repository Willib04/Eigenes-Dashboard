"""FastAPI-Backend fuer das Dashboard (Phase 5).

Liefert eine JSON-API fuer den taeglichen Bericht (reine Lesefunktion aus
der lokalen DB, kein Garmin-API-Zugriff - beliebig oft aufrufbar/reload-bar)
und die statische Frontend-Seite unter web/.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import chat, db, plan
from app import metrics_config as mc
from app import plan_config as pc
from app.report import build_daily_report, build_load_history, build_trends

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
logger = logging.getLogger(__name__)

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


@app.get("/api/trends")
def api_trends(weeks: int = 12) -> dict:
    if weeks not in (4, 12, 26, 52):
        raise HTTPException(status_code=400, detail="weeks muss 4, 12, 26 oder 52 sein")
    with db.connect() as conn:
        return build_trends(conn, weeks=weeks)


@app.get("/api/history")
def api_history(days: int = 90) -> list[dict]:
    if not 7 <= days <= 365:
        raise HTTPException(status_code=400, detail="days muss zwischen 7 und 365 liegen")
    with db.connect() as conn:
        return build_load_history(conn, days=days)


@app.get("/api/activities")
def api_activities(days: int = 30) -> list[dict]:
    date_to = dt.date.today()
    date_from = date_to - dt.timedelta(days=days - 1)
    with db.connect() as conn:
        rows = db.fetch_range(conn, "activities", "date", date_from.isoformat(), date_to.isoformat(),
                               order_by="date DESC, start_time_utc DESC")
    for row in rows:
        row.pop("raw_json", None)
    return rows


# --- Trainingsplan (Phase 4) ------------------------------------------------


class GeneratePlanRequest(BaseModel):
    goal_weeks: int | None = None
    goal_time_seconds: float | None = None
    goal_distance_m: float | None = None


@app.get("/api/plan")
def api_plan() -> dict:
    with db.connect() as conn:
        active = plan.get_active_plan(conn)
        if not active:
            return {"plan": None, "workouts": [], "weekly_fulfillment": []}
        workouts = plan.plan_with_status(conn, active["id"])
        fulfillment = plan.weekly_fulfillment(conn, active["id"])
    return {"plan": active, "workouts": workouts, "weekly_fulfillment": fulfillment}


@app.post("/api/plan/generate")
def api_plan_generate(body: GeneratePlanRequest) -> dict:
    with db.connect() as conn:
        plan_id = plan.generate_plan(
            conn,
            goal_weeks=body.goal_weeks,
            goal_time_seconds=body.goal_time_seconds,
            goal_distance_m=body.goal_distance_m,
        )
        active = plan.get_active_plan(conn)
        workouts = plan.plan_with_status(conn, plan_id)
    return {"plan": active, "workouts": workouts}


@app.get("/api/plan/today")
def api_plan_today() -> dict:
    today = dt.date.today()
    with db.connect() as conn:
        report = build_daily_report(conn, today)
        entry = plan.today_workout_with_override(conn, report["recovery_ampel"], today)
    return {"workout": entry, "recovery_ampel": report["recovery_ampel"]}


@app.post("/api/plan/workouts/{workout_id}/send-to-garmin")
def api_send_to_garmin(workout_id: int) -> dict:
    from app.garmin_client import GarminAuthError, GarminRateLimitError, login

    try:
        garmin = login()
    except GarminRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except GarminAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    try:
        with db.connect() as conn:
            result = plan.send_workout_to_garmin(conn, garmin, workout_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - Upload-Fehler muessen sichtbar werden, nicht verschluckt
        logger.exception("Garmin-Workout-Upload fehlgeschlagen")
        raise HTTPException(status_code=502, detail=f"Garmin-Upload fehlgeschlagen: {exc}") from exc

    return result


@app.get("/api/plan_config")
def api_plan_config() -> dict:
    return {
        "goal_distance_m": pc.GOAL_DISTANCE_M,
        "goal_time_seconds": pc.GOAL_TIME_SECONDS,
        "goal_weeks": pc.GOAL_WEEKS,
    }


# --- Chat (Claude API) ------------------------------------------------------


class ChatRequest(BaseModel):
    message: str


class ApplyChangesRequest(BaseModel):
    aenderungen: list[dict]


@app.get("/api/chat/status")
def api_chat_status() -> dict:
    from app import config

    return {"konfiguriert": bool(config.ANTHROPIC_API_KEY)}


@app.post("/api/chat")
def api_chat(body: ChatRequest) -> dict:
    today = dt.date.today()
    with db.connect() as conn:
        report = build_daily_report(conn, today)
        active = plan.get_active_plan(conn)
        workouts = plan.plan_with_status(conn, active["id"]) if active else []

    try:
        return chat.ask_coach(body.message, report, workouts)
    except chat.ChatNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - Chat-Fehler muessen sichtbar werden
        logger.exception("Chat-Anfrage fehlgeschlagen")
        raise HTTPException(status_code=502, detail=f"Chat-Anfrage fehlgeschlagen: {exc}") from exc


@app.post("/api/chat/apply")
def api_chat_apply(body: ApplyChangesRequest) -> dict:
    with db.connect() as conn:
        active = plan.get_active_plan(conn)
        if not active:
            raise HTTPException(status_code=400, detail="Kein aktiver Trainingsplan vorhanden")
        applied = chat.apply_changes(conn, active["id"], body.aenderungen)
        workouts = plan.plan_with_status(conn, active["id"])
    return {"applied": applied, "workouts": workouts}


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")
