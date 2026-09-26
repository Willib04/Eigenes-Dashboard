"""Duenne Helferschicht um die lokale SQLite-Datenbank.

Es wird bewusst kein ORM verwendet: die Tabellen sind einfach genug,
und Rohabfragen sind fuer Einsteiger leichter nachzuvollziehen.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app import config

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: Path | None = None) -> None:
    """Legt die Datenbankdatei und alle Tabellen an, falls sie nicht existieren."""
    db_path = db_path or config.DASHBOARD_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(db_path) as conn:
        conn.executescript(schema)


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    db_path = db_path or config.DASHBOARD_DB_PATH
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert(conn: sqlite3.Connection, table: str, row: dict[str, Any], key_column: str) -> None:
    """Fuegt eine Zeile ein oder ersetzt sie, falls der Schluessel schon existiert.

    None-Werte werden mitgeschrieben (das ist explizit "keine Daten"), es wird
    nichts weggelassen oder durch einen Schaetzwert ersetzt.
    """
    if key_column not in row:
        raise ValueError(f"row muss den Schluessel '{key_column}' enthalten")

    columns = list(row.keys())
    placeholders = ", ".join(f":{c}" for c in columns)
    column_list = ", ".join(columns)
    sql = f"INSERT OR REPLACE INTO {table} ({column_list}) VALUES ({placeholders})"
    conn.execute(sql, row)


def fetch_one(conn: sqlite3.Connection, table: str, key_column: str, key_value: Any) -> dict[str, Any] | None:
    cur = conn.execute(f"SELECT * FROM {table} WHERE {key_column} = ?", (key_value,))
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_range(
    conn: sqlite3.Connection,
    table: str,
    date_column: str,
    date_from: str,
    date_to: str,
    order_by: str | None = None,
) -> list[dict[str, Any]]:
    order_clause = f" ORDER BY {order_by}" if order_by else f" ORDER BY {date_column}"
    cur = conn.execute(
        f"SELECT * FROM {table} WHERE {date_column} BETWEEN ? AND ?{order_clause}",
        (date_from, date_to),
    )
    return [dict(r) for r in cur.fetchall()]
