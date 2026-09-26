"""Konfiguration fuer den Trainingsplan (Phase 4). Anpassbar wie die anderen
Config-Dateien - Werte aendern, speichern, dann in der App "Plan neu
erstellen" klicken.
"""

from __future__ import annotations

# Ziel: 5 km unter 20 Minuten.
GOAL_DISTANCE_M = 5000.0
GOAL_TIME_SECONDS = 20 * 60

# Du hast "in 3 oder 4 Wochen" gesagt - wir sind erstmal von 4 Wochen
# ausgegangen (etwas mehr Vorbereitungszeit, geringeres Risiko). Wenn du
# lieber 3 Wochen willst: hier auf 3 setzen und den Plan neu erstellen.
GOAL_WEEKS = 4

# Trainingstage: ISO-Wochentag (1=Montag ... 7=Sonntag) -> Kappung in Minuten
# (None = keine Kappung). Montag ist bewusst nicht enthalten (dein Ruhetag).
TRAINING_WEEKDAYS = {
    2: None,   # Dienstag
    3: 30,     # Mittwoch, max. 30 min
    4: None,   # Donnerstag
    5: None,   # Freitag
    6: None,   # Samstag
    7: None,   # Sonntag
}

# 80/20-Regel: Anteil des Wochenumfangs, der locker (Zone 2) statt hart sein soll.
EASY_INTENSITY_RATIO = 0.80

# Maximale Steigerung des Wochenumfangs (Minuten) gegenueber der Vorwoche.
MAX_WEEKLY_VOLUME_INCREASE = 0.10
