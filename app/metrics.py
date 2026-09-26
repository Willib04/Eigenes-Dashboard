"""Berechnete Kennzahlen (Phase 3): Baselines, Recovery-Score, Strain,
CTL/ATL/TSB/ACWR, Schlafbedarf, Tagesempfehlung und Warnsignale.

Grundsatz wie in Phase 1/2: fehlt eine Eingabe, wird das Ergebnis None
("keine Daten") statt geschaetzt. Jede Funktion ist bewusst klein und pur
(gleiche Eingabe -> gleiche Ausgabe), damit sie leicht zu testen und zu
erklaeren ist (Info-Button in Phase 5 kann direkt auf diese Formeln verweisen).
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections import deque
from typing import Any

from app import metrics_config as mc

# ---------------------------------------------------------------------------
# 3.1 Baselines
# ---------------------------------------------------------------------------


def ln_hrv(hrv_ms: float | None) -> float | None:
    """Natuerlicher Logarithmus der HRV (ln rMSSD) - ueblich, weil HRV-Werte
    log-normal verteilt sind und Veraenderungen so eher normalverteilt sind."""
    if hrv_ms is None or hrv_ms <= 0:
        return None
    return math.log(hrv_ms)


def trailing_baseline(
    dated_values: list[tuple[str, float | None]],
    window_days: int,
    min_points: int,
) -> dict[str, tuple[float | None, float | None]]:
    """Fuer jedes Datum: Mittelwert + Standardabweichung der vorherigen
    `window_days` Tage (der Tag selbst ist NICHT enthalten - die Baseline
    soll den "normalen" Zustand zeigen, nicht durch den zu bewertenden Tag
    selbst verzerrt werden).

    dated_values muss chronologisch aufsteigend sortiert sein und sollte fuer
    jeden Kalendertag im Zeitraum einen Eintrag haben (auch mit value=None),
    damit die Fenstergrenze nach Tagen (nicht nach Anzahl Eintraegen) stimmt.

    Liefert (None, None), wenn weniger als `min_points` echte Werte im
    Fenster liegen.
    """
    results: dict[str, tuple[float | None, float | None]] = {}
    window: deque[tuple[str, float | None]] = deque()

    for date_str, value in dated_values:
        real_values = [v for _, v in window if v is not None]
        if len(real_values) >= min_points:
            mean = statistics.fmean(real_values)
            std = statistics.pstdev(real_values) if len(real_values) > 1 else 0.0
            results[date_str] = (mean, std)
        else:
            results[date_str] = (None, None)

        window.append((date_str, value))
        cutoff = (dt.date.fromisoformat(date_str) - dt.timedelta(days=window_days)).isoformat()
        while window and window[0][0] <= cutoff:
            window.popleft()

    return results


# ---------------------------------------------------------------------------
# 3.2 Recovery-Score
# ---------------------------------------------------------------------------


def _zscore_component(value: float | None, baseline_mean: float | None, baseline_std: float | None,
                       higher_is_better: bool) -> float | None:
    """Wandelt einen Wert + seine Baseline in eine 0-100-Teilbewertung um.

    50 Punkte = genau auf der Baseline. +-2 Standardabweichungen = 100/0
    Punkte. Bei higher_is_better=False (z.B. Ruhepuls, Atemfrequenz) wird
    die Richtung umgedreht: niedriger als die Baseline ist dann besser.
    """
    if value is None or baseline_mean is None or baseline_std is None:
        return None
    if baseline_std == 0:
        z = 0.0
    else:
        z = (value - baseline_mean) / baseline_std
        if not higher_is_better:
            z = -z
    score = 50 + z * 25
    return max(0.0, min(100.0, score))


def sleep_performance_score(sleep_hours: float | None, sleep_need_hours: float | None) -> float | None:
    """Schlaf/Schlafbedarf als 0-100-Teilbewertung (100 = Schlafbedarf erfuellt)."""
    if sleep_hours is None or sleep_need_hours is None or sleep_need_hours <= 0:
        return None
    ratio = sleep_hours / sleep_need_hours
    return max(0.0, min(100.0, ratio * 100))


def compute_recovery_score(
    hrv_ln_value: float | None,
    hrv_ln_baseline: tuple[float | None, float | None],
    resting_hr: float | None,
    resting_hr_baseline: tuple[float | None, float | None],
    sleep_hours: float | None,
    sleep_need_hours: float | None,
    respiration_avg: float | None,
    respiration_baseline: tuple[float | None, float | None],
    weights: dict[str, float] | None = None,
) -> tuple[float | None, dict[str, float | None]]:
    """Recovery-Score 0-100. Gewichtung ueber app/metrics_config.py einstellbar.

    Komponenten ohne verfuegbare Daten fallen weg, ihr Gewicht wird
    anteilig auf die vorhandenen Komponenten umgelegt (statt den Score
    kuenstlich nach unten zu ziehen).
    """
    weights = weights or mc.RECOVERY_WEIGHTS

    components = {
        "hrv": _zscore_component(hrv_ln_value, *hrv_ln_baseline, higher_is_better=True),
        "resting_hr": _zscore_component(resting_hr, *resting_hr_baseline, higher_is_better=False),
        "sleep": sleep_performance_score(sleep_hours, sleep_need_hours),
        "respiration": _zscore_component(respiration_avg, *respiration_baseline, higher_is_better=False),
    }

    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return None, components

    total_weight = sum(weights.get(k, 0.0) for k in available)
    if total_weight <= 0:
        return None, components

    score = sum(components[k] * weights.get(k, 0.0) for k in available) / total_weight
    return round(score, 1), components


def recovery_traffic_light(score: float | None) -> str:
    """'gruen' / 'gelb' / 'rot' / 'keine Daten'."""
    if score is None:
        return "keine Daten"
    if score >= mc.RECOVERY_GREEN_MIN:
        return "gruen"
    if score >= mc.RECOVERY_YELLOW_MIN:
        return "gelb"
    return "rot"


# ---------------------------------------------------------------------------
# 3.3 Strain / TRIMP (Banister)
# ---------------------------------------------------------------------------


def banister_trimp(
    duration_minutes: float | None,
    avg_hr: float | None,
    resting_hr: float | None,
    hf_max: float | None = None,
    sex: str | None = None,
) -> float | None:
    """TRIMP nach Banister: duration_min * HRr * 0.64 * e^(b*HRr)

    HRr = (avg_hr - resting_hr) / (HFmax - resting_hr), b = 1.92 (maennlich)
    bzw. 1.67 (weiblich).
    """
    hf_max = hf_max if hf_max is not None else mc.HF_MAX
    sex = sex or mc.SEX

    if duration_minutes is None or avg_hr is None or resting_hr is None:
        return None
    if hf_max is None or hf_max <= resting_hr:
        return None

    hrr = (avg_hr - resting_hr) / (hf_max - resting_hr)
    hrr = max(0.0, min(1.0, hrr))
    b = 1.92 if sex == "male" else 1.67
    return duration_minutes * hrr * 0.64 * math.exp(b * hrr)


def daily_trimp(activity_trimps: list[float | None]) -> float | None:
    """Summe der TRIMP-Werte eines Tages.

    Kein Eintrag (Ruhetag) -> 0.0 (echte Information: nichts trainiert).
    Nur Eintraege ohne berechenbaren TRIMP (z.B. HF-Sensor fehlte) -> None
    ("keine Daten"), damit das nicht faelschlich wie ein Ruhetag aussieht.
    """
    if not activity_trimps:
        return 0.0
    computable = [t for t in activity_trimps if t is not None]
    if not computable:
        return None
    return sum(computable)


def trimp_to_strain(trimp: float | None, k: float | None = None) -> float | None:
    """Bildet TRIMP logarithmisch (saettigend) auf eine 0-21-Skala ab, angelehnt
    an WHOOPs Strain-Konzept. Der genaue WHOOP-Algorithmus ist nicht
    veroeffentlicht - das hier ist eine transparente Naeherung mit gleicher
    Grundidee: kleine Belastungssteigerungen zaehlen bei niedriger
    Tagesbelastung mehr als bei bereits hoher Tagesbelastung.
    """
    if trimp is None:
        return None
    k = k if k is not None else mc.STRAIN_TRIMP_SCALE_K
    strain = mc.STRAIN_SCALE_MAX * (1 - math.exp(-trimp / k))
    return round(strain, 1)


# ---------------------------------------------------------------------------
# 3.4 CTL / ATL / TSB / ACWR
# ---------------------------------------------------------------------------


def compute_ctl_atl_tsb(
    daily_loads: list[tuple[str, float | None]],
    ctl_days: int | None = None,
    atl_days: int | None = None,
) -> list[dict[str, Any]]:
    """Exponentiell gewichtete Mittelwerte (Coggan-Modell).

    TSB fuer einen Tag wird aus CTL/ATL VOR dem Training dieses Tages
    berechnet (Stand zu Beginn des Tages) - das ist die relevante Groesse
    fuer die Frage "wie belastbar bin ich heute", nicht "wie belastbar war
    ich nachdem ich heute schon trainiert habe".

    Fehlende Tageswerte (None) werden fuer die Fortschreibung wie 0
    behandelt (siehe README/Wissensluecken-Hinweis) - das entspricht der
    ueblichen Praxis in Trainings-Tools, wenn an einem Tag keine Aktivitaet
    vorliegt.
    """
    ctl_days = ctl_days or mc.CTL_WINDOW_DAYS
    atl_days = atl_days or mc.ATL_WINDOW_DAYS

    ctl_alpha = 1 - math.exp(-1 / ctl_days)
    atl_alpha = 1 - math.exp(-1 / atl_days)

    results = []
    ctl = 0.0
    atl = 0.0
    for date_str, load in daily_loads:
        tsb_at_start_of_day = ctl - atl
        load_value = load if load is not None else 0.0
        ctl = ctl + (load_value - ctl) * ctl_alpha
        atl = atl + (load_value - atl) * atl_alpha
        results.append(
            {
                "date": date_str,
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(tsb_at_start_of_day, 1),
            }
        )
    return results


def acute_chronic_ratio(
    daily_loads: list[tuple[str, float | None]],
    acute_days: int | None = None,
    chronic_days: int | None = None,
) -> dict[str, float | None]:
    """ACWR = Durchschnitt der letzten `acute_days` Tage / Durchschnitt der
    letzten `chronic_days` Tage, je Datum. None, wenn nicht genug
    Vorlaufzeit fuer das chronische Fenster vorhanden ist.
    """
    acute_days = acute_days or mc.ACWR_ACUTE_DAYS
    chronic_days = chronic_days or mc.ACWR_CHRONIC_DAYS

    dates = [d for d, _ in daily_loads]
    loads = [l if l is not None else 0.0 for _, l in daily_loads]

    results: dict[str, float | None] = {}
    for i, date_str in enumerate(dates):
        if i + 1 < chronic_days:
            results[date_str] = None
            continue
        acute_slice = loads[max(0, i + 1 - acute_days): i + 1]
        chronic_slice = loads[i + 1 - chronic_days: i + 1]
        chronic_avg = statistics.fmean(chronic_slice)
        if chronic_avg == 0:
            results[date_str] = None
            continue
        acute_avg = statistics.fmean(acute_slice)
        results[date_str] = round(acute_avg / chronic_avg, 2)
    return results


def acwr_flag(acwr: float | None) -> str | None:
    if acwr is None:
        return None
    if acwr > mc.ACWR_HIGH_WARNING:
        return "warnung_zu_hoch"
    if acwr < mc.ACWR_LOW_HINT:
        return "hinweis_zu_niedrig"
    return "im_zielbereich"


# ---------------------------------------------------------------------------
# 3.5 Schlafbedarf + Zubettgehzeit
# ---------------------------------------------------------------------------


def sleep_debt_hours(
    recent_sleep_hours: list[float | None],
    base_need_hours: float | None = None,
) -> float:
    """Summe der fehlenden Stunden ueber die letzten Naechte (nur Naechte mit
    echten Schlafdaten, fehlende Naechte werden nicht mitgezaehlt - keine
    Erfindung von Schulden aus Nicht-Daten)."""
    base_need_hours = base_need_hours if base_need_hours is not None else mc.BASE_SLEEP_NEED_HOURS
    debt = 0.0
    for hours in recent_sleep_hours:
        if hours is None:
            continue
        debt += max(0.0, base_need_hours - hours)
    return debt


def compute_sleep_need_hours(
    todays_strain: float | None,
    recent_sleep_hours: list[float | None],
    nap_hours: float = 0.0,
    base_need_hours: float | None = None,
) -> dict[str, float]:
    """Schlafbedarf heute Nacht = Grundbedarf + Strain-Aufschlag +
    anteiliger Schuldenabbau - Nickerchen.

    Nickerchen werden aktuell immer mit 0 angenommen, da Garmin Connect
    keinen direkt abrufbaren "Nap"-Wert liefert (keine erfundene Zahl).
    """
    base_need_hours = base_need_hours if base_need_hours is not None else mc.BASE_SLEEP_NEED_HOURS

    strain = todays_strain if todays_strain is not None else 0.0
    strain_surcharge_hours = (strain / mc.STRAIN_SCALE_MAX) * (mc.SLEEP_STRAIN_SURCHARGE_MAX_MINUTES / 60)

    debt = sleep_debt_hours(recent_sleep_hours, base_need_hours)
    debt_repayment_hours = debt * mc.SLEEP_DEBT_REPAYMENT_FRACTION

    total = base_need_hours + strain_surcharge_hours + debt_repayment_hours - nap_hours
    return {
        "base_need_hours": round(base_need_hours, 2),
        "strain_surcharge_hours": round(strain_surcharge_hours, 2),
        "debt_repayment_hours": round(debt_repayment_hours, 2),
        "nap_hours": round(nap_hours, 2),
        "sleep_need_hours": round(max(0.0, total), 2),
    }


def recommended_bedtime(wake_time: str, sleep_need_hours: float) -> str:
    """wake_time im Format 'HH:MM'. Gibt die Zubettgehzeit im gleichen Format
    zurueck (auf 5 Minuten gerundet), Datumsuebergang wird korrekt
    beruecksichtigt.
    """
    wake_hour, wake_minute = (int(p) for p in wake_time.split(":"))
    anchor = dt.datetime(2000, 1, 2, wake_hour, wake_minute)
    bedtime = anchor - dt.timedelta(hours=sleep_need_hours)

    rounded_minute = round(bedtime.minute / 5) * 5
    bedtime = bedtime.replace(minute=0) + dt.timedelta(minutes=rounded_minute)

    return bedtime.strftime("%H:%M")


def wake_time_for_weekday(iso_weekday: int) -> str:
    """iso_weekday: 1=Montag ... 7=Sonntag (dt.date.isoweekday())."""
    return mc.WAKE_TIME_WEEKEND if iso_weekday in (6, 7) else mc.WAKE_TIME_WEEKDAY


# ---------------------------------------------------------------------------
# 3.6 Optimale Belastung heute
# ---------------------------------------------------------------------------


def daily_load_recommendation(
    recovery_score: float | None,
    tsb: float | None,
    acwr: float | None,
) -> dict[str, Any]:
    """Regelbasierte Tagesempfehlung. Wird in Phase 4 in den periodisierten
    Trainingsplan integriert - hier erstmal die grundsaetzliche Logik aus
    Recovery-Ampel + Form (TSB) + Akut:Chronisch-Verhaeltnis (ACWR).
    """
    traffic_light = recovery_traffic_light(recovery_score)
    flag = acwr_flag(acwr)

    if traffic_light == "keine Daten":
        return {
            "ampel": traffic_light,
            "strain_korridor": None,
            "empfehlung": "Keine Empfehlung moeglich - Recovery-Score konnte nicht berechnet werden (zu wenig Daten).",
        }

    if flag == "warnung_zu_hoch":
        return {
            "ampel": traffic_light,
            "strain_korridor": (0, 6),
            "empfehlung": (
                f"ACWR liegt bei {acwr} (Warnschwelle {mc.ACWR_HIGH_WARNING}) - "
                "Belastung war zuletzt deutlich hoeher als gewohnt. Heute nur "
                "lockere Bewegung oder Pause, kein intensives Training."
            ),
        }

    if traffic_light == "rot":
        return {
            "ampel": traffic_light,
            "strain_korridor": (0, 4),
            "empfehlung": "Recovery ist rot - heute nur lockere Bewegung oder komplette Pause.",
        }

    if traffic_light == "gelb":
        return {
            "ampel": traffic_light,
            "strain_korridor": (6, 12),
            "empfehlung": "Recovery ist gelb - moderates Training moeglich, z.B. 45 min Zone 2 statt einer harten Einheit.",
        }

    # gruen
    if flag == "hinweis_zu_niedrig":
        return {
            "ampel": traffic_light,
            "strain_korridor": (10, 18),
            "empfehlung": (
                f"Recovery ist gruen, ACWR mit {acwr} eher niedrig (< {mc.ACWR_LOW_HINT}) - "
                "du koenntest die Belastung behutsam steigern, z.B. eine Tempo- oder Intervalleinheit."
            ),
        }

    if tsb is not None and tsb < -20:
        return {
            "ampel": traffic_light,
            "strain_korridor": (8, 14),
            "empfehlung": f"Recovery ist gruen, aber die Form (TSB {tsb}) ist stark negativ - moderate statt maximale Qualitaetseinheit.",
        }

    return {
        "ampel": traffic_light,
        "strain_korridor": (10, 18),
        "empfehlung": "Recovery ist gruen - eine Qualitaetseinheit ist moeglich, z.B. Tempolauf oder Intervalle.",
    }


# ---------------------------------------------------------------------------
# 3.8 Warnsignale
# ---------------------------------------------------------------------------


def overload_warning(
    hrv_below_baseline_flags: list[bool | None],
    rhr_above_baseline_flags: list[bool | None],
    consecutive_days: int | None = None,
) -> bool:
    """True, wenn die letzten `consecutive_days` Tage JEWEILS HRV unter
    Baseline UND Ruhepuls ueber Baseline zeigen (moegliches Zeichen von
    Uebermuedung/beginnendem Infekt - absichtlich vorsichtig formuliert,
    keine medizinische Diagnose).
    """
    consecutive_days = consecutive_days or mc.WARNING_CONSECUTIVE_DAYS
    if len(hrv_below_baseline_flags) < consecutive_days or len(rhr_above_baseline_flags) < consecutive_days:
        return False

    recent_hrv = hrv_below_baseline_flags[-consecutive_days:]
    recent_rhr = rhr_above_baseline_flags[-consecutive_days:]

    return all(h is True for h in recent_hrv) and all(r is True for r in recent_rhr)
