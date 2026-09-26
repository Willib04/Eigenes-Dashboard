#!/usr/bin/env python3
"""Startet das Dashboard und macht es im Heim-WLAN erreichbar (Handy, iPad, ...).

Ausfuehren mit:  python3 scripts/dashboard.py
Beenden mit:     Ctrl+C im Terminal

Mit --no-browser wird kein Browser automatisch geoeffnet (fuer den
launchd-Hintergrunddienst aus dem README, der beim Login startet).
"""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from app import db

HOST = "0.0.0.0"  # auf allen Netzwerk-Interfaces lauschen, nicht nur localhost
PORT = 8000


def _local_ip() -> str | None:
    """Ermittelt die IP-Adresse des Mac im WLAN (fuer den Zugriff vom Handy)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))  # keine echte Verbindung, nur um die Interface-IP zu lesen
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def _open_browser_soon() -> None:
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()


def main() -> int:
    no_browser = "--no-browser" in sys.argv

    db.init_db()
    local_ip = _local_ip()

    print(f"Dashboard auf diesem Mac:  http://127.0.0.1:{PORT}")
    if local_ip:
        print(f"Dashboard vom Handy (im selben WLAN):  http://{local_ip}:{PORT}")
    else:
        print("Konnte die WLAN-IP nicht ermitteln - bist du mit einem Netzwerk verbunden?")
    print(
        "Falls macOS beim ersten Start fragt, ob eingehende Verbindungen erlaubt werden "
        "sollen: 'Erlauben' anklicken."
    )
    print("Beenden mit Ctrl+C")

    if not no_browser:
        _open_browser_soon()

    uvicorn.run("app.web:app", host=HOST, port=PORT, reload=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
