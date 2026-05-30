import sqlite3
from pathlib import Path
from typing import Any, Dict, List
from .text_utils import normalize_text


def get_connection(sqlite_path: Path) -> sqlite3.Connection:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(sqlite_path: Path) -> None:
    with get_connection(sqlite_path) as conn:
        conn.execute("DROP TABLE IF EXISTS evidence")
        conn.execute("DROP TABLE IF EXISTS evidence_fts")
        conn.execute(
            """
            CREATE TABLE evidence (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                source TEXT NOT NULL,
                field TEXT NOT NULL,
                text TEXT NOT NULL,
                normalized_text TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE evidence_fts USING fts5(
                id UNINDEXED,
                category,
                source,
                field,
                text,
                content=''
            )
            """
        )
        conn.commit()


def index_evidence(sqlite_path: Path, evidence_bank: List[Dict[str, Any]]) -> None:
    init_db(sqlite_path)
    with get_connection(sqlite_path) as conn:
        for ev in evidence_bank:
            conn.execute(
                """
                INSERT INTO evidence (id, category, source, field, text, normalized_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ev["id"],
                    ev["category"],
                    ev["source"],
                    ev["field"],
                    ev["text"],
                    normalize_text(ev["text"]),
                ),
            )
            conn.execute(
                """
                INSERT INTO evidence_fts (id, category, source, field, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ev["id"], ev["category"], ev["source"], ev["field"], ev["text"]),
            )
        conn.commit()


def load_all_evidence(sqlite_path: Path) -> List[Dict[str, Any]]:
    with get_connection(sqlite_path) as conn:
        rows = conn.execute("SELECT id, category, source, field, text FROM evidence ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def has_index(sqlite_path: Path) -> bool:
    if not sqlite_path.exists():
        return False
    try:
        with get_connection(sqlite_path) as conn:
            row = conn.execute("SELECT COUNT(*) as n FROM evidence").fetchone()
            return bool(row and row["n"] > 0)
    except sqlite3.Error:
        return False
