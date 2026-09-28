from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_DB = ROOT / "runtime" / "sessions.db"


def classify_question(question: str) -> str:
    """Route an open question to a broad skill, never to a fixed task graph."""
    q = question.lower()
    if any(word in q for word in ("危险", "安全", "触电", "冒烟", "烧焦", "短路")):
        return "safety"
    if any(word in q for word in ("红灯", "报警", "故障", "异常", "不工作", "漂移", "噪声")):
        return "troubleshooting"
    if any(word in q for word in ("测量", "频率", "峰峰值", "电压", "电流", "读数", "波形")):
        return "measurement"
    if any(word in q for word in ("怎么按", "如何", "设置", "打开", "保存", "导出", "连接")):
        return "operation"
    return "general"


def save_checkpoint(session_id: str, state: dict[str, Any], decision: dict[str, Any], route: str) -> None:
    """Persist the latest turn so a later upload can resume the conversation."""
    if not session_id:
        return
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(CHECKPOINT_DB) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS checkpoints (
                session_id TEXT PRIMARY KEY,
                route TEXT NOT NULL,
                state_json TEXT NOT NULL,
                decision_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """INSERT INTO checkpoints(session_id, route, state_json, decision_json, updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
                 route=excluded.route, state_json=excluded.state_json,
                 decision_json=excluded.decision_json, updated_at=excluded.updated_at""",
            (session_id, route, json.dumps(state, ensure_ascii=False),
             json.dumps(decision, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
