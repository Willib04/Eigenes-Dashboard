"""Verbindet die lokale Datenbank (Phase 1/2) mit den Berechnungen (Phase 3)
zu einem taeglichen Bericht. Reine Lesefunktionen - kein Garmin-API-Zugriff,
daher jederzeit beliebig oft aufrufbar (z.B. aus dem MCP-Server).
"""

from __future__ import annotations

import datetime as dt
import math
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from app import config, metrics
from app import metrics_config as mc

HISTORY_DAYS_FOR_BASELINE = 90


def _date_range_strings(date_to: dt.date, days: int) -> list[str]:
    date_from = date_to - dt.timedelta(days=days - 1)
    return [(date_from + dt.timedelta(days=i)).isoformat() for i in range((date_to - date_from).days + 1)]


def _load_daily_metrics_by_date(conn: sqlite3.Connection, dates: list[str]) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT * FROM daily_metrics WHERE date BETWEEN ? AND ? ORDER BY date",
        (dates[0], dates[-1]),
    ).fetchall()
    return {row["date"]: dict(row) for row in rows}


def _load_sleep_by_date(conn: sqlite3.Connection, dates: list[str]) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT * FROM sleep WHERE date BETWEEN ? AND ? ORDER BY date",
        (dates[0], dates[-1]),
    ).fetchall()
    return {row["date"]: dict(row) for row in rows}


def _load_activities_by_date(conn: sqlite3.Connection, dates: list[str]) -> dict[str, list[dict]]:
    rows = conn.execute(
        "SELECT * FROM activities WHERE date BETWEEN ? AND ? ORDER BY date",
        (dates[0], dates[-1]),
    ).fetchall()
    by_date: dict[str, list[dict]] = {d: [] for d in dates}
    for row in rows:
        by_date.setdefault(row["date"], []).append(dict(row))
    return by_date


def _sleep_hours(sleep_row: dict | None) -> float | None:
    if not sleep_row or sleep_row.get("total_sleep_seconds") is None:
        return None
    return sleep_row["total_sleep_seconds"] / 3600


def _daily_loads_series(
    dates: list[str], daily_by_date: dict[str, dict], activities_by_date: dict[str, list[dict]]
) -> list[tuple[str, float | None]]:
    """Tages-TRIMP fuer jeden Tag im Zeitraum (Grundlage fuer Strain, CTL/ATL/TSB, ACWR)."""
    daily_loads: list[tuple[str, float | None]] = []
    for d in dates:
        day_daily = daily_by_date.get(d) or {}
        resting_hr_that_day = day_daily.get("resting_hr")
        activity_trimps = [
            metrics.banister_trimp(
                (a.get("duration_seconds") or 0) / 60,
                a.get("avg_hr"),
                resting_hr_that_day,
            )
            for a in activities_by_date.get(d, [])
        ]
        daily_loads.append((d, metrics.daily_trimp(activity_trimps)))
    return daily_loads


