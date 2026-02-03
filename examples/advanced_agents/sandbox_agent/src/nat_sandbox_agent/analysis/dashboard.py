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

"""Failure dashboard - generates HTML reports with ROI-prioritized recommendations."""

import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from nat_sandbox_agent.analysis.models import CategoryStats
from nat_sandbox_agent.analysis.models import FailureCategory
from nat_sandbox_agent.analysis.models import FailurePacket
from nat_sandbox_agent.analysis.models import PriorityScore

logger = logging.getLogger(__name__)


class FailureDashboard:
    """Generate failure analysis dashboard and reports."""

    # Impact weights by category (1-5 scale)
    # Supports both FailureCategory enum and string-based categories from hybrid analyzer
    IMPACT_WEIGHTS: dict[FailureCategory | str, float] = {
        # Legacy FailureCategory
        FailureCategory.TOOL_TIMEOUT: 3.0,
        FailureCategory.TOOL_RATE_LIMIT: 2.0,
        FailureCategory.TOOL_SERVER_ERROR: 3.0,
        FailureCategory.TOOL_PARAMETER_ERROR: 4.0,
        FailureCategory.OUTPUT_FORMAT: 2.0,
        FailureCategory.RETRIEVAL_EMPTY: 3.0,
        FailureCategory.CONTEXT_OVERFLOW: 4.0,
        FailureCategory.TASK_UNDERSTANDING: 5.0,
        FailureCategory.PLANNING_DECOMPOSITION: 5.0,
        FailureCategory.TOOL_SELECTION: 4.0,
        FailureCategory.EVIDENCE_UTILIZATION: 4.0,
        FailureCategory.REASONING_CALCULATION: 5.0,
        FailureCategory.STATE_MEMORY: 4.0,
        FailureCategory.POLICY_SAFETY: 5.0,
        FailureCategory.UNKNOWN: 1.0,
        # Hybrid analyzer RootCauseCategory (string-based)
        "evidence_extraction": 4.0,
        "reasoning_error": 5.0,
        "output_format": 2.0,
        "iteration_limit": 3.0,
        "evidence_utilization": 4.0,
        "task_understanding": 5.0,
        "api_error": 3.0,
        "tool_limitation": 3.0,
        "partial_answer": 3.0,
        "data_unavailable": 2.0,
        "other_needs_review": 1.0,
        "error": 1.0,
    }

    # Effort weights by category (1=easy, 3=hard)
    EFFORT_WEIGHTS: dict[FailureCategory | str, float] = {
        # Legacy FailureCategory
        FailureCategory.TOOL_TIMEOUT: 1.0,
        FailureCategory.TOOL_RATE_LIMIT: 1.0,
        FailureCategory.TOOL_SERVER_ERROR: 1.0,
        FailureCategory.TOOL_PARAMETER_ERROR: 2.0,
        FailureCategory.OUTPUT_FORMAT: 1.0,
        FailureCategory.RETRIEVAL_EMPTY: 2.0,
        FailureCategory.CONTEXT_OVERFLOW: 2.0,
        FailureCategory.TASK_UNDERSTANDING: 3.0,
        FailureCategory.PLANNING_DECOMPOSITION: 3.0,
        FailureCategory.TOOL_SELECTION: 2.0,
        FailureCategory.EVIDENCE_UTILIZATION: 2.0,
        FailureCategory.REASONING_CALCULATION: 3.0,
        FailureCategory.STATE_MEMORY: 2.0,
        FailureCategory.POLICY_SAFETY: 2.0,
        FailureCategory.UNKNOWN: 3.0,
        # Hybrid analyzer RootCauseCategory (string-based)
        "evidence_extraction": 2.0,
        "reasoning_error": 3.0,
        "output_format": 1.0,
        "iteration_limit": 2.0,
        "evidence_utilization": 2.0,
        "task_understanding": 3.0,
        "api_error": 1.0,
        "tool_limitation": 2.0,
        "partial_answer": 2.0,
        "data_unavailable": 1.0,
        "other_needs_review": 3.0,
        "error": 3.0,
    }

    # Fix templates by category
    FIX_TEMPLATES: dict[FailureCategory | str, str] = {
        # Legacy FailureCategory
        FailureCategory.TOOL_TIMEOUT: "Add retry with exponential backoff + configurable timeout",
        FailureCategory.TOOL_RATE_LIMIT: "Add rate limiting + request queuing + fallback",
        FailureCategory.TOOL_SERVER_ERROR: "Add retry with fallback + circuit breaker",
        FailureCategory.TOOL_PARAMETER_ERROR: "Improve tool description + parameter validation",
        FailureCategory.OUTPUT_FORMAT: "Add JSON schema validation + repair loop",
        FailureCategory.RETRIEVAL_EMPTY: "Add query reformulation + fallback search",
        FailureCategory.CONTEXT_OVERFLOW: "Add context summarization middleware",
        FailureCategory.TASK_UNDERSTANDING: "Improve system prompt clarity + add task examples",
        FailureCategory.PLANNING_DECOMPOSITION: "Add explicit planning step + verification",
        FailureCategory.TOOL_SELECTION: "Improve tool descriptions + add few-shot examples",
        FailureCategory.EVIDENCE_UTILIZATION: "Add claim-evidence binding + verification",
        FailureCategory.REASONING_CALCULATION: "Add self-check step + lightweight verifier",
        FailureCategory.STATE_MEMORY: "Add explicit state tracking + scratchpad",
        FailureCategory.POLICY_SAFETY: "Add policy checks + refusal templates",
        FailureCategory.UNKNOWN: "Manual investigation required",
        # Hybrid analyzer RootCauseCategory (string-based)
        "evidence_extraction": "Add structured data extraction + verification step",
        "reasoning_error": "Add calculation verification + self-check step",
        "output_format": "Add format verification + auto-correction step",
        "iteration_limit": "Increase max iterations + add task complexity estimation",
        "evidence_utilization": "Add claim-evidence binding + verification",
        "task_understanding": "Improve system prompt clarity + add task examples",
        "api_error": "Add retry with exponential backoff + fallback",
        "tool_limitation": "Pre-install dependencies + add capability check",
        "partial_answer": "Add completeness verification step",
        "data_unavailable": "Add fallback data sources + archive.org lookup",
        "other_needs_review": "Manual investigation required",
        "error": "Investigation required",
    }

    def __init__(self, packets: list[FailurePacket]):
        """Initialize dashboard with failure packets.

        Args:
            packets: List of classified failure packets.
        """
        self.packets = packets
        self.total_failures = len(packets)

    def get_category_stats(self) -> dict[FailureCategory | str, CategoryStats]:
        """Calculate statistics for each failure category.

        Supports both FailureCategory enum and string-based categories from hybrid analyzer.
        """
        # Count by category - normalize to string for comparison
        category_counts: Counter = Counter()
        for p in self.packets:
            if p.failure_category:
                # Handle both enum and string
                cat = p.failure_category.value if isinstance(p.failure_category, FailureCategory) else p.failure_category
                category_counts[cat] += 1

        stats = {}

        # Include all standard FailureCategory enum values
        for category in FailureCategory:
            count = category_counts.get(category.value, 0)
            percentage = (count / self.total_failures * 100) if self.total_failures > 0 else 0

            # Get example task IDs
            examples = [
                p.task_id
                for p in self.packets
                if (p.failure_category.value if isinstance(p.failure_category, FailureCategory) else p.failure_category) == category.value
            ][:5]

            stats[category] = CategoryStats(
                category=category,
                count=count,
                percentage=percentage,
                example_task_ids=examples,
                has_test_cases=count > 0,
            )

        # Include any string-based categories from hybrid analyzer
        hybrid_categories = {"evidence_extraction", "reasoning_error", "output_format",
                           "iteration_limit", "evidence_utilization", "task_understanding",
                           "api_error", "tool_limitation", "partial_answer",
                           "data_unavailable", "other_needs_review", "error"}

        for cat_str in hybrid_categories:
            if cat_str in category_counts:
                count = category_counts[cat_str]
                percentage = (count / self.total_failures * 100) if self.total_failures > 0 else 0

                examples = [
                    p.task_id
                    for p in self.packets
                    if (p.failure_category.value if isinstance(p.failure_category, FailureCategory) else p.failure_category) == cat_str
                ][:5]

                # Use a placeholder FailureCategory for CategoryStats (which requires enum)
                # We'll handle this in generate_summary by converting to string
                stats[cat_str] = CategoryStats(
                    category=FailureCategory.UNKNOWN,  # Placeholder
                    count=count,
                    percentage=percentage,
                    example_task_ids=examples,
                    has_test_cases=count > 0,
                )

        return stats

    def calculate_priority(self, category: FailureCategory | str, stats: CategoryStats) -> dict[str, Any]:
        """Calculate ROI priority score for a category.

        Priority = frequency × impact × fixability × verifiability

        Returns dict instead of PriorityScore to support string categories.
        """
        frequency = stats.count / self.total_failures if self.total_failures > 0 else 0
        impact = self.IMPACT_WEIGHTS.get(category, 1.0)
        fixability = 1.0 / self.EFFORT_WEIGHTS.get(category, 3.0)
        verifiability = 1.0 if stats.has_test_cases else 0.5

        score = frequency * impact * fixability * verifiability

        effort = self.EFFORT_WEIGHTS.get(category, 3.0)
        effort_level = "Low" if effort <= 1.5 else ("Medium" if effort <= 2.5 else "High")

        # Get category name as string
        cat_str = category.value if isinstance(category, FailureCategory) else category

        return {
            "category": cat_str,
            "score": score,
            "frequency": frequency,
            "impact": impact,
            "fixability": fixability,
            "verifiability": verifiability,
            "fix_template": self.FIX_TEMPLATES.get(category, ""),
            "effort_level": effort_level,
            "count": stats.count,
        }

    def get_priority_ranking(self) -> list[dict[str, Any]]:
        """Get categories ranked by priority score."""
        stats = self.get_category_stats()

        priorities = []
        for category, cat_stats in stats.items():
            if cat_stats.count > 0:  # Only include categories with failures
                priority = self.calculate_priority(category, cat_stats)
                priorities.append(priority)

        # Sort by score descending
        priorities.sort(key=lambda p: p["score"], reverse=True)

        return priorities

    def generate_summary(self) -> dict[str, Any]:
        """Generate summary statistics."""
        stats = self.get_category_stats()
        priorities = self.get_priority_ranking()

        # Count by classification source
        rule_count = sum(1 for p in self.packets if p.classification_source == "rule")
        llm_count = sum(1 for p in self.packets if p.classification_source == "llm")
        hybrid_count = sum(1 for p in self.packets if p.classification_source and p.classification_source.startswith("hybrid"))

        # Build category distribution - handle both enum and string categories
        category_distribution = {}
        for cat, stat in stats.items():
            if stat.count > 0:
                cat_str = cat.value if isinstance(cat, FailureCategory) else cat
                category_distribution[cat_str] = stat.count

        return {
            "total_failures": self.total_failures,
            "rule_classified": rule_count,
            "llm_classified": llm_count,
            "hybrid_classified": hybrid_count,
            "category_distribution": category_distribution,
            "top_priorities": [
                {
                    "category": p["category"],
                    "score": round(p["score"], 4),
                    "count": p["count"],
                    "fix_template": p["fix_template"],
                    "effort": p["effort_level"],
                }
                for p in priorities[:5]
            ],
        }

    def generate_html_report(self, output_path: Path) -> None:
        """Generate HTML dashboard report.

        Args:
            output_path: Path to save the HTML report.
        """
        stats = self.get_category_stats()
        priorities = self.get_priority_ranking()
        summary = self.generate_summary()

        html = self._build_html(stats, priorities, summary)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)

        logger.info(f"Generated HTML report: {output_path}")

    def _build_html(
        self,
        stats: dict[FailureCategory | str, CategoryStats],
        priorities: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> str:
        """Build HTML content."""
        # Category distribution chart data - handle both enum and string categories
        chart_data = [
            {"category": cat.value if isinstance(cat, FailureCategory) else cat, "count": stat.count}
            for cat, stat in stats.items()
            if stat.count > 0
        ]
        chart_data.sort(key=lambda x: x["count"], reverse=True)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Failure Analysis Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        header h1 {{
            font-size: 2em;
            margin-bottom: 10px;
        }}
        header p {{
            opacity: 0.9;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .stat-card .number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-card .label {{
            color: #666;
            font-size: 0.9em;
        }}
        .section {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .section h2 {{
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        .chart-container {{
            height: 300px;
            position: relative;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .priority-high {{
            background: #fee2e2;
            color: #dc2626;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
        }}
        .priority-medium {{
            background: #fef3c7;
            color: #d97706;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
        }}
        .priority-low {{
            background: #d1fae5;
            color: #059669;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
        }}
        .effort-badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
        }}
        .effort-Low {{
            background: #d1fae5;
            color: #059669;
        }}
        .effort-Medium {{
            background: #fef3c7;
            color: #d97706;
        }}
        .effort-High {{
            background: #fee2e2;
            color: #dc2626;
        }}
        .fix-template {{
            font-family: monospace;
            background: #f3f4f6;
            padding: 8px;
            border-radius: 4px;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        .failure-detail {{
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            margin-bottom: 15px;
            overflow: hidden;
        }}
        .failure-header {{
            background: #f9fafb;
            padding: 15px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .failure-header:hover {{
            background: #f3f4f6;
        }}
        .failure-body {{
            padding: 15px;
            display: none;
            border-top: 1px solid #e5e7eb;
        }}
        .failure-body.active {{
            display: block;
        }}
        .task-id {{
            font-family: monospace;
            font-size: 0.9em;
            color: #6b7280;
        }}
        .root-cause-section, .fix-suggestions-section, .error-spans-section {{
            margin: 15px 0;
            padding: 12px;
            border-radius: 6px;
        }}
        .root-cause-section {{
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
        }}
        .evidence-box {{
            font-family: monospace;
            font-size: 0.9em;
            white-space: pre-wrap;
            word-break: break-word;
            margin-top: 8px;
            padding: 8px;
            background: rgba(255,255,255,0.5);
            border-radius: 4px;
        }}
        .fix-suggestions-section {{
            background: #d1fae5;
            border-left: 4px solid #10b981;
        }}
        .suggestions-list {{
            margin: 8px 0 0 20px;
        }}
        .suggestions-list li {{
            margin: 4px 0;
        }}
        .error-spans-section {{
            background: #fee2e2;
            border-left: 4px solid #ef4444;
        }}
        .error-list {{
            margin: 8px 0 0 20px;
        }}
        .error-list li {{
            margin: 6px 0;
        }}
        .error-list code {{
            display: block;
            margin-top: 4px;
            padding: 4px 8px;
            background: rgba(255,255,255,0.5);
            border-radius: 4px;
            font-size: 0.85em;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Agent Failure Analysis Report</h1>
            <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="number">{summary['total_failures']}</div>
                <div class="label">Total Failures</div>
            </div>
            <div class="stat-card">
                <div class="number">{summary['rule_classified']}</div>
                <div class="label">Rule Classified</div>
            </div>
            <div class="stat-card">
                <div class="number">{summary['llm_classified']}</div>
                <div class="label">LLM Classified</div>
            </div>
            <div class="stat-card">
                <div class="number">{len([p for p in priorities if (p["score"] if isinstance(p, dict) else p.score) > 0])}</div>
                <div class="label">Categories Found</div>
            </div>
        </div>

        <div class="section">
            <h2>Failure Distribution</h2>
            <div class="chart-container">
                <canvas id="distributionChart"></canvas>
            </div>
        </div>

        <div class="section">
            <h2>Priority Ranking (ROI-based)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Category</th>
                        <th>Count</th>
                        <th>Priority Score</th>
                        <th>Effort</th>
                        <th>Fix Template</th>
                    </tr>
                </thead>
                <tbody>
                    {self._build_priority_rows(priorities, stats)}
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2>Failure Details</h2>
            {self._build_failure_details()}
        </div>

        <footer>
            <p>NAT Sandbox Agent - Failure Analysis Pipeline</p>
        </footer>
    </div>

    <script>
        // Chart.js configuration
        const ctx = document.getElementById('distributionChart').getContext('2d');
        const chartData = {self._json_encode(chart_data)};

        new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: chartData.map(d => d.category),
                datasets: [{{
                    label: 'Failure Count',
                    data: chartData.map(d => d.count),
                    backgroundColor: 'rgba(102, 126, 234, 0.8)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{ beginAtZero: true }}
                }}
            }}
        }});

        // Toggle failure details
        document.querySelectorAll('.failure-header').forEach(header => {{
            header.addEventListener('click', () => {{
                const body = header.nextElementSibling;
                body.classList.toggle('active');
            }});
        }});
    </script>
</body>
</html>"""

        return html

    def _build_priority_rows(
        self, priorities: list[PriorityScore], stats: dict[FailureCategory, CategoryStats]
    ) -> str:
        """Build HTML rows for priority table."""
        rows = []
        for i, p in enumerate(priorities, 1):
            # Handle both dict (new format) and PriorityScore (legacy)
            if isinstance(p, dict):
                category = p["category"]
                count = p["count"]
                score = p["score"]
                effort_level = p["effort_level"]
                fix_template = p["fix_template"]
            else:
                category = p.category.value if isinstance(p.category, FailureCategory) else p.category
                count = stats.get(p.category, stats.get(category, CategoryStats(category=FailureCategory.UNKNOWN, count=0, percentage=0))).count
                score = p.score
                effort_level = p.effort_level
                fix_template = p.fix_template

            effort_class = f"effort-{effort_level}"
            rows.append(f"""
                <tr>
                    <td>{i}</td>
                    <td><strong>{category}</strong></td>
                    <td>{count}</td>
                    <td>{score:.4f}</td>
                    <td><span class="effort-badge {effort_class}">{effort_level}</span></td>
                    <td><div class="fix-template">{fix_template}</div></td>
                </tr>
            """)
        return "".join(rows)

    def _build_failure_details(self) -> str:
        """Build HTML for failure detail cards."""
        details = []
        for packet in self.packets[:20]:  # Limit to first 20
            # Handle both enum and string categories
            if packet.failure_category:
                category = packet.failure_category.value if isinstance(packet.failure_category, FailureCategory) else packet.failure_category
            else:
                category = "unknown"

            # Build root cause section
            root_cause_html = ""
            if packet.root_cause_evidence:
                root_cause_html = f"""
                        <div class="root-cause-section">
                            <p><strong>🔍 Root Cause:</strong></p>
                            <div class="evidence-box">{self._escape_html(packet.root_cause_evidence)}</div>
                        </div>
                """

            # Build fix suggestions section
            fix_suggestions_html = ""
            if packet.fix_suggestions:
                suggestions = "".join(
                    f"<li>{self._escape_html(s)}</li>" for s in packet.fix_suggestions
                )
                fix_suggestions_html = f"""
                        <div class="fix-suggestions-section">
                            <p><strong>💡 Fix Suggestions:</strong></p>
                            <ul class="suggestions-list">{suggestions}</ul>
                        </div>
                """

            # Build key spans section
            key_spans_html = ""
            if packet.key_span_ids:
                key_spans_html = f"""
                        <p><strong>📍 Key Spans:</strong> <code>{', '.join(packet.key_span_ids[:3])}</code></p>
                """

            # Build error spans section (tool errors)
            error_spans_html = ""
            error_spans = [s for s in packet.spans if s.status == "ERROR" and s.error_message]
            if error_spans:
                error_items = []
                for span in error_spans[:3]:  # Limit to 3 errors
                    error_items.append(
                        f"<li><strong>{span.tool_name or span.name}:</strong> "
                        f"<code>{self._escape_html(span.error_message[:200])}</code></li>"
                    )
                error_spans_html = f"""
                        <div class="error-spans-section">
                            <p><strong>❌ Tool Errors:</strong></p>
                            <ul class="error-list">{''.join(error_items)}</ul>
                        </div>
                """

            details.append(f"""
                <div class="failure-detail">
                    <div class="failure-header">
                        <div>
                            <strong>{category}</strong>
                            <span class="task-id">{packet.task_id[:8]}...</span>
                        </div>
                        <span>▼</span>
                    </div>
                    <div class="failure-body">
                        <p><strong>Question:</strong> {self._escape_html(packet.user_request[:300])}...</p>
                        <p><strong>Expected:</strong> {self._escape_html(packet.expected_output)}</p>
                        <p><strong>Actual:</strong> {self._escape_html(packet.actual_output)}</p>
                        {root_cause_html}
                        {error_spans_html}
                        {fix_suggestions_html}
                        {key_spans_html}
                        <p><strong>Classification:</strong> {packet.classification_source or 'N/A'}
                           (confidence: {packet.classification_confidence or 'N/A'})</p>
                    </div>
                </div>
            """)
        return "".join(details)

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def _json_encode(self, data: Any) -> str:
        """JSON encode for embedding in HTML."""
        import json

        return json.dumps(data)
