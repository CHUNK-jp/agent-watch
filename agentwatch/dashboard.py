"""
AgentWatch Web Dashboard
A minimal FastAPI + WebSocket dashboard served on localhost.
"""

import json
import threading
import time
from typing import Optional

from agentwatch.storage import Storage
from agentwatch.tracker import AgentTracker

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>AgentWatch Dashboard</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0d0d0d; --bg2: #141414; --bg3: #1a1a1a;
  --border: #2a2a2a; --text: #e8e8e8; --muted: #666;
  --accent: #3b82f6; --green: #4ade80; --yellow: #facc15; --red: #f87171;
}
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }
header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 1.5rem; height: 52px;
  background: rgba(13,13,13,0.9); backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 10;
}
.logo { font-weight: 700; font-size: 1rem; color: var(--accent); display: flex; align-items: center; gap: 0.5rem; }
.badge { font-size: 0.7rem; background: rgba(59,130,246,0.15); border: 1px solid rgba(59,130,246,0.3); color: var(--accent); padding: 2px 8px; border-radius: 999px; }
#status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); display: inline-block; transition: background 0.3s; }
#status-dot.live { background: var(--green); box-shadow: 0 0 6px var(--green); }
.main { max-width: 1200px; margin: 0 auto; padding: 1.5rem; }
.metrics-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.5rem; }
.metric-card { background: var(--bg2); border: 1px solid var(--border); border-radius: 10px; padding: 1.2rem 1.5rem; }
.metric-label { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.4rem; }
.metric-value { font-size: 1.8rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.metric-value.blue { color: var(--accent); }
.metric-value.green { color: var(--green); }
.metric-value.yellow { color: var(--yellow); }
.metric-value.red { color: var(--red); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
.panel { background: var(--bg2); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.panel-header { padding: 0.8rem 1.2rem; border-bottom: 1px solid var(--border); font-size: 0.8rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; display: flex; align-items: center; justify-content: space-between; }
.panel-body { padding: 0; max-height: 360px; overflow-y: auto; }
.log-line { display: flex; gap: 1rem; align-items: baseline; padding: 0.45rem 1.2rem; border-bottom: 1px solid rgba(255,255,255,0.03); font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.78rem; transition: background 0.1s; }
.log-line:hover { background: var(--bg3); }
.log-ts { color: var(--muted); flex-shrink: 0; width: 80px; }
.log-agent { color: var(--accent); flex-shrink: 0; width: 110px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.log-action { color: var(--text); flex: 1; }
.log-cost { color: var(--yellow); flex-shrink: 0; width: 72px; text-align: right; }
.agent-row { display: flex; align-items: center; justify-content: space-between; padding: 0.7rem 1.2rem; border-bottom: 1px solid rgba(255,255,255,0.03); }
.agent-name { font-weight: 600; color: var(--text); }
.agent-cost { color: var(--yellow); font-family: monospace; }
.agent-actions { color: var(--muted); font-size: 0.8rem; }
.empty { color: var(--muted); padding: 2rem; text-align: center; font-size: 0.85rem; }
@media (max-width: 700px) { .metrics-row { grid-template-columns: repeat(2, 1fr); } .grid-2 { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <div class="logo">👁 AgentWatch <span class="badge">LOCAL</span></div>
  <div style="display:flex;align-items:center;gap:0.6rem;font-size:0.8rem;color:var(--muted)">
    <span id="status-dot"></span>
    <span id="status-text">connecting…</span>
  </div>
</header>
<div class="main">
  <div class="metrics-row">
    <div class="metric-card">
      <div class="metric-label">Total Actions</div>
      <div class="metric-value blue" id="m-actions">—</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Total Tokens</div>
      <div class="metric-value green" id="m-tokens">—</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Total Cost</div>
      <div class="metric-value yellow" id="m-cost">—</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Agents Seen</div>
      <div class="metric-value blue" id="m-agents">—</div>
    </div>
  </div>

  <div class="grid-2">
    <div class="panel">
      <div class="panel-header">Action Log <span id="log-count" style="color:var(--muted);font-weight:400">0</span></div>
      <div class="panel-body" id="log-panel">
        <div class="empty">Waiting for agent activity…</div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header">Cost by Agent</div>
      <div class="panel-body" id="agents-panel">
        <div class="empty">No agents yet.</div>
      </div>
    </div>
  </div>
</div>

<script>
const ws = new WebSocket(`ws://${location.host}/ws`);
const dot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');

ws.onopen = () => {
  dot.classList.add('live');
  statusText.textContent = 'live';
};
ws.onclose = () => {
  dot.classList.remove('live');
  statusText.textContent = 'disconnected';
};

ws.onmessage = (e) => {
  const data = JSON.parse(e.data);

  // Metrics
  document.getElementById('m-actions').textContent = data.summary.total_actions.toLocaleString();
  document.getElementById('m-tokens').textContent = data.summary.total_tokens.toLocaleString();
  document.getElementById('m-cost').textContent = `$${data.summary.total_cost.toFixed(4)}`;
  document.getElementById('m-agents').textContent = data.summary.agents.length;

  // Log
  const logPanel = document.getElementById('log-panel');
  if (data.actions.length === 0) {
    logPanel.innerHTML = '<div class="empty">Waiting for agent activity…</div>';
  } else {
    document.getElementById('log-count').textContent = data.actions.length;
    logPanel.innerHTML = data.actions.slice(-100).reverse().map(a => {
      const ts = a.timestamp.substring(11, 19);
      const cost = a.cost > 0 ? `$${a.cost.toFixed(4)}` : '';
      return `<div class="log-line">
        <span class="log-ts">${ts}</span>
        <span class="log-agent">${a.agent}</span>
        <span class="log-action">${a.action}${a.model ? ` [${a.model}]` : ''}</span>
        <span class="log-cost">${cost}</span>
      </div>`;
    }).join('');
  }

  // Cost by agent
  const agentsPanel = document.getElementById('agents-panel');
  if (data.cost_by_agent.length === 0) {
    agentsPanel.innerHTML = '<div class="empty">No agents yet.</div>';
  } else {
    agentsPanel.innerHTML = data.cost_by_agent.map(a => `
      <div class="agent-row">
        <div>
          <div class="agent-name">${a.agent}</div>
          <div class="agent-actions">${a.actions} actions · ${(a.tokens||0).toLocaleString()} tokens</div>
        </div>
        <div class="agent-cost">$${(a.cost||0).toFixed(4)}</div>
      </div>
    `).join('');
  }
};
</script>
</body>
</html>
"""


class Dashboard:
    def __init__(self, port: int, storage: Storage):
        self.port = port
        self.storage = storage
        self._tracker = AgentTracker()

    def start(self):
        if not HAS_FASTAPI:
            print("[AgentWatch] FastAPI not installed — dashboard disabled. pip install fastapi uvicorn")
            return

        app = FastAPI(title="AgentWatch Dashboard", docs_url=None, redoc_url=None)
        storage = self.storage
        tracker = self._tracker

        @app.get("/", response_class=HTMLResponse)
        async def root():
            return DASHBOARD_HTML

        @app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    summary = storage.get_summary()
                    actions = storage.get_actions(limit=200)
                    cost_by_agent = storage.get_cost_by_agent()
                    await websocket.send_json({
                        "summary": summary,
                        "actions": actions,
                        "cost_by_agent": cost_by_agent,
                    })
                    await asyncio.sleep(1.0)
            except WebSocketDisconnect:
                pass

        import asyncio
        uvicorn.run(app, host="localhost", port=self.port, log_level="error")
