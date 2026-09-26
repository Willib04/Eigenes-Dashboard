"""Konfiguration fuer die berechneten Kennzahlen (Phase 3).

Alle Werte hier sind einfache Zahlen zum Anpassen - kein Programmierwissen
noetig, nur die Zahl aendern und die Datei speichern. Nach einer Aenderung
wirkt sie sich beim naechsten Lauf des Report-Skripts / Dashboards aus.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Persoenliche Eckwerte
# ---------------------------------------------------------------------------

AGE = 22
WEIGHT_KG = 64.0
SEX = "male"  # "male" oder "female" - beeinflusst den Exponenten in der TRIMP-Formel

# Maximale Herzfrequenz (HFmax). Dein bisher hoechster gemessener Puls war
# 195 (17.09.2026, Laufen) - hoeher als die Tanaka-Schaetzformel
# (208 - 0.7 x Alter = 193). Wir nehmen den hoeheren, echten Wert, weil ein
# tatsaechlich erreichter Puls immer aussagekraeftiger ist als eine
# Bevoelkerungsformel. Falls du spaeter (z.B. bei einem harten Wettkampf
# oder einem echten Maximaltest) einen hoeheren Puls erreichst, den Wert
# hier einfach erhoehen.
HF_MAX = 195

WAKE_TIME_WEEKDAY = "06:30"
WAKE_TIME_WEEKEND = "08:30"

# ---------------------------------------------------------------------------
# Baselines (Phase 3.1)
# ---------------------------------------------------------------------------

BASELINE_WINDOWS_DAYS = (7, 28)
# Mindestanzahl echter Messwerte im Fenster, damit eine Baseline berechnet wird.
# Sonst "keine Daten" statt einer Baseline aus zu wenigen Punkten.
BASELINE_MIN_POINTS = {7: 4, 28: 10}

# ---------------------------------------------------------------------------
# Recovery-Score (Phase 3.2)
# ---------------------------------------------------------------------------

# Muss in Summe 1.0 ergeben. HRV hat den groessten Anteil (siehe Aufgabenstellung).
RECOVERY_WEIGHTS = {
    "hrv": 0.5,
    "resting_hr": 0.2,
    "sleep": 0.2,
    "respiration": 0.1,
}

# Welche Baseline-Fensterlaenge fuer die Recovery-Berechnung verwendet wird.
RECOVERY_BASELINE_WINDOW_DAYS = 28

RECOVERY_GREEN_MIN = 67
RECOVERY_YELLOW_MIN = 34
# < RECOVERY_YELLOW_MIN => rot

# ---------------------------------------------------------------------------
# Strain / TRIMP (Phase 3.3)
# ---------------------------------------------------------------------------

STRAIN_SCALE_MAX = 21.0
# Kalibrierungskonstante fuer die logarithmische TRIMP -> 0-21 Abbildung.
# Groesserer Wert = du musst mehr TRIMP sammeln, um die gleiche Strain-Zahl
# zu erreichen. Kann spaeter anhand deines subjektiven Belastungsgefuehls
# nachjustiert werden.
STRAIN_TRIMP_SCALE_K = 75.0

# ---------------------------------------------------------------------------
# CTL/ATL/TSB/ACWR (Phase 3.4)
# ---------------------------------------------------------------------------

CTL_WINDOW_DAYS = 42
ATL_WINDOW_DAYS = 7

ACWR_ACUTE_DAYS = 7
ACWR_CHRONIC_DAYS = 28
ACWR_HIGH_WARNING = 1.5
ACWR_LOW_HINT = 0.8

# ---------------------------------------------------------------------------
# Schlafbedarf (Phase 3.5)
# ---------------------------------------------------------------------------

BASE_SLEEP_NEED_HOURS = 8.0
# Maximaler Aufschlag (Minuten) bei maximalem Strain (21) des Vortages.
SLEEP_STRAIN_SURCHARGE_MAX_MINUTES = 60.0
# Welcher Anteil der über die letzten 7 Naechte aufgelaufenen Schlafschuld
# heute Nacht "abgebaut" wird (0.15 = 15% der Gesamtschuld pro Nacht).
SLEEP_DEBT_REPAYMENT_FRACTION = 0.15
SLEEP_DEBT_WINDOW_DAYS = 7

# ---------------------------------------------------------------------------
# Warnsignale (Phase 3.8)
# ---------------------------------------------------------------------------

WARNING_CONSECUTIVE_DAYS = 3  # so viele Tage in Folge HRV<Baseline UND RHR>Baseline
