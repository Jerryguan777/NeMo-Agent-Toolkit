# SPDX-FileCopyrightText: Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

"""CLI entry point for failure analysis pipeline.

NOTE: This is a standalone CLI for the sandbox_agent example.
For production use, prefer using `nat analyze` command from the main NAT CLI.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from nat_sandbox_agent.analysis.dashboard import FailureDashboard
from nat_sandbox_agent.analysis.hybrid_analyzer import run_hybrid_analysis
from nat_sandbox_agent.analysis.workflow_exporter import WorkflowExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_export(args: argparse.Namespace) -> int:
    """Export failure packets from workflow_output.json."""
    exporter = WorkflowExporter()

    workflow_path = Path(args.workflow_output)
    if not workflow_path.exists():
        logger.error(f"File not found: {workflow_path}")
        return 1

    packets = exporter.load_from_workflow_output(workflow_path)

    output_path = Path(args.output)
    exporter.save_packets(packets, output_path)

    logger.info(f"Exported {len(packets)} failure packets to {output_path}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Run hybrid LLM-based failure analysis."""
    exporter = WorkflowExporter()

    # Load packets from workflow_output.json or failure_packets.jsonl
    if args.workflow_output:
        workflow_path = Path(args.workflow_output)
        if not workflow_path.exists():
            logger.error(f"File not found: {workflow_path}")
            return 1
        packets = exporter.load_from_workflow_output(workflow_path)
    elif args.packets:
        packets_path = Path(args.packets)
        if not packets_path.exists():
            logger.error(f"File not found: {packets_path}")
            return 1
        packets = exporter.load_packets(packets_path)
    else:
        logger.error("Either --workflow-output or --packets is required")
        return 1

    logger.info(f"Loaded {len(packets)} failure packets")

    if not packets:
        logger.info("No failures found!")
        return 0

    # Determine output directory
    if args.output:
        output_dir = Path(args.output)
    elif args.workflow_output:
        output_dir = Path(args.workflow_output).parent
    else:
        output_dir = Path(args.packets).parent

    # Run hybrid analysis
    stats = asyncio.run(
        run_hybrid_analysis(
            packets=packets,
            output_dir=output_dir,
            concurrency=args.concurrency,
            confidence_threshold=args.confidence_threshold,
        )
    )

    # Save packets with updated classifications
    packets_path = output_dir / "failure_packets.jsonl"
    exporter.save_packets(packets, packets_path)

    # Generate dashboard report
    dashboard = FailureDashboard(packets)
    report_path = output_dir / "failure_report.html"
    dashboard.generate_html_report(report_path)

    # Save summary
    summary = dashboard.generate_summary()
    summary["hybrid_stats"] = stats
    summary_path = output_dir / "failure_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nOutput files:")
    print(f"  - Packets: {packets_path}")
    print(f"  - Report: {report_path}")
    print(f"  - Summary: {summary_path}")
    print(f"  - Analysis: {output_dir / 'hybrid_analysis_results.json'}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Hybrid LLM-based Failure Analysis Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
NOTE: For production use, prefer `nat analyze` command from the main NAT CLI.

Examples:
  # Analyze failures from workflow output
  python -m nat_sandbox_agent.analysis.cli analyze -w workflow_output.json

  # Export failure packets only
  python -m nat_sandbox_agent.analysis.cli export -w workflow_output.json -o packets.jsonl
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export failure packets")
    export_parser.add_argument(
        "--workflow-output", "-w",
        required=True,
        help="Path to workflow_output.json",
    )
    export_parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output path for failure_packets.jsonl",
    )

    # Analyze command (main command)
    analyze_parser = subparsers.add_parser(
        "analyze", help="Run hybrid LLM-based failure analysis"
    )
    analyze_parser.add_argument(
        "--workflow-output", "-w",
        help="Path to workflow_output.json",
    )
    analyze_parser.add_argument(
        "--packets", "-p",
        help="Path to failure_packets.jsonl (alternative to --workflow-output)",
    )
    analyze_parser.add_argument(
        "--output", "-o",
        help="Output directory (default: same as input)",
    )
    analyze_parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Maximum concurrent API calls (default: 5)",
    )
    analyze_parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.8,
        help="Confidence threshold for deep analysis (default: 0.8)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "export": cmd_export,
        "analyze": cmd_analyze,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
