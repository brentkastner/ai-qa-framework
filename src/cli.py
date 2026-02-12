"""CLI entry point for the QA framework."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from src.models.config import FrameworkConfig
from src.models.test_plan import TestPlan
from src.orchestrator import Orchestrator

console = Console()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """AI-Driven Autonomous Website QA Framework"""
    setup_logging(verbose)


@cli.command()
@click.option("--config", "-c", default="qa-config.json", help="Config file path")
def run(config: str) -> None:
    """Run the full QA pipeline: crawl → plan → execute → report."""
    try:
        cfg = FrameworkConfig.load(config)
    except FileNotFoundError:
        console.print(f"[red]Config file not found: {config}[/red]")
        console.print("Run 'qa-framework init' to create a default config.")
        sys.exit(1)

    orchestrator = Orchestrator(cfg)
    results = orchestrator.run_full_pipeline()

    # Display summary
    console.print("\n[bold green]Pipeline Complete[/bold green]")
    table = Table(title="Results Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Run ID", results["run_id"])
    table.add_row("Duration", f"{results['duration']}s")
    table.add_row("Total Tests", str(results["results"]["total"]))
    table.add_row("Passed", f"[green]{results['results']['passed']}[/green]")
    table.add_row("Failed", f"[red]{results['results']['failed']}[/red]")
    table.add_row("Skipped", f"[yellow]{results['results']['skipped']}[/yellow]")
    table.add_row("Errors", f"[red]{results['results']['errors']}[/red]")
    table.add_row("Coverage", f"{results['coverage']['overall']:.0%}")
    console.print(table)

    for fmt, path in results["reports"].items():
        console.print(f"  {fmt.upper()} report: [blue]{path}[/blue]")


@cli.command()
@click.option("--config", "-c", default="qa-config.json", help="Config file path")
def crawl(config: str) -> None:
    """Crawl the target site and build a site model."""
    cfg = FrameworkConfig.load(config)
    orchestrator = Orchestrator(cfg)
    site_model = orchestrator.run_crawl_only()
    console.print(f"[green]Crawl complete:[/green] {len(site_model.pages)} pages discovered")


@cli.command()
@click.option("--config", "-c", default="qa-config.json", help="Config file path")
def plan(config: str) -> None:
    """Generate a test plan from the existing site model."""
    cfg = FrameworkConfig.load(config)
    orchestrator = Orchestrator(cfg)
    try:
        test_plan = orchestrator.run_plan_only()
        console.print(f"[green]Plan generated:[/green] {len(test_plan.test_cases)} test cases")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--plan-file", "-p", required=True, help="Path to test plan JSON")
@click.option("--config", "-c", default="qa-config.json", help="Config file path")
def execute(plan_file: str, config: str) -> None:
    """Execute a saved test plan."""
    cfg = FrameworkConfig.load(config)
    with open(plan_file) as f:
        plan_data = json.load(f)
    test_plan = TestPlan(**plan_data)

    orchestrator = Orchestrator(cfg)
    result = orchestrator.run_execute_only(test_plan)
    console.print(
        f"[green]Execution complete:[/green] {result.passed} passed, "
        f"{result.failed} failed, {result.skipped} skipped"
    )


@cli.command()
@click.option("--gaps", is_flag=True, help="Show coverage gaps")
@click.option("--reset", is_flag=True, help="Reset coverage registry")
@click.option("--config", "-c", default="qa-config.json", help="Config file path")
def coverage(gaps: bool, reset: bool, config: str) -> None:
    """View or manage coverage data."""
    cfg = FrameworkConfig.load(config)
    orchestrator = Orchestrator(cfg)

    if reset:
        orchestrator.reset_coverage()
        console.print("[green]Coverage registry reset[/green]")
        return

    if gaps:
        try:
            gap_text = orchestrator.get_coverage_gaps()
            console.print(gap_text)
        except FileNotFoundError:
            console.print("[yellow]No site model found. Run 'qa-framework crawl' first.[/yellow]")
        return

    summary = orchestrator.get_coverage_summary()
    console.print(summary)


@cli.command()
@click.option("--target", "-t", prompt="Target URL", help="Website URL to test")
def init(target: str) -> None:
    """Create a default configuration file."""
    config_path = Path("qa-config.json")
    if config_path.exists():
        if not click.confirm("qa-config.json already exists. Overwrite?"):
            return

    cfg = FrameworkConfig(target_url=target)
    cfg.save(config_path)
    console.print(f"[green]Created {config_path}[/green]")
    console.print("\nYou can now customize this file and run:")
    console.print("  [blue]qa-framework run[/blue]")
    console.print("\nOptional: Add hints to guide the AI planner:")
    console.print('  [blue]qa-framework hint add "The checkout flow is critical"[/blue]')


@cli.group()
def hint() -> None:
    """Manage user hints for the AI planner."""
    pass


@hint.command("add")
@click.argument("text")
@click.option("--config", "-c", default="qa-config.json", help="Config file path")
def hint_add(text: str, config: str) -> None:
    """Add a hint to the configuration."""
    cfg = FrameworkConfig.load(config)
    cfg.hints.append(text)
    cfg.save(config)
    console.print(f"[green]Added hint:[/green] {text}")


@hint.command("list")
@click.option("--config", "-c", default="qa-config.json", help="Config file path")
def hint_list(config: str) -> None:
    """List all current hints."""
    cfg = FrameworkConfig.load(config)
    if not cfg.hints:
        console.print("[yellow]No hints configured[/yellow]")
        return
    for i, h in enumerate(cfg.hints, 1):
        console.print(f"  {i}. {h}")


@hint.command("clear")
@click.option("--config", "-c", default="qa-config.json", help="Config file path")
def hint_clear(config: str) -> None:
    """Remove all hints."""
    cfg = FrameworkConfig.load(config)
    cfg.hints = []
    cfg.save(config)
    console.print("[green]All hints cleared[/green]")


if __name__ == "__main__":
    cli()
