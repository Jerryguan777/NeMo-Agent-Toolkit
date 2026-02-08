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

import asyncio
import json
import logging
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
    "--model", "-m",
    default="gpt-5.2",
    show_default=True,
    help="LLM model for analysis",
)
@click.option(
    "--base-url",
    help="Custom API base URL",
)
@click.option(
    "--api-key",
    envvar="OPENAI_API_KEY",
    help="API key for LLM calls",
)
@click.option(
    "--concurrency",
    default=5,
    show_default=True,
    type=int,
    help="Number of concurrent LLM calls for per-task analysis",
)
@click.pass_context
def analyze_command(
    ctx: click.Context,
    workflow_output: Path | None,
    output: Path | None,
    model: str,
    base_url: str | None,
    api_key: str | None,
    concurrency: int,
) -> None:
    """Analyze failures from nat eval workflow output.

    Uses LLM to analyze each failed task's execution trace, identify root causes,
    and group similar failures by fingerprint.

    Example usage:

        nat analyze -w .tmp/workflow_output.json

        nat analyze -w output.json -m gpt-5.2 --concurrency 10

        nat analyze -w output.json --base-url https://custom-api.example.com/v1
    """
    ctx.ensure_object(dict)
    ctx.obj["workflow_output"] = workflow_output
    ctx.obj["output"] = output
    ctx.obj["model"] = model
    ctx.obj["base_url"] = base_url
    ctx.obj["api_key"] = api_key
    ctx.obj["concurrency"] = concurrency

    if ctx.invoked_subcommand is None:
        if workflow_output:
            ctx.invoke(run_pipeline)
        else:
            click.echo(ctx.get_help())


@analyze_command.command("pipeline")
@click.pass_context
def run_pipeline(ctx: click.Context) -> None:
    """Run full analysis pipeline: export -> analyze -> report."""
    opts = ctx.obj

    workflow_output = opts["workflow_output"]
    if not workflow_output:
        raise click.UsageError("--workflow-output is required")

    from nat.analyze.analyzer import FailureAnalyzer
    from nat.analyze.dashboard import FailureDashboard
    from nat.analyze.exporter import load_from_workflow_output

    # Step 1: Export failures
    accuracy_output = workflow_output.parent / "accuracy_output.json"
    analyses, total_tasks = load_from_workflow_output(
        workflow_output,
        accuracy_output_path=accuracy_output if accuracy_output.exists() else None,
    )
    click.echo(f"Exported {len(analyses)} failed tasks (out of {total_tasks} total)")

    if not analyses:
        click.echo("No failures found!")
        return

    # Step 2: LLM analysis
    analyzer = FailureAnalyzer(
        model=opts["model"],
        api_key=opts["api_key"],
        base_url=opts["base_url"],
        concurrency=opts["concurrency"],
    )
    click.echo(f"Analyzing with {opts['model']} (concurrency={opts['concurrency']})...")
    asyncio.run(analyzer.analyze_all(analyses))

    # Step 3: Build report
    report = analyzer.build_report(analyses, total_tasks)

    # Step 4: Generate outputs
    output_dir = opts["output"] or workflow_output.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    dashboard = FailureDashboard(report)

    report_path = output_dir / "failure_report.html"
    dashboard.generate_html_report(report_path)

    json_path = output_dir / "failure_analysis.json"
    dashboard.generate_json_report(json_path)

    # Print summary
    click.echo("\n" + "=" * 60)
    click.echo("FAILURE ANALYSIS COMPLETE")
    click.echo("=" * 60)
    click.echo(f"Total tasks: {report.total_tasks}")
    click.echo(f"Total failures: {report.total_failures}")
    click.echo(f"Failure groups: {len(report.fingerprint_groups)}")
    click.echo(f"Model: {report.model_used}")

    if report.fingerprint_groups:
        click.echo("\nFingerprint Groups:")
        for g in sorted(report.fingerprint_groups, key=lambda x: x.count, reverse=True):
            click.echo(f"  [{g.count}] {g.group_name}")
            if g.description:
                click.echo(f"      {g.description[:100]}")

    click.echo(f"\nOutput files:")
    click.echo(f"  - Report: {report_path}")
    click.echo(f"  - JSON:   {json_path}")
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
    help="Output path for task_analyses.json",
)
def export_failures(workflow_output: Path, output: Path) -> None:
    """Export failed task data from workflow_output.json (no LLM analysis)."""
    from nat.analyze.exporter import load_from_workflow_output

    analyses, total_tasks = load_from_workflow_output(workflow_output)

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump([a.model_dump() for a in analyses], f, indent=2, ensure_ascii=False)

    click.echo(f"Exported {len(analyses)} failed tasks (out of {total_tasks}) to {output}")


@analyze_command.command("report")
@click.option(
    "--input", "-i",
    "input_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to failure_analysis.json",
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    help="Output directory for HTML report",
)
def generate_report(input_path: Path, output: Path | None) -> None:
    """Generate HTML report from an existing failure_analysis.json."""
    from nat.analyze.dashboard import FailureDashboard
    from nat.analyze.models import AnalysisReport

    with open(input_path) as f:
        data = json.load(f)

    report = AnalysisReport.model_validate(data)
    dashboard = FailureDashboard(report)

    output_dir = output or input_path.parent
    report_path = output_dir / "failure_report.html"
    dashboard.generate_html_report(report_path)

    click.echo(f"Generated report: {report_path}")


@analyze_command.command("list-categories")
def list_categories() -> None:
    """List fingerprint groups from the most recent analysis."""
    click.echo("\nFailure analysis uses free-form LLM-generated fingerprints.")
    click.echo("Run 'nat analyze -w <workflow_output.json>' to see actual failure categories.")
    click.echo("\nThe LLM will automatically:")
    click.echo("  1. Analyze each failed task's execution trace")
    click.echo("  2. Generate a descriptive fingerprint for each failure")
    click.echo("  3. Cluster similar fingerprints into groups")


if __name__ == "__main__":
    analyze_command()
