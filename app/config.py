"""Zentrale Konfiguration, geladen aus der .env-Datei."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


GARMIN_EMAIL = os.getenv("GARMIN_EMAIL", "")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD", "")
GARMIN_TOKEN_DIR = _resolve(os.getenv("GARMIN_TOKEN_DIR", "./garmin_tokens"))
DASHBOARD_DB_PATH = _resolve(os.getenv("DASHBOARD_DB_PATH", "./data/dashboard.db"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Berlin")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Wie viele Tage beim allerersten Start importiert werden (Baseline-Aufbau).
BACKFILL_DAYS = int(os.getenv("BACKFILL_DAYS", "90"))

# Pause zwischen einzelnen Garmin-API-Aufrufen, um Rate-Limits zu respektieren.
API_CALL_DELAY_SECONDS = float(os.getenv("API_CALL_DELAY_SECONDS", "0.6"))
