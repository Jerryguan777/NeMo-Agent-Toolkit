# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CLI entry point for nat analyze command."""

import json
import logging
import sys
from pathlib import Path

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group(invoke_without_command=True)
@click.option(
    "--workflow-output", "-w",
    type=click.Path(exists=True, path_type=Path),
    help="Path to workflow_output.json from nat eval",
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    help="Output directory for reports (default: same as workflow_output)",
)
@click.option(
    "--config", "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to analyze config YAML file",
)
@click.option(
    "--rules", "-r",
    type=click.Path(exists=True, path_type=Path),
    help="Path to custom rules Python file",
)
@click.option(
    "--llm-triage/--no-llm-triage",
    default=True,
    help="Enable LLM triage for unclassified failures (default: enabled)",
)
@click.option(
    "--llm-model",
    default="gpt-4o-mini",
    help="LLM model for triage (default: gpt-4o-mini)",
)
@click.option(
    "--api-key",
    envvar="OPENAI_API_KEY",
    help="API key for LLM triage",
)
@click.pass_context
def analyze_command(
    ctx: click.Context,
    workflow_output: Path | None,
    output: Path | None,
    config: Path | None,
    rules: Path | None,
    llm_triage: bool,
    llm_model: str,
    api_key: str | None,
) -> None:
    """Analyze failures from nat eval workflow output.

    Automatically classifies failures and generates reports with
    ROI-prioritized fix recommendations.

    Example usage:

        nat analyze -w .tmp/workflow_output.json

        nat analyze -w output.json --llm-triage

        nat analyze -w output.json -c config.yaml -r custom_rules.py
    """
    # Store options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["workflow_output"] = workflow_output
    ctx.obj["output"] = output
    ctx.obj["config"] = config
    ctx.obj["rules"] = rules
    ctx.obj["llm_triage"] = llm_triage
    ctx.obj["llm_model"] = llm_model
    ctx.obj["api_key"] = api_key

    # If invoked without subcommand and workflow_output provided, run full pipeline
    if ctx.invoked_subcommand is None:
        if workflow_output:
            ctx.invoke(run_pipeline)
        else:
            click.echo(ctx.get_help())


@analyze_command.command("pipeline")
@click.pass_context
def run_pipeline(ctx: click.Context) -> None:
    """Run full analysis pipeline: export -> classify -> report."""
    opts = ctx.obj

    workflow_output = opts["workflow_output"]
    if not workflow_output:
        raise click.UsageError("--workflow-output is required")

    from nat.analyze.classifier import RuleBasedClassifier, RuleRegistry
    from nat.analyze.dashboard import FailureDashboard
    from nat.analyze.exporter import WorkflowExporter

    # Load custom config if provided
    if opts["config"]:
        RuleRegistry.load_from_yaml(opts["config"])

    # Load custom rules if provided
    if opts["rules"]:
        RuleRegistry.load_from_python(opts["rules"])

    # Step 1: Export failures
    exporter = WorkflowExporter()
    # Auto-detect accuracy_output.json in the same directory
    accuracy_output = workflow_output.parent / "accuracy_output.json"
    packets = exporter.load_from_workflow_output(
        workflow_output,
        accuracy_output_path=accuracy_output if accuracy_output.exists() else None,
    )
    click.echo(f"Exported {len(packets)} failure packets")

    if not packets:
        click.echo("No failures found!")
        return

    # Step 2: Rule-based classification
    classifier = RuleBasedClassifier()
    rule_classified, needs_llm = classifier.classify_batch(packets)

    # Step 3: LLM triage (if enabled)
    if opts["llm_triage"] and needs_llm:
        from nat.analyze.llm_triage import LLMTriage

        triage = LLMTriage(
            model=opts["llm_model"],
            api_key=opts["api_key"],
            config_path=opts["config"],
        )
        triage.triage_batch(needs_llm)

    all_packets = rule_classified + needs_llm

    # Step 4: Generate reports
    dashboard = FailureDashboard(all_packets)

    output_dir = opts["output"] or workflow_output.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save packets
    packets_path = output_dir / "failure_packets.jsonl"
    exporter.save_packets(all_packets, packets_path)

    # Generate HTML report
    report_path = output_dir / "failure_report.html"
    dashboard.generate_html_report(report_path)

    # Save JSON summary
    summary = dashboard.generate_summary()
    summary_path = output_dir / "failure_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    click.echo("\n" + "=" * 60)
    click.echo("FAILURE ANALYSIS COMPLETE")
    click.echo("=" * 60)
    click.echo(f"Total failures: {summary['total_failures']}")
    click.echo(f"Rule classified: {summary['rule_classified']}")
    click.echo(f"LLM classified: {summary['llm_classified']}")
    click.echo("\nCategory Distribution:")
    for cat, count in summary["category_distribution"].items():
        click.echo(f"  - {cat}: {count}")
    click.echo("\nTop Priorities:")
    for i, p in enumerate(summary["top_priorities"][:5], 1):
        click.echo(f"  {i}. {p['category']} (count={p['count']}, effort={p['effort']})")
        click.echo(f"     Fix: {p['fix_template']}")
    click.echo("\nOutput files:")
    click.echo(f"  - Packets: {packets_path}")
    click.echo(f"  - Report: {report_path}")
    click.echo(f"  - Summary: {summary_path}")
    click.echo("=" * 60)


