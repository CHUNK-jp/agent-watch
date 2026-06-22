"""Agent tracker — detect running agent processes."""

import psutil
from typing import Optional


KNOWN_AGENTS = [
    "claude",
    "claude-code",
    "aider",
    "autogpt",
    "langchain",
    "dify",
    "n8n",
    "openai",
    "crewai",
]


class AgentTracker:
    """Detect agent processes running on the local machine."""

    def get_running_agents(self) -> list[dict]:
        found = []
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline", "cpu_percent", "memory_info"]):
                try:
                    name = (proc.info["name"] or "").lower()
                    cmdline = " ".join(proc.info["cmdline"] or []).lower()
                    combined = name + " " + cmdline

                    for agent in KNOWN_AGENTS:
                        if agent in combined:
                            found.append({
                                "pid": proc.info["pid"],
                                "name": proc.info["name"],
                                "agent": agent,
                                "cpu_percent": proc.info["cpu_percent"],
                                "memory_mb": round(
                                    proc.info["memory_info"].rss / 1024 / 1024, 1
                                ) if proc.info.get("memory_info") else 0,
                            })
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return found
