import datetime as dt
from pathlib import Path

import pytest

from app import db, plan


def test_goal_paces_20min_5k() -> None:
    # 20:00 fuer 5 km = exakt 4:00 min/km Zielpace
    paces = plan.goal_paces(20 * 60, 5000)
    assert paces["race"] == "4:00"
    # Intervallpace schneller, Schwellenpace langsamer als Zielpace
    assert paces["interval"] < paces["race"]
    assert paces["threshold"] > paces["race"]


def test_generate_plan_creates_four_weeks_without_past_dates(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    start = dt.date(2024, 3, 12)  # ein Dienstag

    with db.connect(db_path) as conn:
        plan_id = plan.generate_plan(conn, start_date=start, goal_weeks=4)

    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM planned_workouts WHERE plan_id = ? ORDER BY date", (plan_id,)
        ).fetchall()
        active = plan.get_active_plan(conn)

    assert active is not None
    assert active["id"] == plan_id
    assert active["goal_distance_m"] == 5000.0

    dates = [r["date"] for r in rows]
    assert min(dates) >= start.isoformat()
    # 4 Wochen x 6 Trainingstage = 24 Eintraege (Montag nicht enthalten)
    assert len(rows) == 24

    phases = {r["week_number"]: r["phase"] for r in rows}
    assert phases[0] == "schaerfung"
    assert phases[1] == "schaerfung"
    assert phases[2] == "entlastung"
    assert phases[3] == "taper"

    # Der Wettkampftag ist der letzte Sonntag
    race_rows = [r for r in rows if r["workout_type"] == "race"]
    assert len(race_rows) == 1
    assert dt.date.fromisoformat(race_rows[0]["date"]).isoweekday() == 7


