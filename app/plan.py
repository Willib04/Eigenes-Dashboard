"""Periodisierter Trainingsplan (Phase 4).

Erzeugt einen einfachen, transparenten Schaerfungs-/Taper-Plan fuer ein
kurzfristiges 5-km-Ziel (3-4 Wochen, siehe app/plan_config.py). Kein
automatisches Senden an Garmin - das passiert ausschliesslich ueber
send_workout_to_garmin(), das nur durch einen expliziten Klick im
Dashboard aufgerufen wird.

Die Wochenvorlagen sind bewusst als einfache, lesbare Datenstrukturen
gehalten (kein Regel-Engine-Overkill) - bei einem 3-4-Wochen-Sharpening-Block
gibt es nur eine Handvoll sinnvoller Wochentypen (Schaerfung, Entlastung,
Taper), keine komplexe Mesozyklen-Logik wie bei einem Halbjahresplan.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

from app import plan_config as pc
from app.report import _load_activities_by_date


def _format_pace(seconds_per_km: float) -> str:
    minutes = int(seconds_per_km // 60)
    seconds = int(round(seconds_per_km % 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"


def goal_paces(goal_time_seconds: float, goal_distance_m: float) -> dict[str, str]:
    """Richtwerte fuer Zielpace, Intervallpace (etwas schneller) und
    Schwellenpace (etwas langsamer) - grobe Faustregeln aus der Lauf-
    Trainingslehre, keine individuelle Laktatmessung."""
    race_pace_s = goal_time_seconds / (goal_distance_m / 1000)
    return {
        "race": _format_pace(race_pace_s),
        "interval": _format_pace(race_pace_s * 0.97),
        "threshold": _format_pace(race_pace_s * 1.06),
    }


def _week_schaerfung_1(paces: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"weekday": 2, "type": "intervals", "title": "Intervalle",
         "description": f"Einlaufen 15 min locker, dann 6x400m im Zielpace ({paces['interval']} min/km) "
                         "mit 2 min Trabpause, danach 10 min Auslaufen.",
         "duration_min": 45},
        {"weekday": 3, "type": "easy", "title": "Locker (30 min)",
         "description": "30 min locker laufen, Zone 2, du solltest dich locker unterhalten koennen.",
         "duration_min": 30},
        {"weekday": 4, "type": "easy", "title": "Locker + Steigerungen",
         "description": "40 min locker, am Ende 4x20 Sekunden lockere Steigerungen (nicht voll).",
         "duration_min": 40},
        {"weekday": 5, "type": "tempo", "title": "Schwellenlauf",
         "description": f"15 min Einlaufen, 20 min im Schwellentempo (~{paces['threshold']} min/km), "
                         "10 min Auslaufen.",
         "duration_min": 45},
        {"weekday": 6, "type": "strength", "title": "Krafttraining",
         "description": "30-40 min laufspezifisches Krafttraining: Rumpf, Beine, Stabilisation.",
         "duration_min": 35},
        {"weekday": 7, "type": "long", "title": "Langer lockerer Lauf",
         "description": "60-70 min locker, die letzten 10 Minuten etwas zuegiger.",
         "duration_min": 65},
    ]


def _week_schaerfung_2(paces: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"weekday": 2, "type": "intervals", "title": "Intervalle",
         "description": f"Einlaufen 15 min locker, dann 8x400m im Zielpace ({paces['interval']} min/km) "
                         "mit 90 Sekunden Trabpause, danach 10 min Auslaufen.",
         "duration_min": 45},
        {"weekday": 3, "type": "easy", "title": "Locker (30 min)",
         "description": "30 min locker laufen, Zone 2.",
         "duration_min": 30},
        {"weekday": 4, "type": "easy", "title": "Locker + Steigerungen",
         "description": "35 min locker, am Ende 4x20 Sekunden Steigerungen im Zielpace-Gefuehl.",
         "duration_min": 35},
        {"weekday": 5, "type": "tempo", "title": "Schwellenlauf",
         "description": f"15 min Einlaufen, 25 min im Schwellentempo (~{paces['threshold']} min/km), "
                         "10 min Auslaufen.",
         "duration_min": 50},
        {"weekday": 6, "type": "strength", "title": "Krafttraining",
         "description": "30 min laufspezifisches Krafttraining, etwas reduziert.",
         "duration_min": 30},
        {"weekday": 7, "type": "long", "title": "Langer Lauf mit Tempoanteilen",
         "description": f"60 min: 40 min locker + 15 min im Zielpace ({paces['race']} min/km) + 5 min Auslaufen.",
         "duration_min": 60},
    ]


def _week_entlastung(paces: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"weekday": 2, "type": "intervals", "title": "Kurze Intervalle",
         "description": f"Einlaufen 10 min, dann 4x300m im Zielpace ({paces['interval']} min/km) mit "
                         "viel Pause - Umfang bewusst klein.",
         "duration_min": 30},
        {"weekday": 3, "type": "easy", "title": "Ganz locker (30 min)",
         "description": "30 min ganz locker - bei roter Recovery lieber ausfallen lassen.",
         "duration_min": 30},
        {"weekday": 4, "type": "easy", "title": "Locker (30 min)",
         "description": "30 min locker, entspanntes Tempo.",
         "duration_min": 30},
        {"weekday": 5, "type": "tempo", "title": "Kurzer Tempoabschnitt",
         "description": f"10 min Einlaufen, 12 min im Schwellentempo (~{paces['threshold']} min/km), "
                         "8 min Auslaufen.",
         "duration_min": 30},
        {"weekday": 6, "type": "strength", "title": "Leichtes Krafttraining",
         "description": "20 min lockere Rumpfstabilisation, keine schweren Gewichte.",
         "duration_min": 20},
        {"weekday": 7, "type": "easy", "title": "Locker (40 min)",
         "description": "40 min locker, entspannt.",
         "duration_min": 40},
    ]


def _week_taper(paces: dict[str, str], goal_time_seconds: float, goal_distance_m: float) -> list[dict[str, Any]]:
    goal_minutes = int(goal_time_seconds // 60)
    goal_seconds = int(goal_time_seconds % 60)
    distance_km = goal_distance_m / 1000
    return [
        {"weekday": 2, "type": "easy", "title": "Aktivierung",
         "description": f"20 min locker + 3-4x20 Sekunden zuegig im Zielpace-Gefuehl ({paces['race']} min/km) "
                         "- Beine wach halten, keine Ermuedung.",
         "duration_min": 20},
        {"weekday": 3, "type": "rest", "title": "Ganz locker oder Pause",
         "description": "20-30 min ganz locker oder komplette Pause - je nachdem, wie du dich fuehlst.",
         "duration_min": 20},
        {"weekday": 4, "type": "easy", "title": "Kurze Steigerungen",
         "description": "20 min locker + 3x15 Sekunden Steigerungen.",
         "duration_min": 20},
        {"weekday": 5, "type": "rest", "title": "Ruhetag",
         "description": "Komplette Pause - Erholung vor dem Wettkampf.",
         "duration_min": None},
        {"weekday": 6, "type": "easy", "title": "Aktivierung vor dem Wettkampf",
         "description": "15-20 min ganz locker + 2-3 kurze zuegige Antritte.",
         "duration_min": 20},
        {"weekday": 7, "type": "race", "title": "Wettkampf/Zeitfahren",
         "description": (
             f"{distance_km:.0f} km Zeitfahren oder Wettkampf - Ziel: unter "
             f"{goal_minutes}:{goal_seconds:02d} Minuten (Zielpace {paces['race']} min/km). "
             "Gutes Einlaufen (15-20 min locker + ein paar Steigerungen), dann volle Kraft."
         ),
         "duration_min": None, "distance_m": goal_distance_m},
    ]


def _phase_for_week(week_index: int, total_weeks: int) -> str:
    if week_index == total_weeks - 1:
        return "taper"
    if week_index == total_weeks - 2:
        return "entlastung"
    return "schaerfung"


def _select_week_workouts(
    week_index: int, phase: str, paces: dict[str, str], goal_time_seconds: float, goal_distance_m: float
) -> list[dict[str, Any]]:
    if phase == "taper":
        return _week_taper(paces, goal_time_seconds, goal_distance_m)
    if phase == "entlastung":
        return _week_entlastung(paces)
    # "schaerfung": erste Schaerfungswoche etwas moderater als jede weitere
    if week_index == 0:
        return _week_schaerfung_1(paces)
    return _week_schaerfung_2(paces)


def generate_plan(
    conn: sqlite3.Connection,
    start_date: dt.date | None = None,
    goal_weeks: int | None = None,
    goal_distance_m: float | None = None,
    goal_time_seconds: float | None = None,
) -> int:
    """Erstellt einen neuen aktiven Plan. Ein vorher aktiver Plan wird auf
    inaktiv gesetzt (nicht geloescht - bleibt fuer die Historie erhalten).
    Legt keine Eintraege in der Vergangenheit an. Gibt die neue plan_id zurueck.
    """
    today = start_date or dt.date.today()
    goal_weeks = goal_weeks or pc.GOAL_WEEKS
    goal_distance_m = goal_distance_m or pc.GOAL_DISTANCE_M
    goal_time_seconds = goal_time_seconds or pc.GOAL_TIME_SECONDS
    paces = goal_paces(goal_time_seconds, goal_distance_m)

    monday = today - dt.timedelta(days=today.isoweekday() - 1)
    goal_date = monday + dt.timedelta(days=goal_weeks * 7 - 1)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    conn.execute("UPDATE training_plan SET is_active = 0 WHERE is_active = 1")
    cur = conn.execute(
        "INSERT INTO training_plan (created_at, start_date, goal_date, goal_distance_m, goal_time_seconds, is_active) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (now_iso, monday.isoformat(), goal_date.isoformat(), goal_distance_m, goal_time_seconds),
    )
    plan_id = cur.lastrowid

    for week_index in range(goal_weeks):
        phase = _phase_for_week(week_index, goal_weeks)
        workouts = _select_week_workouts(week_index, phase, paces, goal_time_seconds, goal_distance_m)
        week_monday = monday + dt.timedelta(days=week_index * 7)
        for workout in workouts:
            workout_date = week_monday + dt.timedelta(days=workout["weekday"] - 1)
            if workout_date < today:
                continue
            conn.execute(
                "INSERT INTO planned_workouts (plan_id, date, week_number, phase, workout_type, title, "
                "description, target_duration_minutes, target_distance_m, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plan_id,
                    workout_date.isoformat(),
                    week_index,
                    phase,
                    workout["type"],
                    workout["title"],
                    workout["description"],
                    workout.get("duration_min"),
                    workout.get("distance_m"),
                    now_iso,
                ),
            )
    return plan_id


def get_active_plan(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM training_plan WHERE is_active = 1 ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _is_fulfilled(workout: dict[str, Any], activities_that_day: list[dict[str, Any]]) -> bool:
    wtype = workout["workout_type"]
    if wtype in ("rest",):
        return True
    if wtype == "strength":
        return any("strength" in (a.get("activity_type") or "").lower() for a in activities_that_day)
    return any("running" in (a.get("activity_type") or "").lower() for a in activities_that_day)


def plan_with_status(
    conn: sqlite3.Connection, plan_id: int, today: dt.date | None = None
) -> list[dict[str, Any]]:
    """Alle geplanten Workouts eines Plans, angereichert um den Soll/Ist-Status
    ('erledigt', 'verpasst', 'heute', 'geplant') durch Abgleich mit den echten
    synchronisierten Aktivitaeten am selben Tag.
    """
    today = today or dt.date.today()
    rows = conn.execute(
        "SELECT * FROM planned_workouts WHERE plan_id = ? ORDER BY date", (plan_id,)
    ).fetchall()
    workouts = [dict(r) for r in rows]
    if not workouts:
        return []

    dates = sorted({w["date"] for w in workouts})
    activities_by_date = _load_activities_by_date(conn, dates)

    for w in workouts:
        w_date = dt.date.fromisoformat(w["date"])
        if _is_fulfilled(w, activities_by_date.get(w["date"], [])):
            w["status"] = "erledigt"
        elif w_date < today:
            w["status"] = "verpasst"
        elif w_date == today:
            w["status"] = "heute"
        else:
            w["status"] = "geplant"
    return workouts


def weekly_fulfillment(
    conn: sqlite3.Connection, plan_id: int, today: dt.date | None = None
) -> list[dict[str, Any]]:
    """Erfuellungsquote pro Trainingswoche (Ruhetage zaehlen nicht mit)."""
    workouts = plan_with_status(conn, plan_id, today)
    weeks: dict[int, dict[str, Any]] = {}
    for w in workouts:
        if w["workout_type"] == "rest":
            continue
        week = weeks.setdefault(
            w["week_number"], {"week_number": w["week_number"], "phase": w["phase"], "geplant": 0, "erledigt": 0}
        )
        week["geplant"] += 1
        if w["status"] == "erledigt":
            week["erledigt"] += 1

    result = []
    for week_number in sorted(weeks):
        week = weeks[week_number]
        week["quote_prozent"] = round(100 * week["erledigt"] / week["geplant"]) if week["geplant"] else None
        result.append(week)
    return result


def today_workout_with_override(
    conn: sqlite3.Connection, recovery_ampel: str, today: dt.date | None = None
) -> dict[str, Any] | None:
    """Der heutige geplante Workout, ergaenzt um einen Alternativ-Hinweis, falls
    die Recovery heute rot ist. Der Plan selbst wird dabei NICHT veraendert."""
    today = today or dt.date.today()
    plan = get_active_plan(conn)
    if not plan:
        return None

    workouts = plan_with_status(conn, plan["id"], today)
    todays = [w for w in workouts if w["date"] == today.isoformat()]
    if not todays:
        return None

    workout = dict(todays[0])
    if recovery_ampel == "rot" and workout["workout_type"] not in ("rest", "easy"):
        workout["alternative_wegen_recovery"] = (
            "Deine Recovery ist heute rot - statt der geplanten Einheit empfehlen wir nur "
            "lockere Bewegung oder eine Pause. Die geplante Einheit bleibt im Kalender stehen, "
            "du kannst sie bei Bedarf auf einen anderen Tag verschieben."
        )
    return workout


# ---------------------------------------------------------------------------
# Garmin-Workout-Upload - NUR ueber einen expliziten Klick im Dashboard,
# nie automatisch. Konnte nicht gegen einen echten Garmin-Account getestet
# werden (kein Testzugang verfuegbar) - erst mit einer unkritischen Einheit
# ausprobieren und in der Garmin-Connect-App gegenchecken.
# ---------------------------------------------------------------------------


def build_running_workout(workout_row: dict[str, Any]):
    from garminconnect.workout import (
        RunningWorkout,
        WorkoutSegment,
        create_cooldown_step,
        create_interval_step,
        create_warmup_step,
    )

    duration_min = workout_row.get("target_duration_minutes") or 30
    total_seconds = int(duration_min * 60)
    warmup_s = 300 if total_seconds > 900 else 0
    cooldown_s = 300 if total_seconds > 900 else 0
    main_s = max(60, total_seconds - warmup_s - cooldown_s)

    steps = []
    order = 1
    if warmup_s:
        steps.append(create_warmup_step(warmup_s, order))
        order += 1
    steps.append(create_interval_step(main_s, order))
    order += 1
    if cooldown_s:
        steps.append(create_cooldown_step(cooldown_s, order))

    return RunningWorkout(
        workoutName=workout_row["title"][:60],
        estimatedDurationInSecs=total_seconds,
        description=workout_row["description"][:500],
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 1, "sportTypeKey": "running"},
                workoutSteps=steps,
            )
        ],
    )


def send_workout_to_garmin(conn: sqlite3.Connection, garmin: Any, workout_id: int) -> dict[str, Any]:
    """Sendet EINEN geplanten Workout an Garmin Connect.

    `garmin` ist eine eingeloggte garminconnect.Garmin-Instanz (kein
    RateLimitedGarmin-Wrapper) - Fehler sollen hier NICHT stillschweigend
    verschluckt werden, damit ein Upload-Fehler im Dashboard sichtbar wird
    statt so auszusehen, als waere alles gut gegangen.
    """
    row = conn.execute("SELECT * FROM planned_workouts WHERE id = ?", (workout_id,)).fetchone()
    if not row:
        raise ValueError(f"Kein geplanter Workout mit id={workout_id} gefunden")
    row = dict(row)
    if row["workout_type"] in ("rest",):
        raise ValueError("Ruhetage koennen nicht als Workout gesendet werden")

    workout = build_running_workout(row)
    uploaded = garmin.upload_running_workout(workout)
    garmin_workout_id = uploaded.get("workoutId") or uploaded.get("id") if isinstance(uploaded, dict) else None

    if garmin_workout_id is not None:
        garmin.schedule_workout(garmin_workout_id, row["date"])

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    conn.execute(
        "UPDATE planned_workouts SET sent_to_garmin_at = ?, garmin_workout_id = ? WHERE id = ?",
        (now_iso, str(garmin_workout_id) if garmin_workout_id is not None else None, workout_id),
    )
    return {"garmin_workout_id": garmin_workout_id, "scheduled_date": row["date"]}
