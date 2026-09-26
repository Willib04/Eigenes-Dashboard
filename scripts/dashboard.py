#!/usr/bin/env python3
"""Startet das Dashboard lokal und oeffnet es im Standard-Browser.

Ausfuehren mit:  python3 scripts/dashboard.py
Beenden mit:     Ctrl+C im Terminal
"""

from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from app import db

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def _open_browser_soon() -> None:
    threading.Timer(1.0, lambda: webbrowser.open(URL)).start()


def main() -> int:
    db.init_db()
    print(f"Dashboard startet unter {URL} (im Browser oeffnen, falls er nicht automatisch aufgeht)")
    print("Beenden mit Ctrl+C")
    _open_browser_soon()
    uvicorn.run("app.web:app", host=HOST, port=PORT, reload=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
