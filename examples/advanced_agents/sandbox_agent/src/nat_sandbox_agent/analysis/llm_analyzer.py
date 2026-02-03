# SPDX-FileCopyrightText: Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLM-Native Failure Analyzers: Plan A (3-Stage) and Plan B (2-Stage Adaptive)."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from nat_sandbox_agent.analysis.models import FailurePacket, SpanSummary

logger = logging.getLogger(__name__)


class RootCauseCategory(str, Enum):
    """Root cause categories for LLM-native analysis.

    Simplified taxonomy based on analysis of 98 failure cases:
    - evidence_extraction: 38.8% - Found right source but extracted wrong info
    - reasoning_error: 28.6% - Logical, mathematical, or analytical errors
    - output_format: 12.2% - Answer correct but format wrong
    - iteration_limit: 8.2% - Hit max steps or gave up too soon
    - evidence_utilization: 4.1% - Couldn't access data or abandoned task
    - task_understanding: 3.1% - Misunderstood task requirements
    - api_error: 4.0% - API content filter or token limit errors
    - tool_limitation: 2.1% - Missing dependency or unsupported capability
    """

    # Core categories (95%+ of cases)
    EVIDENCE_EXTRACTION = "evidence_extraction"  # 38.8%
    REASONING_ERROR = "reasoning_error"  # 28.6%
    OUTPUT_FORMAT = "output_format"  # 12.2%
    ITERATION_LIMIT = "iteration_limit"  # 8.2%
    EVIDENCE_UTILIZATION = "evidence_utilization"  # 4.1%
    TASK_UNDERSTANDING = "task_understanding"  # 3.1%
    API_ERROR = "api_error"  # 4.0% - merged api_content_filter + api_token_limit
    TOOL_LIMITATION = "tool_limitation"  # 2.1% - merged missing_dependency + tool_limitation

    # New suggested categories
    PARTIAL_ANSWER = "partial_answer"  # Partially correct but incomplete
    DATA_UNAVAILABLE = "data_unavailable"  # Data source unavailable (site changed, auth required)

    # Fallback category
    OTHER_NEEDS_REVIEW = "other_needs_review"  # Doesn't fit above, requires human review


# Legacy category mapping for backwards compatibility
LEGACY_CATEGORY_MAP = {
    "constraint_violation": RootCauseCategory.TASK_UNDERSTANDING,
    "search_strategy": RootCauseCategory.EVIDENCE_EXTRACTION,
    "calculation_error": RootCauseCategory.REASONING_ERROR,
    "state_tracking": RootCauseCategory.REASONING_ERROR,
    "code_quality": RootCauseCategory.REASONING_ERROR,
    "dependency_missing": RootCauseCategory.TOOL_LIMITATION,
    "unrecovered_error": RootCauseCategory.API_ERROR,
    "planning_error": RootCauseCategory.REASONING_ERROR,
    "early_termination": RootCauseCategory.ITERATION_LIMIT,
    "verification_failure": RootCauseCategory.REASONING_ERROR,
    "other": RootCauseCategory.OTHER_NEEDS_REVIEW,
}


@dataclass
class AnalysisResult:
    """Result from failure analysis."""

    task_id: str
    category: str
    confidence: float
    explanation: str
    turning_point: str = ""
    fix_suggestions: list[str] = field(default_factory=list)
    key_evidence: list[str] = field(default_factory=list)

    # Metadata
    stages_used: int = 1
    total_time_ms: float = 0
    api_calls: int = 0

    # Optional detailed info
    narrative: str = ""
    error_recovery: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "category": self.category,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "turning_point": self.turning_point,
            "fix_suggestions": self.fix_suggestions,
            "key_evidence": self.key_evidence,
            "stages_used": self.stages_used,
            "total_time_ms": self.total_time_ms,
            "api_calls": self.api_calls,
            "narrative": self.narrative,
            "error_recovery": self.error_recovery,
        }


def format_spans_compact(spans: list[SpanSummary]) -> str:
    """Format spans in compact form for LLM consumption."""
    formatted = []
    for i, span in enumerate(spans):
        if span.span_type == "llm":
            output = span.output_summary or ""
            formatted.append(f"{i+1}. [LLM] {span.name}: {output[:300]}")
        elif span.span_type == "tool":
            status = "ERROR" if span.status == "ERROR" else "OK"
            args_str = json.dumps(span.tool_args)[:100] if span.tool_args else ""
            result = span.error_message or span.tool_result_summary or ""
            formatted.append(
                f"{i+1}. [{status}] {span.tool_name}({args_str}): {result[:200]}"
            )
    return "\n".join(formatted)


