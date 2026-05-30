import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_history_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _conn(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at      TEXT    NOT NULL,
                folder          TEXT    NOT NULL,
                title           TEXT,
                score           INTEGER,
                job_offer_snippet TEXT,
                valid_bullets   INTEGER,
                valid_skills    INTEGER,
                model           TEXT,
                offer_url       TEXT
            )
        """)
        # Migration : ajoute offer_url si la table existait déjà sans cette colonne
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(generations)")}
        if "offer_url" not in existing:
            conn.execute("ALTER TABLE generations ADD COLUMN offer_url TEXT")
        conn.commit()


def make_history_slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", (title or "").lower())
    slug = re.sub(r"[\s_-]+", "_", slug).strip("_")[:35]
    return slug or "cv"


def make_history_folder(history_dir: Path, title: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = history_dir / f"{ts}_{make_history_slug(title)}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_generation(
    db_path: Path,
    folder: Path,
    title: str,
    score: int,
    job_offer: str,
    valid_bullets: int,
    valid_skills: int,
    model: str,
    offer_url: Optional[str] = None,
) -> int:
    created_at = datetime.now().isoformat(timespec="seconds")
    with _conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO generations
               (created_at, folder, title, score, job_offer_snippet, valid_bullets, valid_skills, model, offer_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (created_at, str(folder), title, score, job_offer[:300], valid_bullets, valid_skills, model, offer_url),
        )
        conn.commit()
        return cur.lastrowid


def list_generations(db_path: Path) -> List[Dict[str, Any]]:
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM generations ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        return [dict(r) for r in rows]


def get_generation(db_path: Path, gen_id: int) -> Optional[Dict[str, Any]]:
    with _conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM generations WHERE id = ?", (gen_id,)
        ).fetchone()
        return dict(row) if row else None


def delete_generation(db_path: Path, gen_id: int) -> Optional[str]:
    entry = get_generation(db_path, gen_id)
    if not entry:
        return None
    folder = Path(entry["folder"])
    if folder.exists():
        shutil.rmtree(folder)
    with _conn(db_path) as conn:
        conn.execute("DELETE FROM generations WHERE id = ?", (gen_id,))
        conn.commit()
    return entry["folder"]


def read_generation_files(folder: Path) -> Dict[str, Any]:
    def read(name: str) -> str:
        p = folder / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def read_json(name: str) -> Any:
        p = folder / name
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    audit    = read_json("audit_report.json")
    matching = read_json("matching_analysis.json")
    generated = read_json("generated_cv.json")
    editable_cv = read_json("editable_cv.json")
    pdf_design = read_json("pdf_design.json")

    pdf_path = folder / "cv_targeted.pdf"
    output_files: Dict[str, str] = {}
    if pdf_path.exists():
        output_files["cv_targeted.pdf"] = str(pdf_path)

    return {
        "final_markdown":  read("cv_recruiter.md"),
        "audit_markdown":  read("audit_report.md"),
        "email_markdown":  read("email.md"),
        "matching":        matching,
        "generated_cv":    generated,
        "audit":           audit,
        "editable_cv":     editable_cv or None,
        "pdf_design":      pdf_design or {"font_size": 9.25, "margin": "normal"},
        "output_files":    output_files,
    }
