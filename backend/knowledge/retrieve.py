from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "runtime" / "knowledge.db"


def _fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", query.lower())
    return " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:24]) or '"设备"'


def search(query: str, device_model: str, db_path: Path = DEFAULT_DB, limit: int = 5) -> str | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT c.page, c.section, c.content, c.source_level, d.title
               FROM knowledge_fts f
               JOIN knowledge_chunks c ON c.id = f.rowid
               JOIN documents d ON d.id = c.document_id
               WHERE knowledge_fts MATCH ? AND c.device_model = ?
               ORDER BY bm25(knowledge_fts) LIMIT ?""",
            (_fts_query(query), device_model, limit),
        ).fetchall()
        if not rows:
            return None
        return "\n\n".join(
            f"[来源：{row['title']} | 设备：{device_model} | 第 {row['page']} 页 | {row['section']} | {row['source_level']}]\n{row['content']}"
            for row in rows
        )
    finally:
        conn.close()
