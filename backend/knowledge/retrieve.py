from __future__ import annotations

import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "runtime" / "knowledge.db"


def _fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", query.lower())
    return " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:24]) or '"设备"'


@lru_cache(maxsize=256)
def search_hits(query: str, device_model: str, db_path_str: str = str(DEFAULT_DB), limit: int = 5) -> tuple[dict[str, Any], ...]:
    """Return evidence records instead of an already-flattened prompt.

    The shape follows the useful part of RAGFlow's retrieval contract:
    source identity, chunk order, section, page and a stable rank are kept
    until the prompt is assembled. Caching avoids reopening SQLite for repeated
    questions during an interactive session.
    """
    db_path = Path(db_path_str)
    if not db_path.exists():
        return ()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Migrate databases created by the first MVP in-place. Retrieval must
        # remain usable before the manual is re-imported.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_chunks)")}
        for name, definition in (
            ("chunk_order", "INTEGER NOT NULL DEFAULT 0"),
            ("section_path", "TEXT"),
            ("parent_chunk_id", "INTEGER"),
        ):
            if name not in columns:
                conn.execute(f"ALTER TABLE knowledge_chunks ADD COLUMN {name} {definition}")
        conn.commit()
        rows = conn.execute(
            """SELECT c.id, c.page, c.section, c.section_path, c.chunk_order,
                      c.content, c.source_level, d.title, d.path
               FROM knowledge_fts f
               JOIN knowledge_chunks c ON c.id = f.rowid
               JOIN documents d ON d.id = c.document_id
               WHERE knowledge_fts MATCH ? AND c.device_model = ?
               ORDER BY bm25(knowledge_fts) LIMIT ?""",
            (_fts_query(query), device_model, limit),
        ).fetchall()
        return tuple({
            "id": int(row["id"]),
            "title": row["title"],
            "device_model": device_model,
            "page": int(row["page"]),
            "section": row["section"] or "未命名章节",
            "section_path": row["section_path"] or row["section"] or "",
            "chunk_order": int(row["chunk_order"] or 0),
            "content": row["content"],
            "source_level": row["source_level"],
            "source_path": row["path"],
            "rank": index + 1,
            "score": round(1 / (60 + index + 1), 6),
        } for index, row in enumerate(rows))
    finally:
        conn.close()


def search(query: str, device_model: str, db_path: Path = DEFAULT_DB, limit: int = 5) -> str | None:
    """Backward-compatible prompt text wrapper."""
    hits = search_hits(query, device_model, str(db_path), limit)
    if not hits:
        return None
    return format_hits(hits)


def format_hits(hits: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"[证据{hit['rank']}｜来源：{hit['title']}｜设备：{hit['device_model']}｜"
        f"第 {hit['page']} 页｜{hit['section']}｜{hit['source_level']}]\n{hit['content']}"
        for hit in hits
    )
