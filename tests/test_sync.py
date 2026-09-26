import datetime as dt
from pathlib import Path

from app import db, sync

# ---------------------------------------------------------------------------
# Beispiel-Rohantworten, angelehnt an die bekannte Struktur der Garmin-Connect-API.
# Falls Garmin bei dir abweichende Feldnamen liefert (das passiert je nach
# Uhr/Firmware), zeigt raw_json in der DB die echte Antwort - das Mapping
# unten kann dann leicht nachgezogen werden, ohne dass alte Daten verloren gehen.
# ---------------------------------------------------------------------------

STATS_FIXTURE = {
    "restingHeartRate": 52,
    "bodyBatteryHighestValue": 85,
    "bodyBatteryLowestValue": 20,
    "bodyBatteryChargedValue": 70,
    "bodyBatteryDrainedValue": 65,
    "averageStressLevel": 25,
    "maxStressLevel": 60,
    "avgWakingRespirationValue": 14.5,
    "averageSpo2": 97.0,
    "lowestSpo2": 94.0,
    "totalSteps": 8500,
    "moderateIntensityMinutes": 30,
    "vigorousIntensityMinutes": 10,
}

HRV_FIXTURE = {
    "hrvSummary": {
        "weeklyAvg": 45.0,
        "lastNightAvg": 48.0,
        "status": "BALANCED",
        "baseline": {"balancedLow": 40.0, "balancedUpper": 55.0},
    }
}

TRAINING_READINESS_FIXTURE = [{"score": 72, "level": "MODERATE"}]

TRAINING_STATUS_FIXTURE = {
    "mostRecentVO2Max": {
        "generic": {"vo2MaxValue": 52.0},
        "cycling": {"vo2MaxValue": 48.0},
    },
    "mostRecentTrainingStatus": {
        "latestTrainingStatusData": {
            "1234": {"trainingStatusFeedbackPhrase": "PRODUCTIVE"}
        }
    },
}

SLEEP_FIXTURE = {
    "dailySleepDTO": {
        "sleepTimeSeconds": 7 * 3600,
        "deepSleepSeconds": 1 * 3600,
        "lightSleepSeconds": 4 * 3600,
        "remSleepSeconds": 1.5 * 3600,
        "awakeSleepSeconds": 0.5 * 3600,
        "sleepStartTimestampGMT": 1704085200000,  # 2024-01-01 09:00:00 UTC (Beispielwert)
        "sleepEndTimestampGMT": 1704110400000,
        "sleepScores": {"overall": {"value": 82, "qualifierKey": "GOOD"}},
        "avgOvernightHrv": 47.0,
        "avgSleepStress": 15,
    },
    "avgSleepRespirationValue": 13.8,
    "averageSpO2Value": 96.0,
}

RACE_PREDICTIONS_FIXTURE = {
    "calendarDate": "2024-01-01",
    "time5K": 1190,
    "time10K": 2480,
    "timeHalfMarathon": 5600,
    "timeMarathon": 12000,
}

ACTIVITY_FIXTURE = {
    "activityId": 987654321,
    "startTimeLocal": "2024-01-02 07:15:00",
    "startTimeGMT": "2024-01-02 06:15:00",
    "activityType": {"typeKey": "running"},
    "activityName": "Morgenlauf",
    "duration": 1800.0,
    "distance": 5000.0,
    "averageHR": 155,
    "maxHR": 172,
    "averageSpeed": 2.78,  # m/s
    "calories": 350,
    "elevationGain": 45.0,
    "aerobicTrainingEffect": 3.2,
    "anaerobicTrainingEffect": 1.1,
    "activityTrainingLoad": 180.0,
}

HR_ZONES_FIXTURE = [
    {"zoneNumber": 1, "secsInZone": 120.0},
    {"zoneNumber": 2, "secsInZone": 900.0},
    {"zoneNumber": 3, "secsInZone": 600.0},
    {"zoneNumber": 4, "secsInZone": 150.0},
    {"zoneNumber": 5, "secsInZone": 30.0},
]


def test_map_daily_metrics_maps_known_fields() -> None:
    row = sync.map_daily_metrics(
        "2024-01-01", STATS_FIXTURE, HRV_FIXTURE, TRAINING_READINESS_FIXTURE, TRAINING_STATUS_FIXTURE, 64.2,
        SLEEP_FIXTURE,
    )

    assert row["date"] == "2024-01-01"
    assert row["resting_hr"] == 52
    assert row["hrv_avg_ms"] == 48.0
    assert row["hrv_status"] == "BALANCED"
    assert row["hrv_baseline_low_ms"] == 40.0
    assert row["body_battery_max"] == 85
    assert row["vo2max_running"] == 52.0
    assert row["respiration_sleep_avg"] == 13.8
    assert row["vo2max_cycling"] == 48.0
    assert row["training_status"] == "PRODUCTIVE"
    assert row["training_readiness_score"] == 72
    assert row["training_readiness_level"] == "MODERATE"
    assert row["weight_kg"] == 64.2


def test_map_daily_metrics_missing_data_is_none_not_guessed() -> None:
    row = sync.map_daily_metrics("2024-01-01", None, None, None, None, None)

    assert row["resting_hr"] is None
    assert row["hrv_avg_ms"] is None
    assert row["vo2max_running"] is None
    assert row["training_readiness_score"] is None
    assert row["weight_kg"] is None


