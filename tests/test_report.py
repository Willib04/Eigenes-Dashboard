import datetime as dt
from pathlib import Path

from app import db
from app.report import build_daily_report

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
