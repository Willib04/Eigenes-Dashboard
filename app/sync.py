"""Holt Garmin-Daten fuer einen Zeitraum und schreibt sie in die lokale SQLite-DB.

Wichtig: Wenn ein erwarteter Schluessel in der Garmin-Antwort fehlt, wird das
Feld NULL ("keine Daten") statt geraten. Die komplette Rohantwort landet
zusaetzlich in raw_json, damit spaeter nichts verloren geht, falls sich das
Mapping unten mal als unvollstaendig herausstellt.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
from typing import Any

from app import config, db
from app.garmin_client import RateLimitedGarmin

logger = logging.getLogger(__name__)


def _get(d: Any, *path: str) -> Any:
    """Liest verschachtelte dict-Pfade, gibt None zurueck statt zu werfen."""
    current = d
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _date_range(date_from: dt.date, date_to: dt.date) -> list[dt.date]:
    days = (date_to - date_from).days
    return [date_from + dt.timedelta(days=i) for i in range(days + 1)]


# ---------------------------------------------------------------------------
# Mapping: eine Funktion pro Garmin-Endpunkt -> DB-Zeile
# ---------------------------------------------------------------------------


def map_daily_metrics(date_str: str, stats: dict | None, hrv: dict | None,
                       training_readiness: Any, training_status: dict | None,
                       weight_kg: float | None) -> dict:
    hrv_summary = _get(hrv, "hrvSummary") or {}
    baseline = _get(hrv_summary, "baseline") or {}

    tr = training_readiness
    if isinstance(tr, list):
        tr = tr[0] if tr else None
    tr = tr or {}

    vo2max = _get(training_status, "mostRecentVO2Max") or {}
    latest_status_devices = _get(training_status, "mostRecentTrainingStatus", "latestTrainingStatusData")
    training_status_phrase = _first_value_field(latest_status_devices, "trainingStatusFeedbackPhrase")

    return {
        "date": date_str,
        "resting_hr": _get(stats, "restingHeartRate"),
        "hrv_avg_ms": _get(hrv_summary, "lastNightAvg"),
        "hrv_status": _get(hrv_summary, "status"),
        "hrv_weekly_avg_ms": _get(hrv_summary, "weeklyAvg"),
        "hrv_baseline_low_ms": _get(baseline, "balancedLow"),
        "hrv_baseline_high_ms": _get(baseline, "balancedUpper"),
        "body_battery_max": _get(stats, "bodyBatteryHighestValue"),
        "body_battery_min": _get(stats, "bodyBatteryLowestValue"),
        "body_battery_charged": _get(stats, "bodyBatteryChargedValue"),
        "body_battery_drained": _get(stats, "bodyBatteryDrainedValue"),
        "stress_avg": _get(stats, "averageStressLevel"),
        "stress_max": _get(stats, "maxStressLevel"),
        "respiration_avg": _get(stats, "avgWakingRespirationValue"),
        "respiration_sleep_avg": _get(stats, "avgSleepRespirationValue"),
        "spo2_avg": _get(stats, "averageSpo2"),
        "spo2_min": _get(stats, "lowestSpo2"),
        "steps": _get(stats, "totalSteps"),
        "intensity_minutes_moderate": _get(stats, "moderateIntensityMinutes"),
        "intensity_minutes_vigorous": _get(stats, "vigorousIntensityMinutes"),
        "vo2max_running": _get(vo2max, "generic", "vo2MaxValue"),
        "vo2max_cycling": _get(vo2max, "cycling", "vo2MaxValue"),
        "training_status": training_status_phrase,
        "training_readiness_score": _get(tr, "score"),
        "training_readiness_level": _get(tr, "level"),
        "weight_kg": weight_kg,
        "raw_json": json.dumps(
            {"stats": stats, "hrv": hrv, "training_readiness": training_readiness, "training_status": training_status}
        ),
        "synced_at": _now_iso(),
    }


def _first_value_field(devices_dict: Any, field: str) -> Any:
    if not isinstance(devices_dict, dict) or not devices_dict:
        return None
    first_device = next(iter(devices_dict.values()))
    return _get(first_device, field)


def map_sleep(date_str: str, sleep_data: dict | None) -> dict | None:
    if not sleep_data:
        return None
    daily = _get(sleep_data, "dailySleepDTO") or {}
    if not daily:
        return None

    scores = _get(daily, "sleepScores") or {}
    overall = _get(scores, "overall") or {}

    start_ms = _get(daily, "sleepStartTimestampGMT")
    end_ms = _get(daily, "sleepEndTimestampGMT")

    return {
        "date": date_str,
        "bedtime_utc": _ms_to_iso(start_ms),
        "wake_time_utc": _ms_to_iso(end_ms),
        "total_sleep_seconds": _get(daily, "sleepTimeSeconds"),
        "deep_sleep_seconds": _get(daily, "deepSleepSeconds"),
        "light_sleep_seconds": _get(daily, "lightSleepSeconds"),
        "rem_sleep_seconds": _get(daily, "remSleepSeconds"),
        "awake_seconds": _get(daily, "awakeSleepSeconds"),
        "sleep_score": _get(overall, "value"),
        "sleep_score_qualifier": _get(overall, "qualifierKey"),
        "avg_sleep_hrv_ms": _get(daily, "avgOvernightHrv"),
        "avg_sleep_stress": _get(daily, "avgSleepStress"),
        "respiration_avg_sleep": _get(sleep_data, "avgSleepRespirationValue"),
        "spo2_avg_sleep": _get(sleep_data, "averageSpO2Value"),
        "raw_json": json.dumps(sleep_data),
        "synced_at": _now_iso(),
    }


def _ms_to_iso(ms: Any) -> str | None:
    if ms is None:
        return None
    try:
        return dt.datetime.fromtimestamp(int(ms) / 1000, tz=dt.timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def map_activity(activity: dict) -> dict | None:
    activity_id = _get(activity, "activityId")
    if activity_id is None:
        return None

    start_local = _get(activity, "startTimeLocal") or _get(activity, "startTimeGMT")
    date_str = start_local.split(" ")[0].split("T")[0] if start_local else None
    if date_str is None:
        return None

    return {
        "activity_id": activity_id,
        "date": date_str,
        "start_time_utc": _get(activity, "startTimeGMT"),
        "activity_type": _get(activity, "activityType", "typeKey"),
        "name": _get(activity, "activityName"),
        "duration_seconds": _get(activity, "duration"),
        "distance_m": _get(activity, "distance"),
        "avg_hr": _get(activity, "averageHR"),
        "max_hr": _get(activity, "maxHR"),
        "avg_pace_min_per_km": _speed_to_pace(_get(activity, "averageSpeed")),
        "avg_power_w": _get(activity, "avgPower"),
        "normalized_power_w": _get(activity, "normPower"),
        "calories": _get(activity, "calories"),
        "elevation_gain_m": _get(activity, "elevationGain"),
        "training_effect_aerobic": _get(activity, "aerobicTrainingEffect"),
        "training_effect_anaerobic": _get(activity, "anaerobicTrainingEffect"),
        "training_load": _get(activity, "activityTrainingLoad"),
        "hr_zone_1_seconds": None,
        "hr_zone_2_seconds": None,
        "hr_zone_3_seconds": None,
        "hr_zone_4_seconds": None,
        "hr_zone_5_seconds": None,
        "raw_json": json.dumps(activity),
        "synced_at": _now_iso(),
    }


def _speed_to_pace(speed_m_per_s: float | None) -> float | None:
    """Wandelt m/s in min/km um. None, wenn Geschwindigkeit fehlt oder 0 ist."""
    if not speed_m_per_s:
        return None
    seconds_per_km = 1000 / speed_m_per_s
    return round(seconds_per_km / 60, 3)


def apply_hr_zones(row: dict, zones: list[dict] | None) -> dict:
    if not zones:
        return row
    for zone in zones:
        zone_number = _get(zone, "zoneNumber")
        seconds = _get(zone, "secsInZone")
        if zone_number in (1, 2, 3, 4, 5):
            row[f"hr_zone_{zone_number}_seconds"] = seconds
    return row


_RACE_PREDICTION_DATE_KEYS = ("calendarDate", "date", "fromCalendarDate")


def map_race_predictions(entry: dict | None) -> dict | None:
    """Wandelt einen einzelnen Eintrag aus get_race_predictions(..., _type='daily') um.

    Garmin liefert das Datum je nach Version unter leicht unterschiedlichen
    Schluesseln - wir probieren die bekannten Varianten durch, statt zu raten.
    """
    if not entry:
        return None

    date_str = None
    for key in _RACE_PREDICTION_DATE_KEYS:
        date_str = _get(entry, key)
        if date_str:
            break
    if not date_str:
        return None
    date_str = str(date_str).split("T")[0]

    return {
        "date": date_str,
        "time_5k_seconds": _get(entry, "time5K"),
        "time_10k_seconds": _get(entry, "time10K"),
        "time_half_marathon_seconds": _get(entry, "timeHalfMarathon"),
        "time_marathon_seconds": _get(entry, "timeMarathon"),
        "raw_json": json.dumps(entry),
        "synced_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Sync-Ablauf
# ---------------------------------------------------------------------------


def sync_day(conn: sqlite3.Connection, client: RateLimitedGarmin, date: dt.date) -> None:
    date_str = date.isoformat()

    stats = client.call("get_stats", date_str)
    hrv = client.call("get_hrv_data", date_str)
    training_readiness = client.call("get_training_readiness", date_str)
    training_status = client.call("get_training_status", date_str)
    sleep_data = client.call("get_sleep_data", date_str)

    weigh_ins = client.call("get_daily_weigh_ins", date_str)
    weight_kg = _extract_weight_kg(weigh_ins)

    daily_row = map_daily_metrics(date_str, stats, hrv, training_readiness, training_status, weight_kg)
    db.upsert(conn, "daily_metrics", daily_row, "date")

    sleep_row = map_sleep(date_str, sleep_data)
    if sleep_row:
        db.upsert(conn, "sleep", sleep_row, "date")


def _extract_weight_kg(weigh_ins: Any) -> float | None:
    entries = _get(weigh_ins, "dateWeightList") if isinstance(weigh_ins, dict) else None
    if not entries:
        return None
    weight_grams = _get(entries[0], "weight")
    if weight_grams is None:
        return None
    return round(weight_grams / 1000, 2)


def sync_activities(conn: sqlite3.Connection, client: RateLimitedGarmin, date_from: dt.date, date_to: dt.date) -> None:
    activities = client.call("get_activities_by_date", date_from.isoformat(), date_to.isoformat())
    if not activities:
        return

    for activity in activities:
        row = map_activity(activity)
        if row is None:
            continue
        zones = client.call("get_activity_hr_in_timezones", row["activity_id"])
        row = apply_hr_zones(row, zones)
        db.upsert(conn, "activities", row, "activity_id")


def _extract_race_prediction_entries(raw: Any) -> list[dict]:
    """Die Antwortform von get_race_predictions(_type='daily') ist nicht 100% dokumentiert -
    wir probieren die bekannten Formen durch statt anzunehmen, dass es immer eine Liste ist.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("racePredictions", "dailyRacePredictions", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
        if any(k in raw for k in ("time5K", "time10K", "timeHalfMarathon", "timeMarathon")):
            return [raw]
    return []


def sync_race_predictions(
    conn: sqlite3.Connection, client: RateLimitedGarmin, date_from: dt.date, date_to: dt.date
) -> None:
    """Ein einziger API-Aufruf fuer den ganzen Zeitraum statt einem pro Tag."""
    raw = client.call("get_race_predictions", date_from.isoformat(), date_to.isoformat(), "daily")
    for entry in _extract_race_prediction_entries(raw):
        row = map_race_predictions(entry)
        if row:
            db.upsert(conn, "race_predictions", row, "date")


def run_sync(client: RateLimitedGarmin, date_from: dt.date, date_to: dt.date, db_path=None) -> None:
    """Synct alle Tage im Bereich [date_from, date_to] (inklusive)."""
    started_at = _now_iso()
    with db.connect(db_path) as conn:
        log_id = conn.execute(
            "INSERT INTO sync_log (started_at, date_from, date_to, status) VALUES (?, ?, ?, 'running')",
            (started_at, date_from.isoformat(), date_to.isoformat()),
        ).lastrowid

    try:
        with db.connect(db_path) as conn:
            for day in _date_range(date_from, date_to):
                sync_day(conn, client, day)
            sync_activities(conn, client, date_from, date_to)
            sync_race_predictions(conn, client, date_from, date_to)

        with db.connect(db_path) as conn:
            conn.execute(
                "UPDATE sync_log SET finished_at = ?, status = 'success' WHERE id = ?",
                (_now_iso(), log_id),
            )
    except Exception as exc:
        logger.exception("Sync fehlgeschlagen")
        with db.connect(db_path) as conn:
            conn.execute(
                "UPDATE sync_log SET finished_at = ?, status = 'failed', error = ? WHERE id = ?",
                (_now_iso(), str(exc), log_id),
            )
        raise
