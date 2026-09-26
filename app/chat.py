"""Chat-Funktion (Phase 4): Claude sieht die aktuellen Daten + den Trainingsplan
und kann Aenderungen vorschlagen. Eine vorgeschlagene Aenderung wird NIE
automatisch uebernommen - erst wenn der Nutzer im Dashboard "Uebernehmen"
klickt, ruft apply_changes() die eigentliche Datenbank-Aenderung auf.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from typing import Any

from app import config

MODEL = "claude-opus-5"

_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

_ALLOWED_WORKOUT_TYPES = {"easy", "tempo", "intervals", "long", "strength", "rest", "race"}
_ALLOWED_ACTIONS = {"verschieben", "loeschen", "aendern"}


class ChatNotConfigured(RuntimeError):
    """ANTHROPIC_API_KEY fehlt in der .env."""


def _build_system_prompt(report: dict[str, Any], workouts: list[dict[str, Any]]) -> str:
    plan_json = json.dumps(
        [
            {
                "workout_id": w["id"],
                "date": w["date"],
                "workout_type": w["workout_type"],
                "title": w["title"],
                "description": w["description"],
                "status": w["status"],
            }
            for w in workouts
        ],
        ensure_ascii=False,
    )
    report_json = json.dumps(
        {
            "datum": report.get("date"),
            "recovery_score": report.get("recovery_score"),
            "recovery_ampel": report.get("recovery_ampel"),
            "strain_heute": report.get("strain_heute"),
            "tsb": report.get("tsb"),
            "acwr": report.get("acwr"),
            "empfehlung_heute": report.get("empfehlung_heute"),
        },
        ensure_ascii=False,
    )

    return f"""Du bist ein Laufcoach-Assistent in einem persoenlichen Trainings-Dashboard.

Aktuelle Werte des Nutzers (heute):
{report_json}

Sein aktiver Trainingsplan (naechste/letzte Eintraege, je mit workout_id):
{plan_json}

Antworte kurz, konkret und auf Deutsch. Du kennst nur die oben gelieferten
Daten - erfinde keine Werte, die dort nicht stehen.

Wenn der Nutzer eine KONKRETE Aenderung am Trainingsplan wuenscht (z.B. eine
Einheit verschieben, streichen, oder Typ/Beschreibung aendern), schlage sie
in Worten vor UND haenge an das Ende deiner Antwort GENAU EINEN JSON-Block
in diesem Format an (nur wenn eine konkrete Aenderung sinnvoll ist, sonst
komplett weglassen):

```json
{{"aenderungen": [{{"workout_id": <id aus dem Plan oben>, "aktion": "verschieben"|"loeschen"|"aendern", "neues_datum": "YYYY-MM-DD" (nur bei verschieben), "neuer_typ": "easy"|"tempo"|"intervals"|"long"|"strength"|"rest" (nur bei aendern, optional), "neue_beschreibung": "..." (nur bei aendern, optional)}}]}}
```

Nutze NUR workout_id-Werte aus dem obigen Plan. Du kannst keine komplett
neuen Trainingstage hinzufuegen, nur bestehende Eintraege verschieben,
streichen oder inhaltlich anpassen - sag das dem Nutzer, falls er etwas
grundsaetzlich Neues moechte. Die Aenderung wird NICHT automatisch
uebernommen, sondern dem Nutzer erst zur Bestaetigung angezeigt."""


def _parse_proposal(text: str, valid_workout_ids: set[int]) -> tuple[str, list[dict[str, Any]] | None]:
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return text.strip(), None

    clean_text = (text[: match.start()] + text[match.end():]).strip()

    try:
        parsed = json.loads(match.group(1))
        changes = parsed.get("aenderungen", [])
    except (json.JSONDecodeError, AttributeError):
        return clean_text, None

    valid_changes = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        if change.get("workout_id") not in valid_workout_ids:
            continue
        if change.get("aktion") not in _ALLOWED_ACTIONS:
            continue
        if change.get("neuer_typ") is not None and change["neuer_typ"] not in _ALLOWED_WORKOUT_TYPES:
            continue
        valid_changes.append(change)

    return clean_text, (valid_changes or None)


def ask_coach(message: str, report: dict[str, Any], workouts: list[dict[str, Any]]) -> dict[str, Any]:
    if not config.ANTHROPIC_API_KEY:
        raise ChatNotConfigured(
            "Kein ANTHROPIC_API_KEY in der .env hinterlegt. Trag deinen Claude-API-Key "
            "ein, um den Chat zu nutzen."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    system_prompt = _build_system_prompt(report, workouts)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )

    text = "".join(block.text for block in response.content if block.type == "text")
    valid_ids = {w["id"] for w in workouts}
    antwort, vorschlag = _parse_proposal(text, valid_ids)

    return {"antwort": antwort, "vorschlag": vorschlag}


def apply_changes(conn: sqlite3.Connection, plan_id: int, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wendet vom Nutzer bestaetigte Aenderungen an - nur auf Workouts des
    angegebenen (aktiven) Plans, nichts ausserhalb."""
    valid_ids = {
        row["id"]
        for row in conn.execute("SELECT id FROM planned_workouts WHERE plan_id = ?", (plan_id,)).fetchall()
    }
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    applied = []

    for change in changes:
        workout_id = change.get("workout_id")
        if workout_id not in valid_ids:
            continue
        action = change.get("aktion")

        if action == "verschieben" and change.get("neues_datum"):
            conn.execute(
                "UPDATE planned_workouts SET date = ? WHERE id = ?",
                (change["neues_datum"], workout_id),
            )
            applied.append({"workout_id": workout_id, "aktion": "verschoben", "neues_datum": change["neues_datum"]})

        elif action == "loeschen":
            conn.execute(
                "UPDATE planned_workouts SET workout_type = 'rest', "
                "description = description || ' (auf Wunsch gestrichen am ' || ? || ')' WHERE id = ?",
                (now_iso[:10], workout_id),
            )
            applied.append({"workout_id": workout_id, "aktion": "gestrichen"})

        elif action == "aendern":
            fields, params = [], []
            if change.get("neuer_typ"):
                fields.append("workout_type = ?")
                params.append(change["neuer_typ"])
            if change.get("neue_beschreibung"):
                fields.append("description = ?")
                params.append(change["neue_beschreibung"])
            if fields:
                params.append(workout_id)
                conn.execute(f"UPDATE planned_workouts SET {', '.join(fields)} WHERE id = ?", params)
                applied.append({"workout_id": workout_id, "aktion": "geaendert"})

    return applied
