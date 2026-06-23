#!/usr/bin/env bash
# Demo script for AgentWatch — recorded by asciinema

BOLD='\033[1m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
DIM='\033[2m'
RESET='\033[0m'

type_cmd() {
    echo -en "${BOLD}\$ ${RESET}"
    local cmd="$1"
    for (( i=0; i<${#cmd}; i++ )); do
        echo -n "${cmd:$i:1}"
        sleep 0.045
    done
    echo
    sleep 0.3
    eval "$cmd"
}

type_line() {
    echo -en "${BOLD}\$ ${RESET}"
    local cmd="$1"
    for (( i=0; i<${#cmd}; i++ )); do
        echo -n "${cmd:$i:1}"
        sleep 0.045
    done
    echo
    sleep 0.3
}

cd ~/agent-watch

# Reset DB so demo starts clean
python3 -c "
import sys; sys.path.insert(0, '.')
from agentwatch.storage import Storage
Storage().clear()
"

sleep 0.8

# ── Step 1: config ────────────────────────────────────────────────────────────
type_cmd "python3 agentwatch.py config"

sleep 1.8

# ── Step 2: watch --no-dashboard (simulated) ──────────────────────────────────
type_line "python3 agentwatch.py watch --no-dashboard &"

echo -e "${CYAN}${BOLD}👁  AgentWatch${RESET} — starting up"
echo "   Proxy  → http://localhost:8080"
echo ""
echo -e "${GREEN}✓ Monitoring active${RESET}  (Ctrl+C to stop)"
echo ""

sleep 2

# Inject mock log entries and print simulated live output
python3 << 'PYEOF'
import time, sys
sys.path.insert(0, '.')
from agentwatch.storage import Storage

s = Storage()

entries = [
    ("claude-code", "anthropic", "claude-sonnet-4", "chat_completion",  892,  341, 0.0031, 142),
    ("my-agent",    "openai",    "gpt-4o-mini",      "chat_completion",  523,  187, 0.0008,  89),
    ("claude-code", "anthropic", "claude-sonnet-4",  "chat_completion", 1204,  489, 0.0044, 198),
    ("my-agent",    "openai",    "gpt-4o-mini",       "chat_completion",  678,  223, 0.0012, 103),
    ("claude-code", "anthropic", "claude-sonnet-4",  "chat_completion", 2801,  912, 0.0105, 287),
]

CYAN  = "\033[36m"
WHITE = "\033[37m"
YLW   = "\033[33m"
DIM   = "\033[90m"
RED   = "\033[31m"
RST   = "\033[0m"

running_cost = 0.0
for agent, provider, model, action, inp, out, cost, lat in entries:
    s.log_action(
        agent=agent, provider=provider, model=model,
        action=action, detail=f"{inp}in/{out}out tokens",
        input_tokens=inp, output_tokens=out, cost=cost, latency_ms=lat,
    )
    running_cost += cost
    agent_col  = f"{CYAN}{agent:<12}{RST}"
    cost_col   = f"{YLW}${cost:.4f}{RST}"
    model_col  = f"{DIM}[{model}]{RST}"
    print(f"  {agent_col} → {action}  {model_col}  {cost_col}  {lat}ms")
    sys.stdout.flush()
    time.sleep(0.7)

print()
print(f"  {RED}⚠️  Cost alert: ${running_cost:.4f} exceeded $0.10 threshold{RST}")
sys.stdout.flush()
PYEOF

sleep 1.0

# ── Step 3: status ────────────────────────────────────────────────────────────
echo ""
type_cmd "python3 agentwatch.py status"

sleep 1.5
