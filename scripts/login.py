#!/usr/bin/env python3
"""Einmaliger interaktiver Login bei Garmin Connect (mit MFA-Unterstuetzung).

Danach liegen die Login-Tokens im Ordner GARMIN_TOKEN_DIR (siehe .env) und
kuenftige Sync-Laeufe (scripts/sync_daily.py, scripts/backfill.py) brauchen
keinen erneuten Login mehr - solange die Tokens gueltig bleiben.

Ausfuehren mit:  python3 scripts/login.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config
from app.garmin_client import GarminAuthError, GarminRateLimitError, login


def _prompt_mfa() -> str:
    return input("Bitte den MFA-Code eingeben, den du von Garmin erhalten hast: ").strip()


def main() -> int:
    if not config.GARMIN_EMAIL or not config.GARMIN_PASSWORD:
        print(
            "GARMIN_EMAIL / GARMIN_PASSWORD fehlen. Bitte zuerst .env.example zu .env "
            "kopieren und deine Zugangsdaten eintragen."
        )
        return 1

    print(f"Logge ein als {config.GARMIN_EMAIL} ...")
    try:
        login(prompt_mfa=_prompt_mfa)
    except GarminRateLimitError as exc:
        print(f"Rate-Limit: {exc}")
        return 1
    except GarminAuthError as exc:
        print(f"Login fehlgeschlagen: {exc}")
        return 1

    print(f"Login erfolgreich. Tokens gespeichert in: {config.GARMIN_TOKEN_DIR}")
    print("Du kannst jetzt scripts/backfill.py fuer den 90-Tage-Import ausfuehren.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