def test_generate_plan_skips_dates_before_start(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    # Start mitten in der Woche (Donnerstag) -> Dienstag/Mittwoch dieser Woche fallen weg
    start = dt.date(2024, 3, 14)

    with db.connect(db_path) as conn:
        plan_id = plan.generate_plan(conn, start_date=start, goal_weeks=3)
        rows = conn.execute(
            "SELECT date FROM planned_workouts WHERE plan_id = ? AND week_number = 0", (plan_id,)
        ).fetchall()

    assert all(dt.date.fromisoformat(r["date"]) >= start for r in rows)
    assert len(rows) == 4  # Do, Fr, Sa, So dieser ersten Woche


def test_generate_plan_deactivates_previous_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        first_id = plan.generate_plan(conn, start_date=dt.date(2024, 3, 12), goal_weeks=3)
        second_id = plan.generate_plan(conn, start_date=dt.date(2024, 3, 12), goal_weeks=4)

    with db.connect(db_path) as conn:
        first = conn.execute("SELECT is_active FROM training_plan WHERE id = ?", (first_id,)).fetchone()
        second = conn.execute("SELECT is_active FROM training_plan WHERE id = ?", (second_id,)).fetchone()

    assert first["is_active"] == 0
    assert second["is_active"] == 1


def test_plan_with_status_marks_erledigt_verpasst_geplant(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    start = dt.date(2024, 3, 12)  # Dienstag

    with db.connect(db_path) as conn:
        plan_id = plan.generate_plan(conn, start_date=start, goal_weeks=3)
        # Dienstag (12.3., Intervalle) wurde tatsaechlich gelaufen
        db.upsert(
            conn, "activities",
            {"activity_id": 1, "date": "2024-03-12", "activity_type": "running",
             "duration_seconds": 2000, "synced_at": "test"},
            "activity_id",
        )
        today = dt.date(2024, 3, 14)  # Donnerstag: Di ist erledigt, Mi verpasst, Do ist "heute"
        statuses = {w["date"]: w["status"] for w in plan.plan_with_status(conn, plan_id, today)}

    assert statuses["2024-03-12"] == "erledigt"
    assert statuses["2024-03-13"] == "verpasst"
    assert statuses["2024-03-14"] == "heute"
    assert statuses["2024-03-15"] == "geplant"


def test_weekly_fulfillment_excludes_rest_days(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    start = dt.date(2024, 3, 12)

    with db.connect(db_path) as conn:
        plan_id = plan.generate_plan(conn, start_date=start, goal_weeks=3)
        db.upsert(
            conn, "activities",
            {"activity_id": 1, "date": "2024-03-12", "activity_type": "running",
             "duration_seconds": 2000, "synced_at": "test"},
            "activity_id",
        )
        fulfillment = plan.weekly_fulfillment(conn, plan_id, today=dt.date(2024, 3, 19))

    week0 = next(w for w in fulfillment if w["week_number"] == 0)
    assert week0["geplant"] == 6  # 6 Trainingstage, kein Ruhetag in Schaerfungswoche
    assert week0["erledigt"] == 1
    assert week0["quote_prozent"] == round(100 / 6)


def test_today_workout_with_override_adds_alternative_on_red_recovery(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    start = dt.date(2024, 3, 12)  # Dienstag -> Intervalle (harte Einheit)

    with db.connect(db_path) as conn:
        plan.generate_plan(conn, start_date=start, goal_weeks=3)
        entry_red = plan.today_workout_with_override(conn, "rot", today=start)
        entry_green = plan.today_workout_with_override(conn, "gruen", today=start)

    assert "alternative_wegen_recovery" in entry_red
    assert "alternative_wegen_recovery" not in entry_green
    # Der Plan selbst bleibt unveraendert (workout_type nicht ueberschrieben)
    assert entry_red["workout_type"] == "intervals"


def test_today_workout_with_override_no_alternative_for_easy_or_rest(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    start = dt.date(2024, 3, 12)

    with db.connect(db_path) as conn:
        plan.generate_plan(conn, start_date=start, goal_weeks=3)
        # Mittwoch = "easy" -> auch bei rot keine Alternative noetig
        entry = plan.today_workout_with_override(conn, "rot", today=dt.date(2024, 3, 13))

    assert "alternative_wegen_recovery" not in entry


def test_build_running_workout_has_warmup_main_cooldown() -> None:
    row = {"title": "Testeinheit", "description": "Beschreibung", "target_duration_minutes": 45}
    workout = plan.build_running_workout(row)

    assert workout.workoutName == "Testeinheit"
    assert workout.estimatedDurationInSecs == 45 * 60
    steps = workout.workoutSegments[0].workoutSteps
    assert len(steps) == 3  # warmup, interval, cooldown bei > 15 min


def test_build_running_workout_short_workout_has_no_warmup_cooldown() -> None:
    row = {"title": "Kurz", "description": "Kurze Einheit", "target_duration_minutes": 10}
    workout = plan.build_running_workout(row)
    steps = workout.workoutSegments[0].workoutSteps
    assert len(steps) == 1


class _FakeGarminUpload:
    def __init__(self) -> None:
        self.uploaded = None
        self.scheduled = None

    def upload_running_workout(self, workout):
        self.uploaded = workout
        return {"workoutId": 999}

    def schedule_workout(self, workout_id, date_str):
        self.scheduled = (workout_id, date_str)


def test_send_workout_to_garmin_updates_db_and_calls_client(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    start = dt.date(2024, 3, 12)
    fake = _FakeGarminUpload()

    with db.connect(db_path) as conn:
        plan_id = plan.generate_plan(conn, start_date=start, goal_weeks=3)
        workout_row = conn.execute(
            "SELECT id FROM planned_workouts WHERE plan_id = ? ORDER BY date LIMIT 1", (plan_id,)
        ).fetchone()
        result = plan.send_workout_to_garmin(conn, fake, workout_row["id"])

    assert result["garmin_workout_id"] == 999
    assert fake.scheduled == (999, start.isoformat())

    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT sent_to_garmin_at, garmin_workout_id FROM planned_workouts WHERE id = ?",
            (workout_row["id"],),
        ).fetchone()
    assert row["sent_to_garmin_at"] is not None
    assert row["garmin_workout_id"] == "999"


def test_send_workout_to_garmin_rejects_rest_day(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    start = dt.date(2024, 3, 12)

    with db.connect(db_path) as conn:
        plan_id = plan.generate_plan(conn, start_date=start, goal_weeks=4)  # 4 Wochen -> Taper hat Ruhetag
        rest_row = conn.execute(
            "SELECT id FROM planned_workouts WHERE plan_id = ? AND workout_type = 'rest' LIMIT 1", (plan_id,)
        ).fetchone()
        with pytest.raises(ValueError):
            plan.send_workout_to_garmin(conn, _FakeGarminUpload(), rest_row["id"])
