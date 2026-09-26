"""Duenne, fehlertolerante Huelle um die garminconnect-Bibliothek (>= 0.3).

Grundsaetze:
- Nie automatisch mehrfach einloggen, wenn ein Login fehlschlaegt (Rate-Limit-Schutz).
- Tokens werden lokal in einem Ordner mit restriktiven Rechten (700/600) gespeichert,
  damit ein spaeterer Start ohne erneuten Login (und ohne MFA-Abfrage) funktioniert.
- Jede fetch_*-Methode gibt bei fehlenden Daten None zurueck statt etwas zu raten.
"""

from __future__ import annotations

import logging
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from app import config

logger = logging.getLogger(__name__)


class GarminAuthError(RuntimeError):
    """Login war nicht moeglich (falsche Zugangsdaten, MFA fehlgeschlagen, ...)."""


class GarminRateLimitError(RuntimeError):
    """Garmin hat uns wegen zu vieler Anfragen abgewiesen. Nicht automatisch erneut versuchen."""


def _secure_permissions(path: Path) -> None:
    """Setzt restriktive Dateirechte (nur der Besitzer darf lesen/schreiben)."""
    try:
        os.chmod(path, stat.S_IRWXU)  # 700 fuer Ordner
        if path.is_dir():
            for child in path.glob("*"):
                if child.is_file():
                    os.chmod(child, stat.S_IRUSR | stat.S_IWUSR)  # 600 fuer Dateien
    except OSError as exc:  # z.B. auf Dateisystemen ohne Unix-Rechte
        logger.warning("Konnte Dateirechte fuer %s nicht setzen: %s", path, exc)


def build_client(
    email: str | None = None,
    password: str | None = None,
    prompt_mfa: Callable[[], str] | None = None,
) -> Garmin:
    return Garmin(
        email=email or config.GARMIN_EMAIL,
        password=password or config.GARMIN_PASSWORD,
        prompt_mfa=prompt_mfa,
    )


def login(
    client: Garmin | None = None,
    token_dir: Path | None = None,
    prompt_mfa: Callable[[], str] | None = None,
) -> Garmin:
    """Loggt ein: nutzt zuerst gespeicherte Tokens, faellt sonst auf Email/Passwort zurueck.

    Wirft GarminAuthError bzw. GarminRateLimitError bei Problemen - es wird NICHT
    automatisch erneut versucht.
    """
    token_dir = token_dir or config.GARMIN_TOKEN_DIR
    token_dir.mkdir(parents=True, exist_ok=True)

    garmin = client or build_client(prompt_mfa=prompt_mfa)

    try:
        garmin.login(tokenstore=str(token_dir))
    except GarminConnectTooManyRequestsError as exc:
        raise GarminRateLimitError(
            "Garmin hat zu viele Anfragen abgelehnt (Rate-Limit). "
            "Bitte einige Minuten bis Stunden warten, bevor du es erneut versuchst."
        ) from exc
    except GarminConnectAuthenticationError as exc:
        raise GarminAuthError(f"Garmin-Login fehlgeschlagen: {exc}") from exc
    except GarminConnectConnectionError as exc:
        raise GarminAuthError(f"Verbindung zu Garmin fehlgeschlagen: {exc}") from exc

    _secure_permissions(token_dir)
    return garmin


class RateLimitedGarmin:
    """Wrapper, der zwischen jedem echten API-Call eine kleine Pause einlegt
    und Fehler beim Abruf einzelner Felder abfaengt, statt den ganzen Sync abzubrechen.
    """

    def __init__(self, garmin: Garmin, delay_seconds: float | None = None):
        self._garmin = garmin
        self._delay = (
            delay_seconds if delay_seconds is not None else config.API_CALL_DELAY_SECONDS
        )

    def call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Ruft eine Methode der garminconnect-Bibliothek auf.

        Gibt None zurueck, wenn Garmin fuer diesen Tag/diese Aktivitaet keine Daten hat
        oder der Endpunkt einen Fehler liefert - so bleibt "keine Daten" von "Fehler"
        unterscheidbar in den Logs, aber in der DB landet in beiden Faellen NULL statt
        eines erratenen Werts.
        """
        method = getattr(self._garmin, method_name, None)
        if method is None:
            logger.warning("garminconnect kennt keine Methode '%s'", method_name)
            return None

        time.sleep(self._delay)
        try:
            return method(*args, **kwargs)
        except GarminConnectTooManyRequestsError:
            raise GarminRateLimitError(
                f"Rate-Limit beim Aufruf von {method_name} erreicht. Sync wird abgebrochen."
            )
        except Exception as exc:  # noqa: BLE001 - bewusst breit, einzelner Endpunkt darf scheitern
            logger.info("Kein Ergebnis fuer %s(%s, %s): %s", method_name, args, kwargs, exc)
            return None
