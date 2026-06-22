"""Alert system for AgentWatch."""

import click
from typing import Optional


class AlertManager:
    def __init__(self, cost_threshold: float = 0.10, action_threshold: int = 50):
        self.cost_threshold = cost_threshold
        self.action_threshold = action_threshold
        self._cost_alerted = False
        self._action_alerted = False
        self._webhooks: list[str] = []

    def add_webhook(self, url: str):
        self._webhooks.append(url)

    def check(self, *, cost: float, action_count: int, storage):
        summary = storage.get_summary()
        total_cost = summary["total_cost"]
        total_actions = summary["total_actions"]

        if total_cost >= self.cost_threshold and not self._cost_alerted:
            self._cost_alerted = True
            msg = (
                f"\n⚠️  " +
                click.style(f"Cost alert: ${total_cost:.4f} exceeded ${self.cost_threshold:.2f} threshold", fg="red", bold=True)
            )
            click.echo(msg)
            self._send_webhooks(f"AgentWatch cost alert: ${total_cost:.4f} (threshold: ${self.cost_threshold:.2f})")

        if total_actions >= self.action_threshold and not self._action_alerted:
            self._action_alerted = True
            msg = (
                f"\n⚠️  " +
                click.style(f"Action alert: {total_actions} actions exceeded {self.action_threshold} threshold", fg="yellow", bold=True)
            )
            click.echo(msg)
            self._send_webhooks(f"AgentWatch action alert: {total_actions} actions (threshold: {self.action_threshold})")

    def _send_webhooks(self, message: str):
        if not self._webhooks:
            return
        import json
        from urllib.request import urlopen, Request
        payload = json.dumps({"text": message}).encode()
        for url in self._webhooks:
            try:
                req = Request(url, data=payload, headers={"Content-Type": "application/json"})
                urlopen(req, timeout=5)
            except Exception:
                pass

    def reset(self):
        self._cost_alerted = False
        self._action_alerted = False
