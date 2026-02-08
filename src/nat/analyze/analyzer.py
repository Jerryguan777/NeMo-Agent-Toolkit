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

"""LLM-based failure analyzer - two-stage pipeline (per-task analysis + fingerprint clustering)."""

import asyncio
import json
import logging

from nat.analyze.exporter import build_compressed_trajectory
from nat.analyze.models import (
    AnalysisReport,
    FingerprintGroup,
    StepSummary,
    TaskAnalysis,
)

logger = logging.getLogger(__name__)

TASK_ANALYSIS_SYSTEM_PROMPT = """\
You are an expert at analyzing AI agent execution traces to diagnose why a task failed.

You will be given:
1. The task question
2. The expected answer
3. The actual (incorrect) answer
4. The full execution trajectory (sequence of LLM calls, tool calls, retriever calls)

Your job is to:
1. Summarize each step in 1-2 sentences
2. Identify which step(s) are the root cause of the failure
3. Generate a short fingerprint phrase describing the core failure mode
4. Explain the root cause in 2-4 sentences
5. Suggest improvements

Respond with a JSON object (no markdown fences):
{
  "step_summaries": [
    {"step_index": 0, "summary": "...", "is_root_cause": false},
    ...
  ],
  "fingerprint": "short natural language phrase describing the failure mode",
  "root_cause": "2-4 sentence explanation of why the agent failed",
  "root_cause_step_indices": [3, 5],
  "improvement_suggestions": ["suggestion 1", "suggestion 2"],
  "confidence": 0.85
}

Guidelines for fingerprint:
- Use a concise, descriptive English phrase (5-15 words)
- Focus on the agent's behavioral mistake, not the symptom
- Examples: "Agent used too vague a search query", "Arithmetic error in final calculation", \
"Stopped searching after first irrelevant result", "Misunderstood multi-part question structure"
"""

CLUSTERING_SYSTEM_PROMPT = """\
You are an expert at categorizing failure modes. You will receive a list of failure fingerprints \
from multiple failed AI agent tasks. Your job is to cluster similar fingerprints into groups.

Rules:
- Merge fingerprints that describe essentially the same failure mode
- Keep distinct failure modes separate
- Each group needs a clear, concise group_name
- Every task_id must appear in exactly one group

Respond with a JSON object (no markdown fences):
{
  "groups": [
    {
      "group_name": "descriptive category name",
      "description": "1-2 sentence description of this failure pattern",
      "task_ids": ["id1", "id2"]
    }
  ]
}
"""


def _dedup_suggestions(tasks: list[TaskAnalysis], limit: int = 5) -> list[str]:
    """Collect and deduplicate improvement suggestions from tasks, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for t in tasks:
        for s in t.improvement_suggestions:
            if s not in seen:
                seen.add(s)
                result.append(s)
    return result[:limit]


class FailureAnalyzer:
    """Two-stage LLM failure analysis engine.

    Stage 1: Per-task analysis (concurrent) - analyzes each failed task independently
    Stage 2: Fingerprint clustering - groups similar failures across all tasks
    """

    def __init__(
        self,
        model: str = "gpt-5.2",
        api_key: str | None = None,
        base_url: str | None = None,
        concurrency: int = 5,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.concurrency = concurrency
        self._async_client = None
        self._fingerprint_groups: list[FingerprintGroup] = []

    def _get_async_client(self):
        """Lazy-load async OpenAI client."""
        if self._async_client is None:
            from openai import AsyncOpenAI

            kwargs = {}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._async_client = AsyncOpenAI(**kwargs)
        return self._async_client

    async def analyze_all(self, analyses: list[TaskAnalysis]) -> None:
        """Run the full two-stage analysis pipeline.

        Mutates analyses in-place with LLM analysis results.

        Args:
            analyses: List of TaskAnalysis objects with step_details filled in.
        """
        if not analyses:
            return

        # Stage 1: Per-task analysis (concurrent)
        logger.info(f"Stage 1: Analyzing {len(analyses)} tasks (concurrency={self.concurrency})")
        semaphore = asyncio.Semaphore(self.concurrency)

        async def analyze_with_semaphore(task: TaskAnalysis) -> None:
            async with semaphore:
                await self._analyze_single_task(task)

        await asyncio.gather(*[analyze_with_semaphore(t) for t in analyses])

        analyzed = [t for t in analyses if t.fingerprint]
        logger.info(f"Stage 1 complete: {len(analyzed)}/{len(analyses)} tasks analyzed")

        # Stage 2: Fingerprint clustering
        if len(analyzed) > 1:
            logger.info("Stage 2: Clustering fingerprints")
            groups = await self._cluster_fingerprints(analyzed)
            # Assign group_name back to each task via dict lookup
            task_map = {t.task_id: t for t in analyzed}
            for group in groups:
                for task_id in group.task_ids:
                    if task_id in task_map:
                        task_map[task_id].group_name = group.group_name
        elif len(analyzed) == 1:
            analyzed[0].group_name = analyzed[0].fingerprint
            groups = [
                FingerprintGroup(
                    group_name=analyzed[0].fingerprint,
                    description=analyzed[0].root_cause,
                    count=1,
                    task_ids=[analyzed[0].task_id],
                    representative_root_cause=analyzed[0].root_cause,
                    common_suggestions=analyzed[0].improvement_suggestions,
                )
            ]
        else:
            groups = []

        self._fingerprint_groups = groups

    async def _analyze_single_task(self, task: TaskAnalysis) -> None:
        """Analyze a single task using one LLM call."""
        trajectory = build_compressed_trajectory(task.step_details)

        user_message = f"""## Task