def build_daily_report(conn: sqlite3.Connection, target_date: dt.date | None = None) -> dict[str, Any]:
    """Baut den kompletten Bericht fuer `target_date` (Standard: heute).

    Nutzt die letzten HISTORY_DAYS_FOR_BASELINE Tage als Grundlage fuer
    Baselines, CTL/ATL/TSB und ACWR.
    """
    target_date = target_date or dt.date.today()
    dates = _date_range_strings(target_date, HISTORY_DAYS_FOR_BASELINE)
    target_str = target_date.isoformat()

    daily_by_date = _load_daily_metrics_by_date(conn, dates)
    sleep_by_date = _load_sleep_by_date(conn, dates)
    activities_by_date = _load_activities_by_date(conn, dates)

    # --- Baselines (Phase 3.1) ---
    hrv_dated = [(d, metrics.ln_hrv((daily_by_date.get(d) or {}).get("hrv_avg_ms"))) for d in dates]
    rhr_dated = [(d, (daily_by_date.get(d) or {}).get("resting_hr")) for d in dates]
    resp_dated = [(d, (daily_by_date.get(d) or {}).get("respiration_avg")) for d in dates]

    window = mc.RECOVERY_BASELINE_WINDOW_DAYS
    min_points = mc.BASELINE_MIN_POINTS.get(window, max(3, window // 3))

    hrv_baselines = metrics.trailing_baseline(hrv_dated, window, min_points)
    rhr_baselines = metrics.trailing_baseline(rhr_dated, window, min_points)
    resp_baselines = metrics.trailing_baseline(resp_dated, window, min_points)

    # --- Tages-TRIMP fuer die ganze Historie (fuer CTL/ATL/TSB/ACWR) ---
    daily_loads = _daily_loads_series(dates, daily_by_date, activities_by_date)

    ctl_atl_tsb_series = metrics.compute_ctl_atl_tsb(daily_loads)
    ctl_atl_tsb_by_date = {row["date"]: row for row in ctl_atl_tsb_series}
    acwr_by_date = metrics.acute_chronic_ratio(daily_loads)

    # --- Werte fuer den Zieltag ---
    today_daily = daily_by_date.get(target_str) or {}
    today_sleep = sleep_by_date.get(target_str) or {}
    today_sleep_hours = _sleep_hours(today_sleep)
    today_trimp = dict(daily_loads).get(target_str)
    today_strain = metrics.trimp_to_strain(today_trimp)
    today_ctl_atl_tsb = ctl_atl_tsb_by_date.get(target_str, {})
    today_acwr = acwr_by_date.get(target_str)

    sleep_need_hours_for_last_night = None
    recovery_score = None
    recovery_components: dict[str, float | None] = {}
    if today_daily or today_sleep:
        # Schlafbedarf FUER letzte Nacht (um die Schlafleistung heute morgen zu bewerten)
        # wird aus dem Strain des VORTAGES berechnet.
        yesterday_str = (target_date - dt.timedelta(days=1)).isoformat()
        yesterday_trimp = dict(daily_loads).get(yesterday_str)
        yesterday_strain = metrics.trimp_to_strain(yesterday_trimp)
        recent_nights = [
            _sleep_hours(sleep_by_date.get((target_date - dt.timedelta(days=i)).isoformat()))
            for i in range(1, mc.SLEEP_DEBT_WINDOW_DAYS + 1)
        ]
        sleep_need_breakdown = metrics.compute_sleep_need_hours(yesterday_strain, recent_nights)
        sleep_need_hours_for_last_night = sleep_need_breakdown["sleep_need_hours"]

        recovery_score, recovery_components = metrics.compute_recovery_score(
            hrv_ln_value=metrics.ln_hrv(today_daily.get("hrv_avg_ms")),
            hrv_ln_baseline=hrv_baselines.get(target_str, (None, None)),
            resting_hr=today_daily.get("resting_hr"),
            resting_hr_baseline=rhr_baselines.get(target_str, (None, None)),
            sleep_hours=today_sleep_hours,
            sleep_need_hours=sleep_need_hours_for_last_night,
            respiration_avg=today_daily.get("respiration_avg"),
            respiration_baseline=resp_baselines.get(target_str, (None, None)),
        )

    # Rohwerte fuer die Anzeige der Datengrundlage im Dashboard (Info-Buttons).
    hrv_baseline_ln_mean, _ = hrv_baselines.get(target_str, (None, None))
    rhr_baseline_mean, _ = rhr_baselines.get(target_str, (None, None))
    resp_baseline_mean, _ = resp_baselines.get(target_str, (None, None))
    recovery_grundlage = {
        "hrv_ms": today_daily.get("hrv_avg_ms"),
        "hrv_baseline_ms": round(math.exp(hrv_baseline_ln_mean), 1) if hrv_baseline_ln_mean is not None else None,
        "resting_hr": today_daily.get("resting_hr"),
        "resting_hr_baseline": round(rhr_baseline_mean, 1) if rhr_baseline_mean is not None else None,
        "schlaf_stunden": round(today_sleep_hours, 2) if today_sleep_hours is not None else None,
        "schlafbedarf_stunden": sleep_need_hours_for_last_night,
        "atemfrequenz": today_daily.get("respiration_avg"),
        "atemfrequenz_baseline": round(resp_baseline_mean, 1) if resp_baseline_mean is not None else None,
    }

    # Schlafbedarf FUER HEUTE NACHT (basierend auf dem Strain von heute + Schlafschuld)
    recent_nights_incl_today = [
        _sleep_hours(sleep_by_date.get((target_date - dt.timedelta(days=i)).isoformat()))
        for i in range(0, mc.SLEEP_DEBT_WINDOW_DAYS)
    ]
    sleep_need_tonight = metrics.compute_sleep_need_hours(today_strain, recent_nights_incl_today)
    tomorrow_weekday = (target_date + dt.timedelta(days=1)).isoweekday()
    bedtime_recommendation = metrics.recommended_bedtime(
        metrics.wake_time_for_weekday(tomorrow_weekday), sleep_need_tonight["sleep_need_hours"]
    )

    recommendation = metrics.daily_load_recommendation(
        recovery_score, today_ctl_atl_tsb.get("tsb"), today_acwr
    )

    hrv_below_flags = []
    rhr_above_flags = []
    for d in dates[-mc.WARNING_CONSECUTIVE_DAYS:]:
        hrv_val = metrics.ln_hrv((daily_by_date.get(d) or {}).get("hrv_avg_ms"))
        hrv_mean, _ = hrv_baselines.get(d, (None, None))
        rhr_val = (daily_by_date.get(d) or {}).get("resting_hr")
        rhr_mean, _ = rhr_baselines.get(d, (None, None))
        hrv_below_flags.append(None if hrv_val is None or hrv_mean is None else hrv_val < hrv_mean)
        rhr_above_flags.append(None if rhr_val is None or rhr_mean is None else rhr_val > rhr_mean)
    warning = metrics.overload_warning(hrv_below_flags, rhr_above_flags)

    return {
        "date": target_str,
        "recovery_score": recovery_score,
        "recovery_ampel": metrics.recovery_traffic_light(recovery_score),
        "recovery_components": recovery_components,
        "recovery_grundlage": recovery_grundlage,
        "strain_heute": today_strain,
        "trimp_heute": today_trimp,
        "garmin_training_load_heute": sum(
            a.get("training_load") or 0 for a in activities_by_date.get(target_str, [])
        ) or None,
        "ctl": today_ctl_atl_tsb.get("ctl"),
        "atl": today_ctl_atl_tsb.get("atl"),
        "tsb": today_ctl_atl_tsb.get("tsb"),
        "acwr": today_acwr,
        "acwr_flag": metrics.acwr_flag(today_acwr),
        "schlaf_letzte_nacht_stunden": today_sleep_hours,
        "schlafbedarf_letzte_nacht_stunden": sleep_need_hours_for_last_night,
        "schlafbedarf_heute_nacht": sleep_need_tonight,
        "empfohlene_zubettgehzeit": bedtime_recommendation,
        "empfehlung_heute": recommendation,
        "warnsignal_ueberlastung": warning,
    }


def _bedtime_minutes_from_iso(bedtime_iso: str | None) -> float | None:
    """Wandelt eine gespeicherte UTC-Zubettgehzeit in "Minuten seit Mittag" (lokal) um.

    Zeiten nach Mitternacht (z.B. 00:15) werden auf 24:15 verschoben, damit sie
    numerisch nah an 23:xx liegen statt einen Sprung auf ~0 zu machen - sonst
    wuerde die Standardabweichung durch den Mitternachts-Wrap kuenstlich riesig.
    """
    if not bedtime_iso:
        return None
    try:
        moment = dt.datetime.fromisoformat(bedtime_iso)
    except ValueError:
        return None
    local = moment.astimezone(ZoneInfo(config.TIMEZONE))
    minutes = local.hour * 60 + local.minute
    if local.hour < 12:
        minutes += 24 * 60
    return float(minutes)


def build_trends(conn: sqlite3.Connection, weeks: int = 12, end_date: dt.date | None = None) -> dict[str, Any]:
    """HRV-, Ruhepuls-, VO2max- und Schlaf-Trends ueber `weeks` Wochen, plus
    Schlafkonsistenz (Standardabweichung der Zubettgehzeit).
    """
    end_date = end_date or dt.date.today()
    display_days = weeks * 7
    lookback_days = display_days + mc.RECOVERY_BASELINE_WINDOW_DAYS
    dates = _date_range_strings(end_date, lookback_days)
    display_dates = dates[-display_days:]

    daily_by_date = _load_daily_metrics_by_date(conn, dates)
    sleep_by_date = _load_sleep_by_date(conn, dates)

    hrv_dated = [(d, metrics.ln_hrv((daily_by_date.get(d) or {}).get("hrv_avg_ms"))) for d in dates]
    rhr_dated = [(d, (daily_by_date.get(d) or {}).get("resting_hr")) for d in dates]

    window = mc.RECOVERY_BASELINE_WINDOW_DAYS
    min_points = mc.BASELINE_MIN_POINTS.get(window, max(3, window // 3))
    hrv_baselines = metrics.trailing_baseline(hrv_dated, window, min_points)
    rhr_baselines = metrics.trailing_baseline(rhr_dated, window, min_points)

    hrv_series, rhr_series, vo2max_series = [], [], []
    sleep_hours_series, sleep_score_series, bedtime_minutes = [], [], []

    for d in display_dates:
        daily = daily_by_date.get(d) or {}

        hrv_baseline_mean, _ = hrv_baselines.get(d, (None, None))
        hrv_series.append({
            "date": d,
            "value": daily.get("hrv_avg_ms"),
            "baseline": round(math.exp(hrv_baseline_mean), 1) if hrv_baseline_mean is not None else None,
        })

        rhr_baseline_mean, _ = rhr_baselines.get(d, (None, None))
        rhr_series.append({
            "date": d,
            "value": daily.get("resting_hr"),
            "baseline": round(rhr_baseline_mean, 1) if rhr_baseline_mean is not None else None,
        })

        if daily.get("vo2max_running") is not None:
            vo2max_series.append({"date": d, "value": daily["vo2max_running"]})

        sleep_row = sleep_by_date.get(d)
        hours = _sleep_hours(sleep_row)
        sleep_hours_series.append({"date": d, "value": round(hours, 2) if hours is not None else None})
        sleep_score_series.append({"date": d, "value": sleep_row.get("sleep_score") if sleep_row else None})
        bedtime_minutes.append(_bedtime_minutes_from_iso(sleep_row.get("bedtime_utc") if sleep_row else None))

    return {
        "weeks": weeks,
        "hrv": hrv_series,
        "resting_hr": rhr_series,
        "vo2max_running": vo2max_series,
        "sleep_hours": sleep_hours_series,
        "sleep_score": sleep_score_series,
        "sleep_consistency_minutes": metrics.bedtime_consistency_minutes(bedtime_minutes),
    }


def build_load_history(conn: sqlite3.Connection, days: int = 90, end_date: dt.date | None = None) -> list[dict[str, Any]]:
    """CTL/ATL/TSB/ACWR/Strain je Tag - Grundlage fuer den Belastungs-Chart."""
    end_date = end_date or dt.date.today()
    lookback_days = days + mc.CTL_WINDOW_DAYS  # Vorlauf, damit CTL/ATL nicht sichtbar bei 0 anfangen
    dates = _date_range_strings(end_date, lookback_days)
    display_dates = dates[-days:]

    daily_by_date = _load_daily_metrics_by_date(conn, dates)
    activities_by_date = _load_activities_by_date(conn, dates)
    daily_loads = _daily_loads_series(dates, daily_by_date, activities_by_date)

    ctl_atl_tsb_by_date = {row["date"]: row for row in metrics.compute_ctl_atl_tsb(daily_loads)}
    acwr_by_date = metrics.acute_chronic_ratio(daily_loads)
    trimp_by_date = dict(daily_loads)

    history = []
    for d in display_dates:
        row = ctl_atl_tsb_by_date.get(d, {})
        trimp = trimp_by_date.get(d)
        history.append({
            "date": d,
            "ctl": row.get("ctl"),
            "atl": row.get("atl"),
            "tsb": row.get("tsb"),
            "acwr": acwr_by_date.get(d),
            "strain": metrics.trimp_to_strain(trimp),
            "trimp": trimp,
        })
    return history
