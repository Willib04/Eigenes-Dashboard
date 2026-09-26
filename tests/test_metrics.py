import math

import pytest

from app import metrics


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


def test_ln_hrv() -> None:
    assert metrics.ln_hrv(50.0) == pytest.approx(math.log(50.0))
    assert metrics.ln_hrv(None) is None
    assert metrics.ln_hrv(0) is None
    assert metrics.ln_hrv(-5) is None


def test_trailing_baseline_excludes_current_day_and_respects_min_points() -> None:
    dated_values = [(f"2024-01-{d:02d}", 10.0) for d in range(1, 8)]  # 7 Tage à 10.0
    dated_values.append(("2024-01-08", 100.0))  # Ausreisser, der die eigene Baseline nicht beeinflussen darf

    results = metrics.trailing_baseline(dated_values, window_days=7, min_points=4)

    # Erste Tage: zu wenig Vorlauf -> keine Baseline
    assert results["2024-01-01"] == (None, None)
    assert results["2024-01-04"] == (None, None)  # nur 3 Vortage
    # Ab dem 5. Tag (4 Vortage vorhanden) gibt es eine Baseline
    mean, std = results["2024-01-05"]
    assert mean == pytest.approx(10.0)
    assert std == pytest.approx(0.0)
    # Der Ausreisser am 8. Tag darf die Baseline DES 8. TAGES nicht enthalten
    mean_8, _ = results["2024-01-08"]
    assert mean_8 == pytest.approx(10.0)


def test_trailing_baseline_window_is_date_based_not_count_based() -> None:
    dated_values = [
        ("2024-01-01", 10.0),
        ("2024-01-02", 10.0),
        ("2024-01-03", 10.0),
        ("2024-01-04", 10.0),
        # Luecke: 05.-09. fehlen komplett
        ("2024-01-10", 50.0),
    ]
    results = metrics.trailing_baseline(dated_values, window_days=7, min_points=2)
    # Am 10.01. liegt das 7-Tage-Fenster (03.-09.) - nur der 03. und 04. fallen noch hinein
    mean, _ = results["2024-01-10"]
    assert mean == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Recovery-Score
# ---------------------------------------------------------------------------


def test_zscore_component_higher_is_better() -> None:
    assert metrics._zscore_component(50, 40, 5, higher_is_better=True) == 100.0  # +2 SD -> Deckel
    assert metrics._zscore_component(30, 40, 5, higher_is_better=True) == 0.0  # -2 SD -> Boden
    assert metrics._zscore_component(40, 40, 5, higher_is_better=True) == 50.0  # auf Baseline


def test_zscore_component_lower_is_better_inverts_direction() -> None:
    # Ruhepuls UNTER Baseline soll eine bessere (hoehere) Teilbewertung ergeben
    assert metrics._zscore_component(35, 40, 5, higher_is_better=False) == 75.0


def test_zscore_component_zero_std_is_neutral() -> None:
    assert metrics._zscore_component(99, 40, 0, higher_is_better=True) == 50.0


def test_zscore_component_missing_data_returns_none() -> None:
    assert metrics._zscore_component(None, 40, 5, higher_is_better=True) is None
    assert metrics._zscore_component(50, None, 5, higher_is_better=True) is None


def test_sleep_performance_score() -> None:
    assert metrics.sleep_performance_score(8.0, 8.0) == 100.0
    assert metrics.sleep_performance_score(4.0, 8.0) == 50.0
    assert metrics.sleep_performance_score(10.0, 8.0) == 100.0  # gedeckelt
    assert metrics.sleep_performance_score(None, 8.0) is None


def test_compute_recovery_score_weighted_average() -> None:
    score, components = metrics.compute_recovery_score(
        hrv_ln_value=math.log(55), hrv_ln_baseline=(math.log(50), 0.1),
        resting_hr=48, resting_hr_baseline=(50, 2),
        sleep_hours=7.5, sleep_need_hours=8.0,
        respiration_avg=13, respiration_baseline=(14, 1),
        weights={"hrv": 0.5, "resting_hr": 0.2, "sleep": 0.2, "respiration": 0.1},
    )
    expected = (
        components["hrv"] * 0.5
        + components["resting_hr"] * 0.2
        + components["sleep"] * 0.2
        + components["respiration"] * 0.1
    )
    assert score == pytest.approx(expected, abs=0.05)


