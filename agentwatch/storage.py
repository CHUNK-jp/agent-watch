"""SQLite storage for AgentWatch logs."""

import sqlite3
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DB_PATH = Path.home() / ".agentwatch" / "logs.db"


class Storage:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS actions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT    NOT NULL,
                    agent       TEXT    NOT NULL DEFAULT 'unknown',
                    provider    TEXT,
                    model       TEXT,
                    action      TEXT    NOT NULL,
                    detail      TEXT,
                    input_tokens  INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cost        REAL    DEFAULT 0.0,
                    latency_ms  INTEGER DEFAULT 0,
                    raw         TEXT
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at  TEXT    NOT NULL,
                    ended_at    TEXT,
                    agent       TEXT,
                    total_cost  REAL    DEFAULT 0.0,
                    total_actions INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_actions_ts    ON actions(timestamp);
                CREATE INDEX IF NOT EXISTS idx_actions_agent ON actions(agent);
            """)

    def log_action(
        self,
        *,
        agent: str = "unknown",
        provider: str = "",
        model: str = "",
        action: str,
        detail: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
        latency_ms: int = 0,
        raw: Optional[dict] = None,
    ):
        ts = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO actions
                   (timestamp, agent, provider, model, action, detail,
                    input_tokens, output_tokens, cost, latency_ms, raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ts, agent, provider, model, action, detail,
                    input_tokens, output_tokens, cost, latency_ms,
                    json.dumps(raw) if raw else None,
                ),
            )

    def get_summary(self) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) as total_actions,
                          COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                          COALESCE(SUM(cost), 0) as total_cost,
                          MIN(timestamp) as since
                   FROM actions"""
            ).fetchone()

            agents = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT agent FROM actions ORDER BY agent"
                ).fetchall()
            ]

            recent = [
                dict(r) for r in conn.execute(
                    """SELECT timestamp, agent, action, cost
                       FROM actions ORDER BY id DESC LIMIT 20"""
                ).fetchall()
            ]

        return {
            "total_actions": row["total_actions"],
            "total_tokens": row["total_tokens"],
            "total_cost": row["total_cost"],
            "since": (row["since"] or "")[:19],
            "agents": agents,
            "recent_actions": list(reversed(recent)),
        }

    def get_actions(self, limit: int = 200, agent: Optional[str] = None) -> list:
        with self._conn() as conn:
            if agent:
                rows = conn.execute(
                    "SELECT * FROM actions WHERE agent=? ORDER BY id DESC LIMIT ?",
                    (agent, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM actions ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_cost_by_agent(self) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT agent,
                          COUNT(*) as actions,
                          SUM(input_tokens + output_tokens) as tokens,
                          SUM(cost) as cost
                   FROM actions
                   GROUP BY agent
                   ORDER BY cost DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def clear(self):
        with self._conn() as conn:
            conn.execute("DELETE FROM actions")
            conn.execute("DELETE FROM sessions")

    def export_all(self) -> dict:
        with self._conn() as conn:
            actions = [dict(r) for r in conn.execute("SELECT * FROM actions").fetchall()]
        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total": len(actions),
            "actions": actions,
        }
