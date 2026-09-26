#!/usr/bin/env python3
"""Taeglicher Sync: holt die letzten 3 Tage neu (Garmin finalisiert Schlaf/HRV
oft erst mit Verzoegerung) und schreibt sie in die lokale Datenbank.

Gedacht zum 1-2x taeglichen Ausfuehren per launchd/cron, NICHT haeufiger
(siehe README fuer die Einrichtung unter macOS).

Ausfuehren mit:  python3 scripts/sync_daily.py
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db
from app.garmin_client import GarminAuthError, GarminRateLimitError, RateLimitedGarmin, login
from app.sync import run_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

LOOKBACK_DAYS = 3


def main() -> int:
    db.init_db()

    try:
        garmin = login()
    except (GarminAuthError, GarminRateLimitError) as exc:
        logging.error("Login fehlgeschlagen: %s", exc)
        return 1

    client = RateLimitedGarmin(garmin)

    date_to = dt.date.today()
    date_from = date_to - dt.timedelta(days=LOOKBACK_DAYS - 1)

    run_sync(client, date_from, date_to)
    logging.info("Sync abgeschlossen: %s bis %s", date_from, date_to)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
