# 👁 AgentWatch

**Real-time AI Agent Monitor — Know what your agents are doing.**

A local-first CLI dashboard that intercepts OpenAI / Anthropic / Ollama API calls,
logs every action, tracks costs, and alerts you when thresholds are exceeded.
No cloud. No account. Just your agents, visible.

```
[12:34:01] claude-code → chat_completion [claude-sonnet-4]  $0.0031  142ms
[12:34:03] my-agent   → chat_completion [gpt-4o-mini]       $0.0008   89ms
⚠️  Cost alert: $0.1012 exceeded $0.10 threshold
```

## Quick Start

```bash
pip install -r requirements.txt

# Configure your AI tool to use the AgentWatch proxy
python3 agentwatch.py config

# Start monitoring
python3 agentwatch.py watch
```

Dashboard auto-opens at **http://localhost:7070**

## Commands

| Command | Description |
|---|---|
| `watch` | Start proxy + live log + dashboard |
| `status` | Show current session summary |
| `clear` | Delete all stored logs |
| `export` | Export logs to JSON |
| `config` | Show proxy env variables |

## How It Works

```
Your Agent
    ↓
OPENAI_BASE_URL=http://localhost:8080/openai
    ↓
AgentWatch Proxy (port 8080)
    ↓ intercepts + logs + calculates cost
Upstream API (OpenAI / Anthropic / Ollama)
    ↓ response forwarded back
Your Agent (unchanged behavior)
```

AgentWatch acts as a transparent HTTP proxy. Your agent runs normally —
it just routes through `localhost:8080` first.

## Supported Providers

| Provider | Env Variable |
|---|---|
| OpenAI | `OPENAI_BASE_URL=http://localhost:8080/openai` |
| Anthropic | `ANTHROPIC_BASE_URL=http://localhost:8080/anthropic` |
| Ollama | `OLLAMA_HOST=http://localhost:8080/ollama` |

## Options

```
python3 agentwatch.py watch \\
  --port 8080 \\
  --dashboard-port 7070 \\
  --alert-cost 0.05 \\
  --alert-actions 100 \\
  --no-dashboard
```

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

## License

MIT — free to use, modify, and distribute.

Built by [CHUNK-jp](https://github.com/CHUNK-jp) · No cloud. No subscription. Just your agents.
