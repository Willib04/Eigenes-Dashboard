-- SQLite-Schema fuer das persoenliche Sport-Dashboard.
-- Grundsatz: fehlt ein Wert bei Garmin, bleibt das Feld NULL ("keine Daten"),
-- es wird nichts geschaetzt oder erfunden. raw_json bewahrt die komplette
-- Rohantwort auf, damit spaeter nachvollziehbar bleibt, was Garmin geliefert hat.

CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,                 -- YYYY-MM-DD

    resting_hr INTEGER,

    hrv_avg_ms REAL,                       -- Nacht-Durchschnitt rMSSD in ms
    hrv_status TEXT,                       -- BALANCED, UNBALANCED, LOW, ...
    hrv_weekly_avg_ms REAL,
    hrv_baseline_low_ms REAL,
    hrv_baseline_high_ms REAL,

    body_battery_max INTEGER,
    body_battery_min INTEGER,
    body_battery_charged INTEGER,
    body_battery_drained INTEGER,

    stress_avg INTEGER,
    stress_max INTEGER,

    respiration_avg REAL,
    respiration_sleep_avg REAL,

    spo2_avg REAL,
    spo2_min REAL,

    steps INTEGER,
    intensity_minutes_moderate INTEGER,
    intensity_minutes_vigorous INTEGER,

    vo2max_running REAL,
    vo2max_cycling REAL,

    training_status TEXT,
    training_readiness_score INTEGER,
    training_readiness_level TEXT,

    weight_kg REAL,

    raw_json TEXT,
    synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sleep (
    date TEXT PRIMARY KEY,                 -- Kalendertag des Aufwachens

    bedtime_utc TEXT,
    wake_time_utc TEXT,

    total_sleep_seconds INTEGER,
    deep_sleep_seconds INTEGER,
    light_sleep_seconds INTEGER,
    rem_sleep_seconds INTEGER,
    awake_seconds INTEGER,

    sleep_score INTEGER,
    sleep_score_qualifier TEXT,

    avg_sleep_hrv_ms REAL,
    avg_sleep_stress INTEGER,
    respiration_avg_sleep REAL,
    spo2_avg_sleep REAL,

    raw_json TEXT,
    synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    start_time_utc TEXT,

    activity_type TEXT,
    name TEXT,

    duration_seconds REAL,
    distance_m REAL,

    avg_hr INTEGER,
    max_hr INTEGER,

    avg_pace_min_per_km REAL,
    avg_power_w REAL,
    normalized_power_w REAL,

    calories REAL,
    elevation_gain_m REAL,

    training_effect_aerobic REAL,
    training_effect_anaerobic REAL,
    training_load REAL,

    hr_zone_1_seconds REAL,
    hr_zone_2_seconds REAL,
    hr_zone_3_seconds REAL,
    hr_zone_4_seconds REAL,
    hr_zone_5_seconds REAL,

    raw_json TEXT,
    synced_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date);

CREATE TABLE IF NOT EXISTS race_predictions (
    date TEXT PRIMARY KEY,
    time_5k_seconds INTEGER,
    time_10k_seconds INTEGER,
    time_half_marathon_seconds INTEGER,
    time_marathon_seconds INTEGER,
    raw_json TEXT,
    synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    date_from TEXT,
    date_to TEXT,
    status TEXT NOT NULL,                  -- running, success, failed
    error TEXT
);