def test_compute_recovery_score_renormalizes_missing_components() -> None:
    # Nur HRV und Ruhepuls vorhanden, Schlaf/Atmung fehlen
    score, components = metrics.compute_recovery_score(
        hrv_ln_value=math.log(55), hrv_ln_baseline=(math.log(50), 0.1),
        resting_hr=48, resting_hr_baseline=(50, 2),
        sleep_hours=None, sleep_need_hours=None,
        respiration_avg=None, respiration_baseline=(None, None),
        weights={"hrv": 0.5, "resting_hr": 0.2, "sleep": 0.2, "respiration": 0.1},
    )
    expected = (components["hrv"] * 0.5 + components["resting_hr"] * 0.2) / 0.7
    assert score == pytest.approx(expected, abs=0.05)


def test_compute_recovery_score_all_missing_returns_none() -> None:
    score, _ = metrics.compute_recovery_score(
        None, (None, None), None, (None, None), None, None, None, (None, None)
    )
    assert score is None


def test_recovery_traffic_light_boundaries() -> None:
    assert metrics.recovery_traffic_light(67) == "gruen"
    assert metrics.recovery_traffic_light(66.9) == "gelb"
    assert metrics.recovery_traffic_light(34) == "gelb"
    assert metrics.recovery_traffic_light(33.9) == "rot"
    assert metrics.recovery_traffic_light(None) == "keine Daten"


# ---------------------------------------------------------------------------
# Strain / TRIMP
# ---------------------------------------------------------------------------


def test_banister_trimp_matches_published_formula() -> None:
    # Bekanntes Referenzbeispiel: 45 min, HRr=0.6, maennlich -> ca. 54-55 TRIMP
    # (Banister/Morton-Formel: TRIMP = t * HRr * 0.64 * e^(1.92*HRr))
    duration, avg_hr, resting_hr, hf_max = 45, 122, 50, 170  # HRr = (122-50)/(170-50) = 0.6
    hrr = (avg_hr - resting_hr) / (hf_max - resting_hr)
    assert hrr == pytest.approx(0.6)

    expected = duration * hrr * 0.64 * math.exp(1.92 * hrr)
    result = metrics.banister_trimp(duration, avg_hr, resting_hr, hf_max, "male")

    assert result == pytest.approx(expected)
    assert 53 < result < 56


def test_banister_trimp_female_uses_different_exponent() -> None:
    male = metrics.banister_trimp(30, 150, 50, 190, "male")
    female = metrics.banister_trimp(30, 150, 50, 190, "female")
    assert male != female


def test_banister_trimp_missing_data_returns_none() -> None:
    assert metrics.banister_trimp(None, 150, 50, 190) is None
    assert metrics.banister_trimp(30, None, 50, 190) is None
    assert metrics.banister_trimp(30, 150, 50, 50) is None  # hf_max <= resting_hr


def test_daily_trimp() -> None:
    assert metrics.daily_trimp([]) == 0.0  # Ruhetag
    assert metrics.daily_trimp([10.0, None, 5.0]) == 15.0
    assert metrics.daily_trimp([None, None]) is None  # Aktivitaet(en) ohne HF-Daten


def test_trimp_to_strain_bounds_and_shape() -> None:
    assert metrics.trimp_to_strain(None) is None
    assert metrics.trimp_to_strain(0) == 0.0
    strain_75 = metrics.trimp_to_strain(75.0, k=75.0)
    assert strain_75 == pytest.approx(21 * (1 - math.exp(-1)), abs=0.05)
    # Saettigend: doppelte Belastung bringt weniger als doppelten Strain-Zuwachs
    strain_150 = metrics.trimp_to_strain(150.0, k=75.0)
    assert (strain_150 - strain_75) < strain_75
    assert strain_150 < 21.0


# ---------------------------------------------------------------------------
# CTL / ATL / TSB / ACWR
# ---------------------------------------------------------------------------


def test_compute_ctl_atl_tsb_first_day_starts_from_zero() -> None:
    results = metrics.compute_ctl_atl_tsb([("2024-01-01", 100.0)], ctl_days=42, atl_days=7)
    ctl_alpha = 1 - math.exp(-1 / 42)
    atl_alpha = 1 - math.exp(-1 / 7)

    assert results[0]["tsb"] == 0.0  # vor dem ersten Tag gab es keine Belastung
    assert results[0]["ctl"] == pytest.approx(100.0 * ctl_alpha, abs=0.1)
    assert results[0]["atl"] == pytest.approx(100.0 * atl_alpha, abs=0.1)


def test_compute_ctl_atl_tsb_missing_day_treated_as_zero_load() -> None:
    results = metrics.compute_ctl_atl_tsb([("2024-01-01", 100.0), ("2024-01-02", None)])
    assert results[1]["ctl"] < results[0]["ctl"]  # Belastung faellt ohne neuen Reiz


def test_acute_chronic_ratio_requires_chronic_window() -> None:
    loads = [(f"day{i}", 10.0) for i in range(27)]  # nur 27 Tage < 28 chronic_days
    results = metrics.acute_chronic_ratio(loads, acute_days=7, chronic_days=28)
    assert all(v is None for v in results.values())


