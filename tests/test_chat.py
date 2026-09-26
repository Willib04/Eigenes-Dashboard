import datetime as dt
from pathlib import Path

import pytest

from app import chat, db, plan


def test_parse_proposal_without_json_block_returns_none() -> None:
    text, proposal = chat._parse_proposal("Klingt gut, hier ist mein Rat.", {1, 2})
    assert text == "Klingt gut, hier ist mein Rat."
    assert proposal is None


def test_parse_proposal_extracts_valid_change() -> None:
    text = (
        "Klar, ich verschiebe die Einheit.\n\n"
        '```json\n{"aenderungen": [{"workout_id": 1, "aktion": "verschieben", '
        '"neues_datum": "2024-03-20"}]}\n```'
    )
    clean, proposal = chat._parse_proposal(text, {1, 2})
    assert "json" not in clean
    assert "verschiebe" in clean
    assert proposal == [{"workout_id": 1, "aktion": "verschieben", "neues_datum": "2024-03-20"}]


def test_parse_proposal_filters_unknown_workout_id() -> None:
    text = '```json\n{"aenderungen": [{"workout_id": 999, "aktion": "loeschen"}]}\n```'
    _, proposal = chat._parse_proposal(text, {1, 2})
    assert proposal is None


def test_parse_proposal_filters_invalid_action() -> None:
    text = '```json\n{"aenderungen": [{"workout_id": 1, "aktion": "explodieren"}]}\n```'
    _, proposal = chat._parse_proposal(text, {1})
    assert proposal is None


def test_parse_proposal_handles_malformed_json_gracefully() -> None:
    text = "Vorschlag:\n```json\n{not valid json\n```"
    clean, proposal = chat._parse_proposal(text, {1})
    assert proposal is None
    assert clean  # Text bleibt trotzdem erhalten


def test_apply_changes_verschieben(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    start = dt.date(2024, 3, 12)

    with db.connect(db_path) as conn:
        plan_id = plan.generate_plan(conn, start_date=start, goal_weeks=3)
        workout = conn.execute(
            "SELECT id FROM planned_workouts WHERE plan_id = ? ORDER BY date LIMIT 1", (plan_id,)
        ).fetchone()
        applied = chat.apply_changes(
            conn, plan_id, [{"workout_id": workout["id"], "aktion": "verschieben", "neues_datum": "2024-03-21"}]
        )
        new_date = conn.execute(
            "SELECT date FROM planned_workouts WHERE id = ?", (workout["id"],)
        ).fetchone()["date"]

    assert applied == [{"workout_id": workout["id"], "aktion": "verschoben", "neues_datum": "2024-03-21"}]
    assert new_date == "2024-03-21"


def test_apply_changes_loeschen_keeps_row_as_rest(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)
    start = dt.date(2024, 3, 12)

    with db.connect(db_path) as conn:
        plan_id = plan.generate_plan(conn, start_date=start, goal_weeks=3)
        workout = conn.execute(
            "SELECT id FROM planned_workouts WHERE plan_id = ? ORDER BY date LIMIT 1", (plan_id,)
        ).fetchone()
        chat.apply_changes(conn, plan_id, [{"workout_id": workout["id"], "aktion": "loeschen"}])
        row = conn.execute("SELECT workout_type, description FROM planned_workouts WHERE id = ?", (workout["id"],)).fetchone()

    assert row["workout_type"] == "rest"
    assert "gestrichen" in row["description"]


def test_apply_changes_ignores_workout_outside_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db.init_db(db_path)

    with db.connect(db_path) as conn:
        plan_id_1 = plan.generate_plan(conn, start_date=dt.date(2024, 3, 12), goal_weeks=3)
        plan_id_2 = plan.generate_plan(conn, start_date=dt.date(2024, 3, 12), goal_weeks=3)
        other_plan_workout = conn.execute(
            "SELECT id FROM planned_workouts WHERE plan_id = ? LIMIT 1", (plan_id_1,)
        ).fetchone()
        applied = chat.apply_changes(
            conn, plan_id_2, [{"workout_id": other_plan_workout["id"], "aktion": "loeschen"}]
        )

    assert applied == []


def test_ask_coach_raises_when_not_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(chat.config, "ANTHROPIC_API_KEY", "")
    with pytest.raises(chat.ChatNotConfigured):
        chat.ask_coach("Hallo", {"date": "2024-03-12"}, [])


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResponse(self.reply_text)


class _FakeAnthropicClient:
    def __init__(self, reply_text: str) -> None:
        self.messages = _FakeMessages(reply_text)


def test_ask_coach_returns_answer_and_proposal(monkeypatch) -> None:
    monkeypatch.setattr(chat.config, "ANTHROPIC_API_KEY", "test-key")

    reply = (
        "Klar, ich verschiebe deine Einheit auf Mittwoch.\n\n"
        '```json\n{"aenderungen": [{"workout_id": 1, "aktion": "verschieben", '
        '"neues_datum": "2024-03-13"}]}\n```'
    )
    fake_client = _FakeAnthropicClient(reply)

    import anthropic as anthropic_module
    monkeypatch.setattr(anthropic_module, "Anthropic", lambda api_key: fake_client)

    result = chat.ask_coach(
        "Ich bin Dienstag krank, verschieb die Einheit",
        {"date": "2024-03-12", "recovery_score": 70},
        [{"id": 1, "date": "2024-03-12", "workout_type": "intervals", "title": "Intervalle",
          "description": "...", "status": "heute"}],
    )

    assert "verschiebe" in result["antwort"]
    assert result["vorschlag"] == [{"workout_id": 1, "aktion": "verschieben", "neues_datum": "2024-03-13"}]
    assert fake_client.messages.last_kwargs["model"] == chat.MODEL
