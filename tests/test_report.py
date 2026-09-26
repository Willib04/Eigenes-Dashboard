import datetime as dt
from pathlib import Path

from app import db
from app.report import build_daily_report, build_load_history, build_recovery_history, build_trends

DAYS = 35


def _seed(db_path: Path) -> dt.date:
    db.init_db(db_path)
    today = dt.date(2024, 3, 10)

    with db.connect(db_path) as conn:
        for i in range(DAYS):
            day = today - dt.timedelta(days=DAYS - 1 - i)
            date_str = day.isoformat()
            db.upsert(
                conn,
                "daily_metrics",
                {
                    "date": date_str,
                    "resting_hr": 50 + (i % 3),
                    "hrv_avg_ms": 45.0 + (i % 5),
                    "respiration_avg": 13.5,
                    "synced_at": "test",
                },
                "date",
            )
            db.upsert(
                conn,
                "sleep",
                {
                    "date": date_str,
                    "total_sleep_seconds": int(7.5 * 3600),
                    # 22:30 Europe/Berlin (Winterzeit, +01:00) an jedem Tag -> Konsistenz-Test unten
                    "bedtime_utc": f"{date_str}T21:30:00+00:00",
                    "synced_at": "test",
                },
                "date",
            )
            # Jeden dritten Tag eine Laufaktivitaet
            if i % 3 == 0:
                db.upsert(
                    conn,
                    "activities",
                    {
                        "activity_id": 1000 + i,
                        "date": date_str,
                        "activity_type": "running",
                        "duration_seconds": 1800,
                        "avg_hr": 150,
                        "training_load": 80,
                        "synced_at": "test",
                    },
                    "activity_id",
                )
    return today


def test_build_daily_report_runs_without_error_on_realistic_history(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    today = _seed(db_path)

    with db.connect(db_path) as conn:
        report = build_daily_report(conn, today)

    assert report["date"] == today.isoformat()
    # Nach 34 Tagen Vorlauf sollte die 28-Tage-Baseline vorhanden sein
    assert report["recovery_score"] is not None
    assert 0 <= report["recovery_score"] <= 100
    assert report["recovery_ampel"] in ("gruen", "gelb", "rot")

    assert report["tsb"] is not None
    assert report["acwr"] is not None

    need = report["schlafbedarf_heute_nacht"]
    assert need["sleep_need_hours"] > 0

    assert report["empfohlene_zubettgehzeit"].count(":") == 1
    assert report["empfehlung_heute"]["ampel"] in ("gruen", "gelb", "rot")


def test_build_daily_report_handles_missing_data_gracefully(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        report = build_daily_report(conn, dt.date(2024, 3, 10))

    # Komplett leere DB -> "keine Daten" statt Fehler oder erratenen Werten
    assert report["recovery_score"] is None
    assert report["recovery_ampel"] == "keine Daten"
    # Kein Aktivitaets-Log an dem Tag ist eine echte Aussage (Ruhetag -> Strain 0.0),
    # kein fehlender Wert - anders als z.B. der Recovery-Score, der echte Messdaten braucht.
    assert report["strain_heute"] == 0.0
    assert report["schlafbedarf_heute_nacht"]["sleep_need_hours"] > 0


def test_build_trends_returns_series_and_consistent_bedtime(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    today = _seed(db_path)

    with db.connect(db_path) as conn:
        trends = build_trends(conn, weeks=4, end_date=today)

    assert len(trends["hrv"]) == 28
    assert len(trends["resting_hr"]) == 28
    assert trends["hrv"][-1]["value"] is not None
    # Immer 22:30 Bettzeit im Testdatensatz -> keine Schwankung
    assert trends["sleep_consistency_minutes"] == 0.0
    assert len(trends["body_battery_max"]) == 28
    assert len(trends["stress_avg"]) == 28


def test_build_trends_handles_empty_database(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        trends = build_trends(conn, weeks=2, end_date=dt.date(2024, 3, 10))

    assert len(trends["hrv"]) == 14
    assert all(point["value"] is None for point in trends["hrv"])
    assert trends["sleep_consistency_minutes"] is None


def test_build_load_history_returns_one_row_per_day(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    today = _seed(db_path)

    with db.connect(db_path) as conn:
        history = build_load_history(conn, days=14, end_date=today)

    assert len(history) == 14
    assert history[-1]["date"] == today.isoformat()
    assert history[-1]["ctl"] is not None
    assert history[-1]["tsb"] is not None
    # Am letzten Tag (i=34, kein Aktivitaets-Log, da 34 % 3 != 0) ist Strain 0.0, nicht None
    assert history[-1]["strain"] == 0.0


def test_build_recovery_history_returns_one_entry_per_day(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    today = _seed(db_path)

    with db.connect(db_path) as conn:
        history = build_recovery_history(conn, weeks=2, end_date=today)

    assert len(history) == 14
    assert history[-1]["date"] == today.isoformat()
    assert history[-1]["recovery_score"] is not None
    assert history[-1]["recovery_ampel"] in ("gruen", "gelb", "rot")