**Question:** {task.question}

**Expected Answer:** {task.expected_answer}

**Actual Answer:** {task.actual_answer}

## Execution Trajectory ({len(task.step_details)} steps)
{trajectory}
"""

        client = self._get_async_client()
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": TASK_ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_completion_tokens=4096,
            )

            msg = response.choices[0].message
            finish = response.choices[0].finish_reason
            content = (msg.content or "").strip()
            if not content or finish == "length":
                logger.warning(
                    f"  Truncated/empty response for task {task.task_id} "
                    f"(finish_reason={finish}, content_len={len(content)})"
                )
                if not content:
                    task.fingerprint = "response_truncated"
                    task.root_cause = "LLM response was truncated (output too long or input too large)"
                    task.confidence = 0.0
                    return
            self._parse_task_analysis(task, content)
            logger.info(f"  Analyzed task {task.task_id}: fingerprint='{task.fingerprint}'")

        except Exception as e:
            logger.error(f"  Failed to analyze task {task.task_id}: {e}")
            task.fingerprint = "analysis_failed"
            task.root_cause = f"LLM analysis failed: {e}"
            task.confidence = 0.0

    def _parse_task_analysis(self, task: TaskAnalysis, content: str) -> None:
        """Parse LLM response and fill TaskAnalysis fields."""
        try:
            # Strip markdown code fences if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content)

            # Step summaries
            for s in data.get("step_summaries", []):
                task.step_summaries.append(
                    StepSummary(
                        step_index=s["step_index"],
                        event_type=next(
                            (d.event_type for d in task.step_details if d.step_index == s["step_index"]),
                            "unknown",
                        ),
                        name=next(
                            (d.name for d in task.step_details if d.step_index == s["step_index"]),
                            "unknown",
                        ),
                        summary=s["summary"],
                        is_root_cause=s.get("is_root_cause", False),
                    )
                )

            task.fingerprint = data.get("fingerprint", "unknown")
            task.root_cause = data.get("root_cause", "")
            task.root_cause_step_indices = data.get("root_cause_step_indices", [])
            task.improvement_suggestions = data.get("improvement_suggestions", [])
            task.confidence = float(data.get("confidence", 0.5))

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response for task {task.task_id}: {e}")
            task.fingerprint = "parse_error"
            task.root_cause = f"Failed to parse LLM response: {content[:200]}"
            task.confidence = 0.0

    async def _cluster_fingerprints(self, analyses: list[TaskAnalysis]) -> list[FingerprintGroup]:
        """Cluster fingerprints from all tasks into groups using one LLM call."""
        fingerprint_list = [
            {"task_id": t.task_id, "fingerprint": t.fingerprint}
            for t in analyses
        ]

        user_message = f"""Cluster these failure fingerprints into groups:

{json.dumps(fingerprint_list, indent=2, ensure_ascii=False)}
"""

        client = self._get_async_client()
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CLUSTERING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_completion_tokens=4096,
            )

            content = response.choices[0].message.content.strip()
            return self._parse_clustering_response(content, analyses)

        except Exception as e:
            logger.error(f"Fingerprint clustering failed: {e}")
            return self._fallback_clustering(analyses)

    def _parse_clustering_response(
        self, content: str, analyses: list[TaskAnalysis]
    ) -> list[FingerprintGroup]:
        """Parse clustering LLM response into FingerprintGroup objects."""
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content)

            # Build task lookup
            task_map = {t.task_id: t for t in analyses}

            groups = []
            for g in data.get("groups", []):
                task_ids = g.get("task_ids", [])
                tasks_in_group = [task_map[tid] for tid in task_ids if tid in task_map]

                rep_task = max(tasks_in_group, key=lambda t: t.confidence) if tasks_in_group else None

                groups.append(
                    FingerprintGroup(
                        group_name=g["group_name"],
                        description=g.get("description", ""),
                        count=len(task_ids),
                        task_ids=task_ids,
                        representative_root_cause=rep_task.root_cause if rep_task else "",
                        common_suggestions=_dedup_suggestions(tasks_in_group),
                    )
                )

            return groups

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse clustering response: {e}")
            return self._fallback_clustering(analyses)

    def _fallback_clustering(self, analyses: list[TaskAnalysis]) -> list[FingerprintGroup]:
        """Fallback: each unique fingerprint becomes its own group."""
        groups_map: dict[str, list[TaskAnalysis]] = {}
        for t in analyses:
            groups_map.setdefault(t.fingerprint, []).append(t)

        groups = []
        for fingerprint, tasks in groups_map.items():
            rep = max(tasks, key=lambda t: t.confidence)
            groups.append(
                FingerprintGroup(
                    group_name=fingerprint,
                    description=rep.root_cause,
                    count=len(tasks),
                    task_ids=[t.task_id for t in tasks],
                    representative_root_cause=rep.root_cause,
                    common_suggestions=_dedup_suggestions(tasks),
                )
            )
        return groups

    def build_report(
        self,
        analyses: list[TaskAnalysis],
        total_tasks: int,
    ) -> AnalysisReport:
        """Build the final AnalysisReport after analysis is complete."""
        from datetime import datetime

        return AnalysisReport(
            total_tasks=total_tasks,
            total_failures=len(analyses),
            task_analyses=analyses,
            fingerprint_groups=self._fingerprint_groups,
            model_used=self.model,
            analysis_timestamp=datetime.now().isoformat(),
        )
