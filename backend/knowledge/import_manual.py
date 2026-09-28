from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
from pathlib import Path

try:
    import pymupdf as fitz  # type: ignore
except ImportError:  # pragma: no cover - older environments
    import fitz  # type: ignore


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "runtime" / "knowledge.db"


def normalize(text: str) -> str:
    text = text.replace("\x00", "")
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def infer_heading(text: str) -> str:
    lines = [normalize(x) for x in text.splitlines() if normalize(x)]
    for line in lines[:8]:
        if len(line) <= 80 and (re.match(r"^(第?[一二三四五六七八九十0-9]+[章节、.]?)", line) or line.isupper()):
            return line
    return lines[0][:80] if lines else "未命名章节"


def make_chunks(text: str, page: int, chunk_size: int = 1200, overlap: int = 160):
    clean = normalize(text)
    if not clean:
        return []
    # Keep page boundaries as evidence boundaries. Paragraphs are preferred;
    # long pages are then split with a small overlap.
    paragraphs = [normalize(p) for p in re.split(r"\n{2,}|(?<=[。！？；])\s+", text) if normalize(p)]
    if not paragraphs:
        paragraphs = [clean]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 1 <= chunk_size:
            current = f"{current} {paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            if len(paragraph) > chunk_size:
                start = 0
                while start < len(paragraph):
                    chunks.append(paragraph[start : start + chunk_size])
                    start += chunk_size - overlap
                current = ""
            else:
                current = paragraph
    if current:
        chunks.append(current)
    return [(page, infer_heading(text), chunk) for chunk in chunks]


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            device_model TEXT NOT NULL,
            title TEXT NOT NULL,
            version TEXT,
            source_level TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            page_count INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            device_model TEXT NOT NULL,
            page INTEGER NOT NULL,
            section TEXT,
            content TEXT NOT NULL,
            chunk_type TEXT NOT NULL DEFAULT 'text',
            source_level TEXT NOT NULL,
            chunk_order INTEGER NOT NULL DEFAULT 0,
            section_path TEXT,
            parent_chunk_id INTEGER,
            UNIQUE(document_id, page, content)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
            content, section, device_model, content='knowledge_chunks', content_rowid='id'
        );
        """
    )
    # Keep existing demo databases usable while adding the metadata fields
    # borrowed from RAGFlow's chunk model. SQLite has no IF NOT EXISTS form
    # for ADD COLUMN, so inspect the table before applying each migration.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_chunks)")}
    for name, definition in (
        ("chunk_order", "INTEGER NOT NULL DEFAULT 0"),
        ("section_path", "TEXT"),
        ("parent_chunk_id", "INTEGER"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE knowledge_chunks ADD COLUMN {name} {definition}")


def import_pdf(pdf_path: Path, db_path: Path, device_model: str, source_level: str = "official") -> int:
    pdf_path = pdf_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    doc = fitz.open(pdf_path)
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        old = conn.execute("SELECT id FROM documents WHERE sha256 = ?", (digest,)).fetchone()
        if old:
            conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (old[0],))
            conn.execute("DELETE FROM documents WHERE id = ?", (old[0],))
        cur = conn.execute(
            "INSERT INTO documents(device_model,title,version,source_level,path,sha256,page_count) VALUES(?,?,?,?,?,?,?)",
            (device_model, pdf_path.stem, "unknown", source_level, str(pdf_path), digest, len(doc)),
        )
        document_id = cur.lastrowid
        count = 0
        chunk_order = 0
        for page_no, page in enumerate(doc, start=1):
            page_text = page.get_text("text") or ""
            for _, section, content in make_chunks(page_text, page_no):
                chunk_order += 1
                conn.execute(
                    """INSERT OR IGNORE INTO knowledge_chunks(
                        document_id,device_model,page,section,content,source_level,
                        chunk_order,section_path,parent_chunk_id
                    ) VALUES(?,?,?,?,?,?,?,?,NULL)""",
                    (document_id, device_model, page_no, section, content, source_level,
                     chunk_order, section, ),
                )
                count += 1
        # Rebuild the external-content FTS table so importing a second device
        # never removes the first device's searchable chunks.
        conn.execute("DELETE FROM knowledge_fts")
        conn.execute("INSERT INTO knowledge_fts(rowid,content,section,device_model) SELECT id,content,section,device_model FROM knowledge_chunks")
        conn.commit()
        return count
    finally:
        doc.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import a LabMate device manual into SQLite knowledge base")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--device-model", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--source-level", default="official")
    args = parser.parse_args()
    total = import_pdf(args.pdf, args.db, args.device_model, args.source_level)
    print(f"Imported {total} chunks into {args.db}")
