#!/usr/bin/env python3
"""Zeigt den berechneten Tagesbericht (Recovery, Strain, CTL/ATL/TSB,
Schlafbedarf, Empfehlung) fuer ein Datum an. Liest nur aus der lokalen
Datenbank - kein Garmin-Login noetig.

Ausfuehren mit:  python3 scripts/report.py [YYYY-MM-DD]
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db
from app.report import build_daily_report


def _fmt(value: object) -> str:
    return "keine Daten" if value is None else str(value)


def main() -> int:
    target_date = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()

    db.init_db()
    with db.connect() as conn:
        report = build_daily_report(conn, target_date)

    print(f"=== Bericht fuer {report['date']} ===\n")

    print(f"Recovery: {_fmt(report['recovery_score'])} % ({report['recovery_ampel']})")
    for name, value in report["recovery_components"].items():
        print(f"  - {name}: {_fmt(value)}")

    print(f"\nStrain heute: {_fmt(report['strain_heute'])} / 21 (TRIMP: {_fmt(report['trimp_heute'])})")
    print(f"Garmin Training Load heute: {_fmt(report['garmin_training_load_heute'])}")

    print(f"\nCTL (Fitness, 42T): {_fmt(report['ctl'])}")
    print(f"ATL (Ermuedung, 7T): {_fmt(report['atl'])}")
    print(f"TSB (Form): {_fmt(report['tsb'])}")
    print(f"ACWR: {_fmt(report['acwr'])} ({_fmt(report['acwr_flag'])})")

    print(f"\nSchlaf letzte Nacht: {_fmt(report['schlaf_letzte_nacht_stunden'])} h")
    print(f"Schlafbedarf letzte Nacht: {_fmt(report['schlafbedarf_letzte_nacht_stunden'])} h")

    need = report["schlafbedarf_heute_nacht"]
    print(f"\nSchlafbedarf heute Nacht: {need['sleep_need_hours']} h")
    print(f"  Grundbedarf: {need['base_need_hours']} h")
    print(f"  + Strain-Aufschlag: {need['strain_surcharge_hours']} h")
    print(f"  + Schlafschuld-Abbau: {need['debt_repayment_hours']} h")
    print(f"  - Nickerchen: {need['nap_hours']} h")
    print(f"Empfohlene Zubettgehzeit: {report['empfohlene_zubettgehzeit']}")

    rec = report["empfehlung_heute"]
    print(f"\nEmpfehlung heute ({rec['ampel']}): {rec['empfehlung']}")
    if rec["strain_korridor"]:
        print(f"Ziel-Strain-Korridor: {rec['strain_korridor'][0]}-{rec['strain_korridor'][1]}")

    if report["warnsignal_ueberlastung"]:
        print(
            "\nHinweis: HRV liegt seit mehreren Tagen unter deiner Baseline und der Ruhepuls "
            "gleichzeitig darueber. Das KANN auf beginnende Ueberlastung oder einen Infekt "
            "hindeuten - ist aber keine Diagnose. Beobachte es und erhole dich, falls du dich "
            "auch subjektiv nicht fit fuehlst."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