def test_map_sleep_maps_known_fields() -> None:
    row = sync.map_sleep("2024-01-01", SLEEP_FIXTURE)

    assert row is not None
    assert row["total_sleep_seconds"] == 7 * 3600
    assert row["deep_sleep_seconds"] == 3600
    assert row["sleep_score"] == 82
    assert row["sleep_score_qualifier"] == "GOOD"
    assert row["avg_sleep_hrv_ms"] == 47.0
    assert row["bedtime_utc"] is not None
    assert row["wake_time_utc"] is not None


def test_map_sleep_returns_none_without_daily_dto() -> None:
    assert sync.map_sleep("2024-01-01", None) is None
    assert sync.map_sleep("2024-01-01", {}) is None


def test_map_race_predictions() -> None:
    row = sync.map_race_predictions(RACE_PREDICTIONS_FIXTURE)

    assert row is not None
    assert row["date"] == "2024-01-01"
    assert row["time_5k_seconds"] == 1190
    assert row["time_marathon_seconds"] == 12000


def test_map_race_predictions_without_date_returns_none() -> None:
    entry = {k: v for k, v in RACE_PREDICTIONS_FIXTURE.items() if k != "calendarDate"}
    assert sync.map_race_predictions(entry) is None
    assert sync.map_race_predictions(None) is None


def test_extract_race_prediction_entries_handles_list_and_wrapped_dict() -> None:
    assert sync._extract_race_prediction_entries([RACE_PREDICTIONS_FIXTURE]) == [RACE_PREDICTIONS_FIXTURE]
    assert sync._extract_race_prediction_entries(
        {"racePredictions": [RACE_PREDICTIONS_FIXTURE]}
    ) == [RACE_PREDICTIONS_FIXTURE]
    assert sync._extract_race_prediction_entries(RACE_PREDICTIONS_FIXTURE) == [RACE_PREDICTIONS_FIXTURE]
    assert sync._extract_race_prediction_entries(None) == []
    assert sync._extract_race_prediction_entries({"unrelated": True}) == []


def test_map_activity_and_pace_conversion() -> None:
    row = sync.map_activity(ACTIVITY_FIXTURE)

    assert row is not None
    assert row["activity_id"] == 987654321
    assert row["date"] == "2024-01-02"
    assert row["activity_type"] == "running"
    assert row["distance_m"] == 5000.0
    # 2.78 m/s -> ca. 5:59 min/km
    assert 5.9 < row["avg_pace_min_per_km"] < 6.05


def test_map_activity_without_start_time_returns_none() -> None:
    broken = dict(ACTIVITY_FIXTURE)
    broken.pop("startTimeLocal")
    broken.pop("startTimeGMT")
    assert sync.map_activity(broken) is None


def test_apply_hr_zones() -> None:
    row = {f"hr_zone_{i}_seconds": None for i in range(1, 6)}
    row = sync.apply_hr_zones(row, HR_ZONES_FIXTURE)

    assert row["hr_zone_1_seconds"] == 120.0
    assert row["hr_zone_5_seconds"] == 30.0


class _FakeGarmin:
    """Stellt garminconnect-Methoden nach, ohne echte Netzwerkaufrufe zu machen."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_stats(self, cdate: str) -> dict:
        self.calls.append(f"get_stats:{cdate}")
        return STATS_FIXTURE

    def get_hrv_data(self, cdate: str) -> dict:
        return HRV_FIXTURE

    def get_training_readiness(self, cdate: str) -> list:
        return TRAINING_READINESS_FIXTURE

    def get_training_status(self, cdate: str) -> dict:
        return TRAINING_STATUS_FIXTURE

    def get_sleep_data(self, cdate: str) -> dict:
        return SLEEP_FIXTURE

    def get_race_predictions(self, startdate: str, enddate: str, _type: str) -> list:
        return [{**RACE_PREDICTIONS_FIXTURE, "calendarDate": startdate}]

    def get_daily_weigh_ins(self, cdate: str) -> dict:
        return {"dateWeightList": [{"weight": 64200}]}

    def get_activities_by_date(self, startdate: str, enddate: str) -> list:
        return [ACTIVITY_FIXTURE]

    def get_activity_hr_in_timezones(self, activity_id: int) -> list:
        return HR_ZONES_FIXTURE


def test_run_sync_end_to_end(tmp_path: Path) -> None:
    from app.garmin_client import RateLimitedGarmin

    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    client = RateLimitedGarmin(_FakeGarmin(), delay_seconds=0)

    day = dt.date(2024, 1, 2)
    sync.run_sync(client, day, day, db_path=db_path)

    with db.connect(db_path) as conn:
        daily = db.fetch_one(conn, "daily_metrics", "date", "2024-01-02")
        sleep_row = db.fetch_one(conn, "sleep", "date", "2024-01-02")
        activity = db.fetch_one(conn, "activities", "activity_id", 987654321)
        prediction = db.fetch_one(conn, "race_predictions", "date", "2024-01-02")
        log_row = conn.execute("SELECT status FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()

    assert daily is not None
    assert daily["resting_hr"] == 52
    assert daily["weight_kg"] == 64.2
    assert prediction is not None
    assert prediction["time_5k_seconds"] == 1190
    assert sleep_row is not None
    assert activity is not None
    assert activity["hr_zone_2_seconds"] == 900.0
    assert log_row["status"] == "success"