def format_spans_detailed(spans: list[SpanSummary]) -> str:
    """Format spans with full details."""
    formatted = []
    for i, span in enumerate(spans):
        entry = {
            "step": i + 1,
            "type": span.span_type,
            "name": span.name,
            "status": span.status,
        }
        if span.span_type == "llm":
            entry["output"] = span.output_summary
            entry["tokens"] = {"prompt": span.prompt_tokens, "completion": span.completion_tokens}
        elif span.span_type == "tool":
            entry["tool"] = span.tool_name
            entry["args"] = span.tool_args
            entry["result"] = span.tool_result_summary
            if span.error_message:
                entry["error"] = span.error_message
        formatted.append(entry)
    return json.dumps(formatted, indent=2, ensure_ascii=False)


# =============================================================================
# Plan A: 3-Stage Analyzer
# =============================================================================

STAGE1_NARRATIVE_PROMPT = """You are analyzing an AI agent's execution trace. Convert this into a clear narrative.

## Task
Question: {question}
Expected Answer: {expected}
Actual Answer: {actual}

## Execution Trace
{spans}

## Instructions
Write a clear narrative (3-5 paragraphs) describing:
1. What the agent was trying to accomplish
2. What steps it took (tools used, results obtained)
3. How it arrived at its final answer
4. Any errors encountered and how the agent responded to them

Focus on the REASONING and DECISION-MAKING process, not just listing tool calls.
Be specific about what information was obtained and how it was used."""


STAGE2_TURNING_POINT_PROMPT = """You are a failure analysis expert. Identify the CRITICAL TURNING POINT.

## Execution Narrative
{narrative}

## Task
Question: {question}
Expected: {expected}
Actual: {actual}

## Instructions
Identify the SINGLE MOST CRITICAL moment where things went wrong.

Respond in JSON format:
{{
  "turning_point": "Describe the exact moment/decision that led to failure",
  "what_should_have_happened": "What the agent should have done instead",
  "error_recovery": {{
    "encountered_errors": true/false,
    "recovered": true/false,
    "errors_caused_failure": true/false
  }}
}}"""


STAGE3_ROOT_CAUSE_PROMPT = """You are analyzing an AI agent failure. Determine the ROOT CAUSE.

## Turning Point Analysis
{turning_point_analysis}

## Original Task
Question: {question}
Expected: {expected}
Actual: {actual}

## Categories (choose the MOST SPECIFIC one):
- evidence_extraction: Found right source but extracted wrong info (wrong table cell, misread data, parsing error)
- reasoning_error: Flawed logical reasoning, mathematical computation mistake, or analytical error
- output_format: Understood correctly but output in wrong format (commas, units, case, delimiter)
- iteration_limit: Gave up too soon, hit max steps, or ran out of iterations
- evidence_utilization: Had access to correct info but didn't use it properly or abandoned the task
- task_understanding: Misunderstood what the question was asking or ignored constraints
- api_error: API content filter blocked request, token limit exceeded, or rate limited
- tool_limitation: Task required unsupported capability (PDF audio, missing package/dependency)
- partial_answer: Answer is partially correct but incomplete
- data_unavailable: Data source is unavailable (website changed, requires authentication, blocked)
- other_needs_review: Doesn't fit above categories, requires human review

Respond in JSON:
{{
  "category": "category_name",
  "confidence": 0.0-1.0,
  "explanation": "Why this category (not others)",
  "fix_suggestions": ["suggestion1", "suggestion2"],
  "key_evidence": ["evidence1", "evidence2"]
}}"""


