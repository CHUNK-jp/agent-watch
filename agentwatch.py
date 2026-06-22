#!/usr/bin/env python3
"""
AgentWatch — Real-time AI Agent Monitor
Monitor your AI agents' actions, costs, and behavior in one place.
"""

import click
import sys
import os

from agentwatch.proxy import ProxyServer
from agentwatch.dashboard import Dashboard
from agentwatch.storage import Storage
from agentwatch.tracker import AgentTracker
from agentwatch.alerts import AlertManager


@click.group()
def cli():
    """👁 AgentWatch — Monitor your AI agents in real time."""
    pass


@cli.command()
@click.option("--port", default=8080, help="Proxy port (default: 8080)")
@click.option("--dashboard-port", default=7070, help="Dashboard port (default: 7070)")
@click.option("--alert-cost", default=0.10, type=float, help="Alert when cost exceeds $X (default: 0.10)")
@click.option("--alert-actions", default=50, type=int, help="Alert when actions exceed N (default: 50)")
@click.option("--no-dashboard", is_flag=True, help="Disable web dashboard")
def watch(port, dashboard_port, alert_cost, alert_actions, no_dashboard):
    """Start monitoring — launch proxy + dashboard."""
    import threading
    import webbrowser
    import time

    storage = Storage()
    alerts = AlertManager(cost_threshold=alert_cost, action_threshold=alert_actions)

    click.echo(click.style("👁  AgentWatch", fg="cyan", bold=True) + " — starting up")
    click.echo(f"   Proxy  → http://localhost:{port}")
    if not no_dashboard:
        click.echo(f"   Dashboard → http://localhost:{dashboard_port}")
    click.echo()

    proxy = ProxyServer(port=port, storage=storage, alerts=alerts)
    proxy_thread = threading.Thread(target=proxy.start, daemon=True)
    proxy_thread.start()

    if not no_dashboard:
        dashboard = Dashboard(port=dashboard_port, storage=storage)
        dash_thread = threading.Thread(target=dashboard.start, daemon=True)
        dash_thread.start()
        time.sleep(1.0)
        webbrowser.open(f"http://localhost:{dashboard_port}")

    click.echo(click.style("✓ Monitoring active", fg="green") + "  (Ctrl+C to stop)\n")

    try:
        proxy.print_live(storage, alerts)
    except KeyboardInterrupt:
        click.echo("\n" + click.style("⏹  AgentWatch stopped.", fg="yellow"))
        summary = storage.get_summary()
        click.echo(f"\n📊 Session summary:")
        click.echo(f"   Total actions : {summary['total_actions']}")
        click.echo(f"   Total tokens  : {summary['total_tokens']:,}")
        click.echo(f"   Total cost    : ${summary['total_cost']:.4f}")
        click.echo(f"   Agents seen   : {', '.join(summary['agents']) or 'none'}")


@cli.command()
def status():
    """Show current agent activity and cost summary."""
    storage = Storage()
    summary = storage.get_summary()

    if summary["total_actions"] == 0:
        click.echo("No agent activity recorded yet. Run `agentwatch watch` first.")
        return

    click.echo(click.style("📊 AgentWatch Status", fg="cyan", bold=True))
    click.echo(f"   Actions  : {summary['total_actions']}")
    click.echo(f"   Tokens   : {summary['total_tokens']:,}")
    click.echo(f"   Cost     : ${summary['total_cost']:.4f}")
    click.echo(f"   Agents   : {', '.join(summary['agents']) or 'none'}")
    click.echo(f"   Since    : {summary['since']}")

    if summary["recent_actions"]:
        click.echo(click.style("\n⏱  Recent Actions", fg="cyan"))
        for action in summary["recent_actions"][-10:]:
            ts = action["timestamp"][:19]
            agent = click.style(action["agent"], fg="blue")
            act = action["action"]
            cost = f"[${action['cost']:.4f}]" if action["cost"] else ""
            click.echo(f"   [{ts}] {agent} → {act} {cost}")


@cli.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def clear(confirm):
    """Delete all stored agent logs."""
    if not confirm:
        click.confirm("This will delete all AgentWatch logs. Continue?", abort=True)
    storage = Storage()
    storage.clear()
    click.echo(click.style("✓ Logs cleared.", fg="green"))


@cli.command()
@click.argument("output", default="agentwatch-export.json")
def export(output):
    """Export all logs to JSON."""
    import json
    storage = Storage()
    data = storage.export_all()
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    click.echo(click.style(f"✓ Exported {len(data['actions'])} actions to {output}", fg="green"))


@cli.command()
def config():
    """Show proxy configuration for your AI tools."""
    click.echo(click.style("⚙️  AgentWatch Proxy Config", fg="cyan", bold=True))
    click.echo()
    click.echo("Set these environment variables BEFORE running your AI agent:\n")
    click.echo(click.style("  # OpenAI", fg="yellow"))
    click.echo("  export OPENAI_BASE_URL=http://localhost:8080/openai")
    click.echo()
    click.echo(click.style("  # Anthropic", fg="yellow"))
    click.echo("  export ANTHROPIC_BASE_URL=http://localhost:8080/anthropic")
    click.echo()
    click.echo(click.style("  # Ollama", fg="yellow"))
    click.echo("  export OLLAMA_HOST=http://localhost:8080/ollama")
    click.echo()
    click.echo("Then run your agent as usual — AgentWatch will capture all traffic.")


if __name__ == "__main__":
    cli()
