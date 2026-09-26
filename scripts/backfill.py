#!/usr/bin/env python3
"""Importiert die letzten BACKFILL_DAYS Tage (Standard: 90) fuer Baselines.

Voraussetzung: scripts/login.py wurde bereits erfolgreich ausgefuehrt.

Ausfuehren mit:  python3 scripts/backfill.py
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db
from app.garmin_client import GarminAuthError, GarminRateLimitError, RateLimitedGarmin, login

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    db.init_db()

    try:
        garmin = login()
    except (GarminAuthError, GarminRateLimitError) as exc:
        print(f"Login fehlgeschlagen: {exc}")
        print("Bitte zuerst scripts/login.py erfolgreich ausfuehren.")
        return 1

    client = RateLimitedGarmin(garmin)

    date_to = dt.date.today()
    date_from = date_to - dt.timedelta(days=config.BACKFILL_DAYS - 1)

    print(f"Importiere Daten von {date_from} bis {date_to} ({config.BACKFILL_DAYS} Tage) ...")
    from app.sync import run_sync  # spaeter Import, damit login-Fehler frueh auffallen

    run_sync(client, date_from, date_to)
    print("Backfill abgeschlossen. Datenbank liegt unter:", config.DASHBOARD_DB_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