def test_acute_chronic_ratio_detects_spike() -> None:
    dates = [f"d{i:03d}" for i in range(35)]
    loads = [10.0] * 28 + [50.0] * 7  # letzte 7 Tage deutlich hoeher belastet
    results = metrics.acute_chronic_ratio(list(zip(dates, loads)), acute_days=7, chronic_days=28)
    last_ratio = results[dates[-1]]
    assert last_ratio is not None
    assert last_ratio > 1.5


def test_acwr_flag_thresholds() -> None:
    assert metrics.acwr_flag(1.6) == "warnung_zu_hoch"
    assert metrics.acwr_flag(0.7) == "hinweis_zu_niedrig"
    assert metrics.acwr_flag(1.0) == "im_zielbereich"
    assert metrics.acwr_flag(None) is None


# ---------------------------------------------------------------------------
# Schlafbedarf + Zubettgehzeit
# ---------------------------------------------------------------------------


def test_sleep_debt_hours_ignores_missing_nights() -> None:
    debt = metrics.sleep_debt_hours([6.0, None, 7.0], base_need_hours=8.0)
    assert debt == pytest.approx(2.0 + 1.0)  # nur die zwei echten Naechte zaehlen


def test_compute_sleep_need_hours_components() -> None:
    result = metrics.compute_sleep_need_hours(
        todays_strain=21.0,  # maximale Belastung -> voller Aufschlag
        recent_sleep_hours=[8.0] * 7,  # keine Schuld
        nap_hours=0.0,
        base_need_hours=8.0,
    )
    assert result["base_need_hours"] == 8.0
    assert result["strain_surcharge_hours"] == pytest.approx(1.0)  # 60 min Maximalaufschlag
    assert result["debt_repayment_hours"] == 0.0
    assert result["sleep_need_hours"] == pytest.approx(9.0)


def test_compute_sleep_need_hours_with_debt_and_naps() -> None:
    result = metrics.compute_sleep_need_hours(
        todays_strain=0.0,
        recent_sleep_hours=[6.0] * 7,  # 2h Schuld/Nacht * 7 = 14h Gesamtschuld
        nap_hours=0.5,
        base_need_hours=8.0,
    )
    assert result["debt_repayment_hours"] == pytest.approx(14.0 * 0.15)
    assert result["sleep_need_hours"] == pytest.approx(8.0 + 14.0 * 0.15 - 0.5)


def test_recommended_bedtime_simple_case() -> None:
    assert metrics.recommended_bedtime("06:30", 7.5) == "23:00"


def test_recommended_bedtime_rounds_to_five_minutes() -> None:
    bedtime = metrics.recommended_bedtime("06:30", 7.87)
    minute = int(bedtime.split(":")[1])
    assert minute % 5 == 0


def test_wake_time_for_weekday() -> None:
    assert metrics.wake_time_for_weekday(1) == "06:30"  # Montag
    assert metrics.wake_time_for_weekday(5) == "06:30"  # Freitag
    assert metrics.wake_time_for_weekday(6) == "08:30"  # Samstag
    assert metrics.wake_time_for_weekday(7) == "08:30"  # Sonntag


# ---------------------------------------------------------------------------
# Optimale Belastung + Warnsignale
# ---------------------------------------------------------------------------


def test_daily_load_recommendation_no_data() -> None:
    rec = metrics.daily_load_recommendation(None, None, None)
    assert rec["ampel"] == "keine Daten"
    assert rec["strain_korridor"] is None


def test_daily_load_recommendation_acwr_warning_overrides_green() -> None:
    rec = metrics.daily_load_recommendation(recovery_score=80, tsb=5, acwr=1.8)
    assert rec["ampel"] == "gruen"
    assert rec["strain_korridor"] == (0, 6)
    assert "ACWR" in rec["empfehlung"]


def test_daily_load_recommendation_red() -> None:
    rec = metrics.daily_load_recommendation(recovery_score=20, tsb=0, acwr=1.0)
    assert rec["ampel"] == "rot"
    assert rec["strain_korridor"] == (0, 4)


def test_daily_load_recommendation_green_normal() -> None:
    rec = metrics.daily_load_recommendation(recovery_score=80, tsb=5, acwr=1.0)
    assert rec["ampel"] == "gruen"
    assert rec["strain_korridor"] == (10, 18)


def test_overload_warning_requires_consecutive_days() -> None:
    assert metrics.overload_warning([True, True, True], [True, True, True], consecutive_days=3) is True
    assert metrics.overload_warning([True, False, True], [True, True, True], consecutive_days=3) is False
    assert metrics.overload_warning([True, True], [True, True], consecutive_days=3) is False