class ThreeStageAnalyzer:
    """Plan A: 3-Stage Analyzer (Narrative -> Turning Point -> Root Cause)"""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.client = AsyncOpenAI()

    async def analyze(self, packet: FailurePacket) -> AnalysisResult:
        """Run 3-stage analysis."""
        start_time = time.time()
        api_calls = 0

        spans_text = format_spans_compact(packet.spans)

        # Stage 1: Narrative
        narrative = await self._call_llm(
            STAGE1_NARRATIVE_PROMPT.format(
                question=packet.user_request,
                expected=packet.expected_output,
                actual=packet.actual_output,
                spans=spans_text
            ),
            max_tokens=1000
        )
        api_calls += 1

        # Stage 2: Turning Point
        turning_point_response = await self._call_llm(
            STAGE2_TURNING_POINT_PROMPT.format(
                narrative=narrative,
                question=packet.user_request,
                expected=packet.expected_output,
                actual=packet.actual_output
            ),
            max_tokens=500,
            json_mode=True
        )
        api_calls += 1

        try:
            turning_point_data = json.loads(turning_point_response)
        except json.JSONDecodeError:
            turning_point_data = {
                "turning_point": turning_point_response[:500],
                "what_should_have_happened": "",
                "error_recovery": {}
            }

        # Stage 3: Root Cause
        root_cause_response = await self._call_llm(
            STAGE3_ROOT_CAUSE_PROMPT.format(
                turning_point_analysis=json.dumps(turning_point_data, indent=2),
                question=packet.user_request,
                expected=packet.expected_output,
                actual=packet.actual_output
            ),
            max_tokens=600,
            json_mode=True
        )
        api_calls += 1

        try:
            root_cause_data = json.loads(root_cause_response)
        except json.JSONDecodeError:
            root_cause_data = {
                "category": "other",
                "confidence": 0.5,
                "explanation": root_cause_response[:500],
                "fix_suggestions": [],
                "key_evidence": []
            }

        total_time = (time.time() - start_time) * 1000

        return AnalysisResult(
            task_id=packet.task_id,
            category=root_cause_data.get("category", "other"),
            confidence=root_cause_data.get("confidence", 0.5),
            explanation=root_cause_data.get("explanation", ""),
            turning_point=turning_point_data.get("turning_point", ""),
            fix_suggestions=root_cause_data.get("fix_suggestions", []),
            key_evidence=root_cause_data.get("key_evidence", []),
            stages_used=3,
            total_time_ms=total_time,
            api_calls=api_calls,
            narrative=narrative,
            error_recovery=turning_point_data.get("error_recovery", {})
        )

    async def _call_llm(
        self, prompt: str, max_tokens: int = 500, json_mode: bool = False
    ) -> str:
        """Make LLM API call."""
        kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content


# =============================================================================
# Plan B: 2-Stage Adaptive Analyzer
# =============================================================================

QUICK_SCAN_PROMPT = """Analyze this AI agent failure case.

## Task
Question: {question}
Expected: {expected}
Actual: {actual}

## Execution Trace
{spans}

## Instructions
Analyze and respond with JSON:

{{
  "execution_summary": "Brief summary of what the agent did (2-3 sentences)",

  "turning_point": "The critical moment where the agent's approach led to wrong answer",

  "error_recovery": {{
    "encountered_errors": true/false,
    "recovered": true/false,
    "errors_caused_failure": true/false
  }},

  "category": "One of: evidence_extraction, reasoning_error, output_format, iteration_limit, evidence_utilization, task_understanding, api_error, tool_limitation, partial_answer, data_unavailable, other_needs_review",

  "confidence": 0.0-1.0,

  "needs_deep_dive": true if confidence < 0.7 or case is complex,

  "fix_suggestion": "One actionable fix (1 sentence)",

  "key_evidence": ["evidence1", "evidence2"]
}}"""


DEEP_DIVE_PROMPT = """The quick analysis was uncertain. Perform deeper analysis.

## Quick Analysis Result
{quick_analysis}

## Full Execution Trace
{spans}

## Original Task
Question: {question}
Expected: {expected}
Actual: {actual}

## Instructions
Respond with JSON:

{{
  "alternative_causes": [
    {{"cause": "cause1", "evidence_for": "...", "evidence_against": "..."}},
    {{"cause": "cause2", "evidence_for": "...", "evidence_against": "..."}}
  ],

  "final_category": "category after deeper analysis",

  "confidence": 0.0-1.0,

  "explanation": "Why this category after considering alternatives",

  "fix_suggestions": ["fix1", "fix2"],

  "key_evidence": ["evidence1", "evidence2"]
}}"""


