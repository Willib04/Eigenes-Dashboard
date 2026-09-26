from pathlib import Path

from app import db


def test_init_db_creates_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    assert {"daily_metrics", "sleep", "activities", "race_predictions", "sync_log"} <= tables


def test_upsert_and_fetch_one(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        db.upsert(conn, "daily_metrics", {"date": "2024-01-01", "resting_hr": 50, "synced_at": "now"}, "date")

    with db.connect(db_path) as conn:
        row = db.fetch_one(conn, "daily_metrics", "date", "2024-01-01")

    assert row is not None
    assert row["resting_hr"] == 50
    assert row["hrv_avg_ms"] is None  # nicht gesetzte Felder bleiben NULL, nicht erraten


def test_upsert_replaces_existing_row(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        db.upsert(conn, "daily_metrics", {"date": "2024-01-01", "resting_hr": 50, "synced_at": "t1"}, "date")
        db.upsert(conn, "daily_metrics", {"date": "2024-01-01", "resting_hr": 48, "synced_at": "t2"}, "date")

    with db.connect(db_path) as conn:
        row = db.fetch_one(conn, "daily_metrics", "date", "2024-01-01")
        count = conn.execute("SELECT COUNT(*) FROM daily_metrics").fetchone()[0]

    assert row["resting_hr"] == 48
    assert count == 1


def test_fetch_range(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        for day, hr in [("2024-01-01", 50), ("2024-01-02", 51), ("2024-01-05", 52)]:
            db.upsert(conn, "daily_metrics", {"date": day, "resting_hr": hr, "synced_at": "now"}, "date")

    with db.connect(db_path) as conn:
        rows = db.fetch_range(conn, "daily_metrics", "date", "2024-01-01", "2024-01-03")

    assert [r["date"] for r in rows] == ["2024-01-01", "2024-01-02"]
