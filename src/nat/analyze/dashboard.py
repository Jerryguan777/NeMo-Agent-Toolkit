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

"""Failure dashboard - generates HTML reports with ROI-prioritized recommendations."""

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from nat.analyze.models import (
    CategoryStats,
    FailureCategory,
    FailurePacket,
    PriorityScore,
)

logger = logging.getLogger(__name__)


class FailureDashboard:
    """Generate failure analysis dashboard and reports."""

    # Impact weights by category (1-5 scale)
    IMPACT_WEIGHTS: dict[str, float] = {
        "tool_timeout": 3.0,
        "tool_rate_limit": 2.0,
        "tool_server_error": 3.0,
        "tool_parameter_error": 4.0,
        "output_format": 2.0,
        "output_empty": 2.0,
        "retrieval_empty": 3.0,
        "context_overflow": 4.0,
        "network_error": 3.0,
        "auth_failure": 3.0,
        "resource_exhaustion": 4.0,
        "recursion_limit": 3.0,
        "task_understanding": 5.0,
        "planning_decomposition": 5.0,
        "tool_selection": 4.0,
        "evidence_utilization": 4.0,
        "reasoning_calculation": 5.0,
        "state_memory": 4.0,
        "policy_safety": 5.0,
        "unknown": 1.0,
    }

    # Effort weights (1=easy, 3=hard)
    EFFORT_WEIGHTS: dict[str, float] = {
        "tool_timeout": 1.0,
        "tool_rate_limit": 1.0,
        "tool_server_error": 1.0,
        "tool_parameter_error": 2.0,
        "output_format": 1.0,
        "output_empty": 1.0,
        "retrieval_empty": 2.0,
        "context_overflow": 2.0,
        "network_error": 1.0,
        "auth_failure": 1.0,
        "resource_exhaustion": 2.0,
        "recursion_limit": 1.0,
        "task_understanding": 3.0,
        "planning_decomposition": 3.0,
        "tool_selection": 2.0,
        "evidence_utilization": 2.0,
        "reasoning_calculation": 3.0,
        "state_memory": 2.0,
        "policy_safety": 2.0,
        "unknown": 3.0,
    }

    # Fix templates
    FIX_TEMPLATES: dict[str, str] = {
        "tool_timeout": "Add retry with exponential backoff + configurable timeout",
        "tool_rate_limit": "Add rate limiting + request queuing + fallback",
        "tool_server_error": "Add retry with fallback + circuit breaker",
        "tool_parameter_error": "Improve tool description + parameter validation",
        "output_format": "Add JSON schema validation + repair loop",
        "output_empty": "Add validation to ensure non-empty response",
        "retrieval_empty": "Add query reformulation + fallback search",
        "context_overflow": "Add context summarization middleware",
        "network_error": "Add retry with network error handling",
        "auth_failure": "Check API key/token configuration",
        "resource_exhaustion": "Increase resource limits or optimize usage",
        "recursion_limit": "Increase max_iterations or improve task decomposition",
        "task_understanding": "Improve system prompt clarity + add task examples",
        "planning_decomposition": "Add explicit planning step + verification",
        "tool_selection": "Improve tool descriptions + add few-shot examples",
        "evidence_utilization": "Add claim-evidence binding + verification",
        "reasoning_calculation": "Add self-check step + lightweight verifier",
        "state_memory": "Add explicit state tracking + scratchpad",
        "policy_safety": "Add policy checks + refusal templates",
        "unknown": "Manual investigation required",
    }

    def __init__(self, packets: list[FailurePacket]) -> None:
        """Initialize dashboard with failure packets."""
        self.packets = packets
        self.total_failures = len(packets)

    def _get_category_value(self, cat: FailureCategory | str | None) -> str:
        """Get string value from category."""
        if cat is None:
            return "unknown"
        if isinstance(cat, str):
            return cat
        return cat.value

    def get_category_stats(self) -> dict[str, CategoryStats]:
        """Calculate statistics for each failure category."""
        category_counts = Counter(
            self._get_category_value(p.failure_category) for p in self.packets
        )

        stats = {}
        for cat_value in set(category_counts.keys()) | set(self.IMPACT_WEIGHTS.keys()):
            count = category_counts.get(cat_value, 0)
            percentage = (count / self.total_failures * 100) if self.total_failures > 0 else 0

            examples = [
                p.task_id
                for p in self.packets
                if self._get_category_value(p.failure_category) == cat_value
            ][:5]

            stats[cat_value] = CategoryStats(
                category=cat_value,
                count=count,
                percentage=percentage,
                example_task_ids=examples,
                has_test_cases=count > 0,
            )

        return stats

    def calculate_priority(self, category: str, stats: CategoryStats) -> PriorityScore:
        """Calculate ROI priority score."""
        frequency = stats.count / self.total_failures if self.total_failures > 0 else 0
        impact = self.IMPACT_WEIGHTS.get(category, 2.0)
        fixability = 1.0 / self.EFFORT_WEIGHTS.get(category, 2.0)
        verifiability = 1.0 if stats.has_test_cases else 0.5

        score = frequency * impact * fixability * verifiability

        effort = self.EFFORT_WEIGHTS.get(category, 2.0)
        effort_level = "Low" if effort <= 1.5 else ("Medium" if effort <= 2.5 else "High")

        return PriorityScore(
            category=category,
            score=score,
            frequency=frequency,
            impact=impact,
            fixability=fixability,
            verifiability=verifiability,
            fix_template=self.FIX_TEMPLATES.get(category, "Manual investigation required"),
            effort_level=effort_level,
        )

    def get_priority_ranking(self) -> list[PriorityScore]:
        """Get categories ranked by priority score."""
        stats = self.get_category_stats()

        priorities = []
        for category, cat_stats in stats.items():
            if cat_stats.count > 0:
                priority = self.calculate_priority(category, cat_stats)
                priorities.append(priority)

        priorities.sort(key=lambda p: p.score, reverse=True)
        return priorities

    def generate_summary(self) -> dict[str, Any]:
        """Generate summary statistics."""
        stats = self.get_category_stats()
        priorities = self.get_priority_ranking()

        rule_count = sum(1 for p in self.packets if p.classification_source == "rule")
        llm_count = sum(1 for p in self.packets if p.classification_source == "llm")

        return {
            "total_failures": self.total_failures,
            "rule_classified": rule_count,
            "llm_classified": llm_count,
            "category_distribution": {
                cat: stat.count for cat, stat in stats.items() if stat.count > 0
            },
            "top_priorities": [
                {
                    "category": p.category if isinstance(p.category, str) else p.category.value,
                    "score": round(p.score, 4),
                    "count": stats[p.category if isinstance(p.category, str) else p.category.value].count,
                    "fix_template": p.fix_template,
                    "effort": p.effort_level,
                }
                for p in priorities[:5]
            ],
        }

    def generate_html_report(self, output_path: Path) -> None:
        """Generate HTML dashboard report."""
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
        stats: dict[str, CategoryStats],
        priorities: list[PriorityScore],
        summary: dict[str, Any],
    ) -> str:
        """Build HTML content."""
        chart_data = [
            {"category": cat, "count": stat.count}
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
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        header h1 {{ font-size: 2em; margin-bottom: 10px; }}
        header p {{ opacity: 0.9; }}
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
        .stat-card .number {{ font-size: 2.5em; font-weight: bold; color: #667eea; }}
        .stat-card .label {{ color: #666; font-size: 0.9em; }}
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
        .chart-container {{ height: 300px; position: relative; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background: #f8f9fa; }}
        .effort-badge {{ padding: 4px 8px; border-radius: 4px; font-size: 0.85em; }}
        .effort-Low {{ background: #d1fae5; color: #059669; }}
        .effort-Medium {{ background: #fef3c7; color: #d97706; }}
        .effort-High {{ background: #fee2e2; color: #dc2626; }}
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
        .failure-header:hover {{ background: #f3f4f6; }}
        .failure-body {{
            padding: 15px;
            display: none;
            border-top: 1px solid #e5e7eb;
        }}
        .failure-body.active {{ display: block; }}
        .task-id {{ font-family: monospace; font-size: 0.9em; color: #6b7280; }}
        .root-cause-section {{
            margin: 15px 0;
            padding: 12px;
            border-radius: 6px;
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
        }}
        .fix-suggestions-section {{
            margin: 15px 0;
            padding: 12px;
            border-radius: 6px;
            background: #d1fae5;
            border-left: 4px solid #10b981;
        }}
        .error-spans-section {{
            margin: 15px 0;
            padding: 12px;
            border-radius: 6px;
            background: #fee2e2;
            border-left: 4px solid #ef4444;
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
        .suggestions-list {{ margin: 8px 0 0 20px; }}
        .suggestions-list li {{ margin: 4px 0; }}
        .error-list {{ margin: 8px 0 0 20px; }}
        .error-list li {{ margin: 6px 0; }}
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
        footer {{ text-align: center; padding: 20px; color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Agent Failure Analysis Report</h1>
            <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Powered by nat analyze</p>
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
                <div class="number">{len([p for p in priorities if p.score > 0])}</div>
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
            <p>nat analyze - Failure Analysis for NeMo Agent Toolkit</p>
        </footer>
    </div>

    <script>
        const ctx = document.getElementById('distributionChart').getContext('2d');
        const chartData = {json.dumps(chart_data)};

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
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ y: {{ beginAtZero: true }} }}
            }}
        }});

        document.querySelectorAll('.failure-header').forEach(header => {{
            header.addEventListener('click', () => {{
                header.nextElementSibling.classList.toggle('active');
            }});
        }});
    </script>
</body>
</html>"""
        return html

    def _build_priority_rows(
        self, priorities: list[PriorityScore], stats: dict[str, CategoryStats]
    ) -> str:
        """Build HTML rows for priority table."""
        rows = []
        for i, p in enumerate(priorities, 1):
            cat_key = p.category if isinstance(p.category, str) else p.category.value
            effort_class = f"effort-{p.effort_level}"
            rows.append(f"""
                <tr>
                    <td>{i}</td>
                    <td><strong>{cat_key}</strong></td>
                    <td>{stats.get(cat_key, CategoryStats(category=cat_key, count=0, percentage=0)).count}</td>
                    <td>{p.score:.4f}</td>
                    <td><span class="effort-badge {effort_class}">{p.effort_level}</span></td>
                    <td><div class="fix-template">{p.fix_template}</div></td>
                </tr>
            """)
        return "".join(rows)

    def _build_failure_details(self) -> str:
        """Build HTML for failure detail cards."""
        details = []
        for packet in self.packets[:20]:
            category = self._get_category_value(packet.failure_category)

            root_cause_html = ""
            if packet.root_cause_evidence:
                root_cause_html = f"""
                    <div class="root-cause-section">
                        <p><strong>Root Cause:</strong></p>
                        <div class="evidence-box">{self._escape_html(packet.root_cause_evidence)}</div>
                    </div>
                """

            fix_suggestions_html = ""
            if packet.fix_suggestions:
                suggestions = "".join(
                    f"<li>{self._escape_html(s)}</li>" for s in packet.fix_suggestions
                )
                fix_suggestions_html = f"""
                    <div class="fix-suggestions-section">
                        <p><strong>Fix Suggestions:</strong></p>
                        <ul class="suggestions-list">{suggestions}</ul>
                    </div>
                """

            error_spans_html = ""
            error_spans = [s for s in packet.spans if s.status == "ERROR" and s.error_message]
            if error_spans:
                error_items = []
                for span in error_spans[:3]:
                    error_items.append(
                        f"<li><strong>{span.tool_name or span.name}:</strong> "
                        f"<code>{self._escape_html(span.error_message[:200])}</code></li>"
                    )
                error_spans_html = f"""
                    <div class="error-spans-section">
                        <p><strong>Tool Errors:</strong></p>
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
                        <span>+</span>
                    </div>
                    <div class="failure-body">
                        <p><strong>Question:</strong> {self._escape_html(packet.user_request[:300])}...</p>
                        <p><strong>Expected:</strong> {self._escape_html(packet.expected_output)}</p>
                        <p><strong>Actual:</strong> {self._escape_html(packet.actual_output)}</p>
                        {root_cause_html}
                        {error_spans_html}
                        {fix_suggestions_html}
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
