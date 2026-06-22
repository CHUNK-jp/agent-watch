"""SQLite storage for AgentWatch logs."""

import sqlite3
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DB_PATH = Path.home() / ".agentwatch" / "logs.db"


class Storage:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    agent TEXT NOT NULL DEFAULT 'unknown',
                    provider TEXT, model TEXT, action TEXT NOT NULL,
                    detail TEXT, input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0, cost REAL DEFAULT 0.0,
                    latency_ms INTEGER DEFAULT 0, raw TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL, ended_at TEXT, agent TEXT,
                    total_cost REAL DEFAULT 0.0, total_actions INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_actions_ts ON actions(timestamp);
                CREATE INDEX IF NOT EXISTS idx_actions_agent ON actions(agent);
            """)

    def log_action(self, *, agent="unknown", provider="", model="", action,
                   detail="", input_tokens=0, output_tokens=0, cost=0.0,
                   latency_ms=0, raw=None):
        ts = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO actions (timestamp,agent,provider,model,action,
                   detail,input_tokens,output_tokens,cost,latency_ms,raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (ts,agent,provider,model,action,detail,
                 input_tokens,output_tokens,cost,latency_ms,
                 json.dumps(raw) if raw else None),
            )

    def get_summary(self):
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) as total_actions,
                   COALESCE(SUM(input_tokens+output_tokens),0) as total_tokens,
                   COALESCE(SUM(cost),0) as total_cost, MIN(timestamp) as since
                   FROM actions""").fetchone()
            agents = [r[0] for r in conn.execute(
                "SELECT DISTINCT agent FROM actions ORDER BY agent").fetchall()]
            recent = [dict(r) for r in conn.execute(
                "SELECT timestamp,agent,action,cost FROM actions ORDER BY id DESC LIMIT 20").fetchall()]
        return {"total_actions":row["total_actions"],"total_tokens":row["total_tokens"],
                "total_cost":row["total_cost"],"since":(row["since"] or "")[:19],
                "agents":agents,"recent_actions":list(reversed(recent))}

    def get_actions(self, limit=200, agent=None):
        with self._conn() as conn:
            if agent:
                rows = conn.execute("SELECT * FROM actions WHERE agent=? ORDER BY id DESC LIMIT ?",
                    (agent, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM actions ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_cost_by_agent(self):
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT agent, COUNT(*) as actions,
                   SUM(input_tokens+output_tokens) as tokens, SUM(cost) as cost
                   FROM actions GROUP BY agent ORDER BY cost DESC""").fetchall()
        return [dict(r) for r in rows]

    def clear(self):
        with self._conn() as conn:
            conn.execute("DELETE FROM actions")
            conn.execute("DELETE FROM sessions")

    def export_all(self):
        with self._conn() as conn:
            actions = [dict(r) for r in conn.execute("SELECT * FROM actions").fetchall()]
        return {"exported_at":datetime.now(timezone.utc).isoformat(),
                "total":len(actions),"actions":actions}
"""
HTTP Proxy that intercepts OpenAI / Anthropic / Ollama API calls
and logs them to Storage.
"""

import time
import json
import threading
import click
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import urlparse, urlencode
from typing import Optional

from agentwatch.storage import Storage
from agentwatch.alerts import AlertManager

# ── Cost tables (USD per 1K tokens) ──────────────────────────────────────────
OPENAI_PRICES = {
    "gpt-4o":              (0.0025, 0.010),
    "gpt-4o-mini":         (0.00015, 0.0006),
    "gpt-4-turbo":         (0.010,  0.030),
    "gpt-4":               (0.030,  0.060),
    "gpt-3.5-turbo":       (0.0005, 0.0015),
    "o1":                  (0.015,  0.060),
    "o1-mini":             (0.003,  0.012),
    "o3-mini":             (0.0011, 0.0044),
}

ANTHROPIC_PRICES = {
    "claude-opus-4":       (0.015, 0.075),
    "claude-sonnet-4":     (0.003, 0.015),
    "claude-haiku-4":      (0.00025, 0.00125),
    "claude-3-5-sonnet":   (0.003, 0.015),
    "claude-3-5-haiku":    (0.00025, 0.00125),
    "claude-3-opus":       (0.015, 0.075),
}


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    tables = [OPENAI_PRICES, ANTHROPIC_PRICES]
    for table in tables:
        for key, (inp_price, out_price) in table.items():
            if key in model.lower():
                return (input_tokens / 1000 * inp_price) + (output_tokens / 1000 * out_price)
    return 0.0


def _detect_provider(path: str) -> str:
    if "/openai" in path:
        return "openai"
    if "/anthropic" in path:
        return "anthropic"
    if "/ollama" in path:
        return "ollama"
    return "unknown"


def _upstream_url(path: str) -> str:
    if "/openai" in path:
        base = "https://api.openai.com"
        tail = path.split("/openai", 1)[1]
        return base + (tail or "/v1/chat/completions")
    if "/anthropic" in path:
        base = "https://api.anthropic.com"
        tail = path.split("/anthropic", 1)[1]
        return base + (tail or "/v1/messages")
    if "/ollama" in path:
        base = "http://localhost:11434"
        tail = path.split("/ollama", 1)[1]
        return base + (tail or "/api/chat")
    return ""


class _ProxyHandler(BaseHTTPRequestHandler):
    storage: Storage
    alerts: AlertManager

    def log_message(self, format, *args):
        pass  # suppress default HTTP logs

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        provider = _detect_provider(self.path)
        upstream = _upstream_url(self.path)

        if not upstream:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"unknown provider path"}')
            return

        # Forward headers (strip hop-by-hop)
        fwd_headers = {}
        for k, v in self.headers.items():
            if k.lower() not in {"host", "content-length", "transfer-encoding", "connection"}:
                fwd_headers[k] = v
        fwd_headers["Host"] = urlparse(upstream).netloc

        t0 = time.monotonic()
        try:
            req = Request(upstream, data=body, headers=fwd_headers, method="POST")
            with urlopen(req, timeout=120) as resp:
                resp_body = resp.read()
                status = resp.status
        except URLError as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Parse response for token counts
        model = ""
        action = "api_call"
        input_tokens = 0
        output_tokens = 0
        raw_resp = None

        try:
            raw_resp = json.loads(resp_body)
            model = raw_resp.get("model", "")

            # OpenAI format
            if "usage" in raw_resp:
                usage = raw_resp["usage"]
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                if "choices" in raw_resp:
                    action = "chat_completion"

            # Anthropic format
            elif "input_tokens" in raw_resp or "usage" in raw_resp:
                usage = raw_resp.get("usage", raw_resp)
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                action = "message"

            # Ollama format
            elif "prompt_eval_count" in raw_resp:
                input_tokens = raw_resp.get("prompt_eval_count", 0)
                output_tokens = raw_resp.get("eval_count", 0)
                model = raw_resp.get("model", "ollama")
                action = "generate"

        except Exception:
            pass

        cost = _calc_cost(model, input_tokens, output_tokens)

        self.storage.log_action(
            agent=fwd_headers.get("X-Agent-Name", "unknown"),
            provider=provider,
            model=model,
            action=action,
            detail=f"{input_tokens}in/{output_tokens}out tokens",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_ms=latency_ms,
        )

        self.alerts.check(cost=cost, action_count=1, storage=self.storage)

        # Send response back to client
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"AgentWatch proxy running"}')


class ProxyServer:
    def __init__(self, port: int, storage: Storage, alerts: AlertManager):
        self.port = port
        self.storage = storage
        self.alerts = alerts
        self._server: Optional[HTTPServer] = None

    def start(self):
        storage = self.storage
        alerts = self.alerts

        class Handler(_ProxyHandler):
            pass

        Handler.storage = storage
        Handler.alerts = alerts

        self._server = HTTPServer(("localhost", self.port), Handler)
        self._server.serve_forever()

    def stop(self):
        if self._server:
            self._server.shutdown()

    def print_live(self, storage: Storage, alerts: AlertManager):
        """Print a live tail of actions to the terminal."""
        import time
        last_id = 0

        while True:
            actions = storage.get_actions(limit=100)
            new_actions = [a for a in actions if a["id"] > last_id]
            for action in new_actions:
                last_id = action["id"]
                ts = action["timestamp"][11:19]
                agent = click.style(action["agent"], fg="cyan")
                act = click.style(action["action"], fg="white")
                cost_str = (
                    click.style(f"  ${action['cost']:.4f}", fg="yellow")
                    if action["cost"] else ""
                )
                model_str = f"  [{action['model']}]" if action["model"] else ""
                lat = f"  {action['latency_ms']}ms" if action["latency_ms"] else ""
                click.echo(f"[{ts}] {agent} → {act}{model_str}{cost_str}{lat}")
            time.sleep(0.5)