@analyze_command.command("export")
@click.option(
    "--workflow-output", "-w",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to workflow_output.json",
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    required=True,
    help="Output path for failure_packets.jsonl",
)
def export_failures(workflow_output: Path, output: Path) -> None:
    """Export failure packets from workflow_output.json."""
    from nat.analyze.exporter import WorkflowExporter

    exporter = WorkflowExporter()
    packets = exporter.load_from_workflow_output(workflow_output)
    exporter.save_packets(packets, output)

    click.echo(f"Exported {len(packets)} failure packets to {output}")


@analyze_command.command("report")
@click.option(
    "--packets", "-p",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to failure_packets.jsonl",
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    help="Output directory for report",
)
def generate_report(packets: Path, output: Path | None) -> None:
    """Generate HTML report from classified packets."""
    from nat.analyze.dashboard import FailureDashboard
    from nat.analyze.exporter import WorkflowExporter

    exporter = WorkflowExporter()
    packet_list = exporter.load_packets(packets)

    dashboard = FailureDashboard(packet_list)

    output_dir = output or packets.parent
    report_path = output_dir / "failure_report.html"
    dashboard.generate_html_report(report_path)

    summary = dashboard.generate_summary()
    summary_path = output_dir / "failure_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    click.echo(f"Generated report: {report_path}")
    click.echo(f"Generated summary: {summary_path}")


@analyze_command.command("list-rules")
@click.option(
    "--config", "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to analyze config YAML file",
)
@click.option(
    "--rules", "-r",
    type=click.Path(exists=True, path_type=Path),
    help="Path to custom rules Python file",
)
def list_rules(config: Path | None, rules: Path | None) -> None:
    """List all available classification rules."""
    from nat.analyze.classifier import RuleRegistry

    if config:
        RuleRegistry.load_from_yaml(config)
    if rules:
        RuleRegistry.load_from_python(rules)

    rule_list = RuleRegistry.list_rules()

    click.echo("\nAvailable Classification Rules:")
    click.echo("-" * 60)
    for rule in rule_list:
        status = "enabled" if rule["enabled"] else "disabled"
        click.echo(
            f"  {rule['name']:<25} "
            f"category={rule['category']:<20} "
            f"priority={rule['priority']:<3} "
            f"[{status}]"
        )
    click.echo("-" * 60)
    click.echo(f"Total: {len(rule_list)} rules")


@analyze_command.command("list-categories")
def list_categories() -> None:
    """List all failure categories."""
    from nat.analyze.models import FailureCategory

    click.echo("\nFailure Categories:")
    click.echo("-" * 60)

    click.echo("\nRule-based (detectable without LLM):")
    rule_cats = [
        "tool_timeout", "tool_rate_limit", "tool_server_error",
        "tool_parameter_error", "output_format", "output_empty",
        "context_overflow", "resource_exhaustion", "recursion_limit",
        "network_error", "auth_failure", "retrieval_empty",
    ]
    for cat in rule_cats:
        click.echo(f"  - {cat}")

    click.echo("\nLLM-based (requires semantic analysis):")
    llm_cats = [
        "task_understanding", "planning_decomposition", "tool_selection",
        "evidence_utilization", "reasoning_calculation", "state_memory",
        "policy_safety",
    ]
    for cat in llm_cats:
        click.echo(f"  - {cat}")

    # Show custom categories if any
    custom = list(FailureCategory._custom_categories.keys())
    if custom:
        click.echo("\nCustom categories:")
        for cat in custom:
            click.echo(f"  - {cat}")

    click.echo("-" * 60)


if __name__ == "__main__":
    analyze_command()