class TwoStageAdaptiveAnalyzer:
    """Plan B: 2-Stage Adaptive Analyzer (Quick Scan -> Deep Dive if needed)"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        deep_dive_model: str = "gpt-4o",
        confidence_threshold: float = 0.7
    ):
        self.model = model
        self.deep_dive_model = deep_dive_model
        self.confidence_threshold = confidence_threshold
        self.client = AsyncOpenAI()

    async def analyze(self, packet: FailurePacket) -> AnalysisResult:
        """Run adaptive 2-stage analysis."""
        start_time = time.time()
        api_calls = 0
        stages_used = 1

        spans_compact = format_spans_compact(packet.spans)

        # Stage 1: Quick Scan (always)
        quick_response = await self._call_llm(
            QUICK_SCAN_PROMPT.format(
                question=packet.user_request,
                expected=packet.expected_output,
                actual=packet.actual_output,
                spans=spans_compact
            ),
            model=self.model,
            max_tokens=800,
            json_mode=True
        )
        api_calls += 1

        try:
            quick_data = json.loads(quick_response)
        except json.JSONDecodeError:
            quick_data = {
                "category": "other",
                "confidence": 0.5,
                "needs_deep_dive": True,
                "turning_point": "",
                "fix_suggestion": "",
                "key_evidence": [],
                "error_recovery": {},
                "execution_summary": ""
            }

        confidence = quick_data.get("confidence", 0.5)
        needs_deep_dive = quick_data.get("needs_deep_dive", False)

        # Stage 2: Deep Dive (only if needed)
        if needs_deep_dive or confidence < self.confidence_threshold:
            stages_used = 2
            spans_detailed = format_spans_detailed(packet.spans)

            deep_response = await self._call_llm(
                DEEP_DIVE_PROMPT.format(
                    quick_analysis=json.dumps(quick_data, indent=2),
                    spans=spans_detailed,
                    question=packet.user_request,
                    expected=packet.expected_output,
                    actual=packet.actual_output
                ),
                model=self.deep_dive_model,
                max_tokens=1000,
                json_mode=True
            )
            api_calls += 1

            try:
                deep_data = json.loads(deep_response)
            except json.JSONDecodeError:
                deep_data = {}

            # Merge results
            category = deep_data.get("final_category", quick_data.get("category", "other"))
            confidence = deep_data.get("confidence", confidence)
            explanation = deep_data.get("explanation", quick_data.get("execution_summary", ""))
            fix_suggestions = deep_data.get("fix_suggestions", [quick_data.get("fix_suggestion", "")])
            key_evidence = deep_data.get("key_evidence", quick_data.get("key_evidence", []))
        else:
            category = quick_data.get("category", "other")
            explanation = quick_data.get("execution_summary", "")
            fix_suggestions = [quick_data.get("fix_suggestion", "")] if quick_data.get("fix_suggestion") else []
            key_evidence = quick_data.get("key_evidence", [])

        total_time = (time.time() - start_time) * 1000

        return AnalysisResult(
            task_id=packet.task_id,
            category=category,
            confidence=confidence,
            explanation=explanation,
            turning_point=quick_data.get("turning_point", ""),
            fix_suggestions=fix_suggestions,
            key_evidence=key_evidence,
            stages_used=stages_used,
            total_time_ms=total_time,
            api_calls=api_calls,
            narrative=quick_data.get("execution_summary", ""),
            error_recovery=quick_data.get("error_recovery", {})
        )

    async def _call_llm(
        self, prompt: str, model: str, max_tokens: int = 500, json_mode: bool = False
    ) -> str:
        """Make LLM API call."""
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content


# =============================================================================
# Comparison Runner
# =============================================================================

async def run_comparison(
    packets: list[FailurePacket],
    output_dir: Path,
    concurrency: int = 3
) -> dict:
    """Run both analyzers and compare results."""

    plan_a = ThreeStageAnalyzer(model="gpt-4o-mini")
    plan_b = TwoStageAdaptiveAnalyzer(
        model="gpt-4o-mini",
        deep_dive_model="gpt-4o",
        confidence_threshold=0.7
    )

    semaphore = asyncio.Semaphore(concurrency)

    async def run_with_semaphore(analyzer, packet, name):
        async with semaphore:
            try:
                logger.info(f"[{name}] Analyzing {packet.task_id[:8]}...")
                result = await analyzer.analyze(packet)
                logger.info(f"[{name}] {packet.task_id[:8]} -> {result.category} ({result.confidence:.2f})")
                return result
            except Exception as e:
                logger.error(f"[{name}] Error analyzing {packet.task_id[:8]}: {e}")
                return AnalysisResult(
                    task_id=packet.task_id,
                    category="error",
                    confidence=0.0,
                    explanation=str(e),
                    stages_used=0,
                    total_time_ms=0,
                    api_calls=0
                )

    # Run Plan A
    logger.info("=" * 60)
    logger.info("Running Plan A (3-Stage)...")
    logger.info("=" * 60)
    start_a = time.time()
    results_a = await asyncio.gather(
        *[run_with_semaphore(plan_a, p, "Plan A") for p in packets]
    )
    time_a = time.time() - start_a

    # Run Plan B
    logger.info("=" * 60)
    logger.info("Running Plan B (2-Stage Adaptive)...")
    logger.info("=" * 60)
    start_b = time.time()
    results_b = await asyncio.gather(
        *[run_with_semaphore(plan_b, p, "Plan B") for p in packets]
    )
    time_b = time.time() - start_b

    # Save results
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "plan_a_results.json", "w") as f:
        json.dump([r.to_dict() for r in results_a], f, indent=2, ensure_ascii=False)

    with open(output_dir / "plan_b_results.json", "w") as f:
        json.dump([r.to_dict() for r in results_b], f, indent=2, ensure_ascii=False)

    # Calculate statistics
    stats_a = {
        "total_time_s": time_a,
        "avg_time_ms": sum(r.total_time_ms for r in results_a) / len(results_a),
        "total_api_calls": sum(r.api_calls for r in results_a),
        "avg_confidence": sum(r.confidence for r in results_a) / len(results_a),
        "category_distribution": {},
    }
    for r in results_a:
        stats_a["category_distribution"][r.category] = stats_a["category_distribution"].get(r.category, 0) + 1

    stats_b = {
        "total_time_s": time_b,
        "avg_time_ms": sum(r.total_time_ms for r in results_b) / len(results_b),
        "total_api_calls": sum(r.api_calls for r in results_b),
        "avg_confidence": sum(r.confidence for r in results_b) / len(results_b),
        "stages_distribution": {1: 0, 2: 0},
        "category_distribution": {},
    }
    for r in results_b:
        stats_b["stages_distribution"][r.stages_used] = stats_b["stages_distribution"].get(r.stages_used, 0) + 1
        stats_b["category_distribution"][r.category] = stats_b["category_distribution"].get(r.category, 0) + 1

    comparison = {
        "total_cases": len(packets),
        "plan_a": stats_a,
        "plan_b": stats_b,
        "comparison": {
            "time_ratio": time_a / time_b if time_b > 0 else 0,
            "api_calls_ratio": stats_a["total_api_calls"] / stats_b["total_api_calls"] if stats_b["total_api_calls"] > 0 else 0,
        }
    }

    with open(output_dir / "comparison_stats.json", "w") as f:
        json.dump(comparison, f, indent=2)

    # Print summary
    print("\n" + "=" * 70)
    print("COMPARISON RESULTS")
    print("=" * 70)
    print(f"\nTotal cases analyzed: {len(packets)}")
    print(f"\n{'Metric':<30} {'Plan A (3-Stage)':<20} {'Plan B (2-Stage)':<20}")
    print("-" * 70)
    print(f"{'Total time (s)':<30} {time_a:<20.2f} {time_b:<20.2f}")
    print(f"{'Avg time per case (ms)':<30} {stats_a['avg_time_ms']:<20.0f} {stats_b['avg_time_ms']:<20.0f}")
    print(f"{'Total API calls':<30} {stats_a['total_api_calls']:<20} {stats_b['total_api_calls']:<20}")
    print(f"{'Avg confidence':<30} {stats_a['avg_confidence']:<20.2f} {stats_b['avg_confidence']:<20.2f}")

    if stats_b["stages_distribution"]:
        print(f"\nPlan B stages used: {stats_b['stages_distribution']}")

    print("\nCategory Distribution:")
    print(f"{'Category':<25} {'Plan A':<10} {'Plan B':<10}")
    print("-" * 45)
    all_cats = set(stats_a["category_distribution"].keys()) | set(stats_b["category_distribution"].keys())
    for cat in sorted(all_cats):
        a_count = stats_a["category_distribution"].get(cat, 0)
        b_count = stats_b["category_distribution"].get(cat, 0)
        print(f"{cat:<25} {a_count:<10} {b_count:<10}")

    print("=" * 70)

    return comparison


async def main():
    """Main entry point for comparison."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Compare Plan A and Plan B analyzers")
    parser.add_argument(
        "--packets", "-p",
        required=True,
        help="Path to failure_packets.jsonl"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output directory for results"
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=3,
        help="Number of concurrent API calls"
    )

    args = parser.parse_args()

    # Load packets
    from nat_sandbox_agent.analysis.workflow_exporter import WorkflowExporter
    exporter = WorkflowExporter()
    packets = exporter.load_packets(Path(args.packets))

    # Run comparison
    await run_comparison(packets, Path(args.output), args.concurrency)


if __name__ == "__main__":
    asyncio.run(main())
