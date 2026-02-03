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

"""Hybrid Failure Analyzer: Combines fast classification with deep analysis.

This analyzer implements a 2-stage conditional architecture:
- Stage 1: Fast classification with gpt-4o-mini (predefined categories + confidence)
- Stage 2: Deep analysis with gpt-4o (triggered when confidence < 0.8 or category is "other")

Based on analysis showing Plan A (3-stage) achieves better precision (29.7% vs 9.0%)
while Plan B (2-stage adaptive) achieves better Level 3 recall (47.4% vs 26.3%).
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from nat_sandbox_agent.analysis.llm_analyzer import (
    AnalysisResult,
    RootCauseCategory,
    format_spans_compact,
    format_spans_detailed,
)
from nat_sandbox_agent.analysis.models import FailurePacket

logger = logging.getLogger(__name__)


# Category descriptions for quick classification
CATEGORY_DESCRIPTIONS = {
    RootCauseCategory.EVIDENCE_EXTRACTION: "Found the right source but extracted wrong information (wrong cell, misread data, parsing error)",
    RootCauseCategory.REASONING_ERROR: "Flawed logical reasoning, mathematical computation mistake, or analytical error",
    RootCauseCategory.OUTPUT_FORMAT: "Answer is correct but format is wrong (commas, units, case, delimiter)",
    RootCauseCategory.ITERATION_LIMIT: "Gave up too soon, hit max steps, or ran out of iterations before completing",
    RootCauseCategory.EVIDENCE_UTILIZATION: "Had access to correct information but didn't use it properly or abandoned task",
    RootCauseCategory.TASK_UNDERSTANDING: "Misunderstood what the question was asking or ignored explicit constraints",
    RootCauseCategory.API_ERROR: "API content filter blocked request, token limit exceeded, or rate limited",
    RootCauseCategory.TOOL_LIMITATION: "Task required unsupported capability (PDF audio, missing package/dependency)",
    RootCauseCategory.PARTIAL_ANSWER: "Answer is partially correct but incomplete",
    RootCauseCategory.DATA_UNAVAILABLE: "Data source is unavailable (website changed, requires authentication, blocked)",
    RootCauseCategory.OTHER_NEEDS_REVIEW: "Doesn't fit above categories, requires human review",
}


STAGE1_QUICK_CLASSIFY_PROMPT = """You are a failure classification expert. Quickly classify this AI agent failure.

## Task
Question: {question}
Expected Answer: {expected}
Actual Answer: {actual}

## Execution Summary
{spans}

## Categories (with frequency in real data):
- evidence_extraction (38.8%): {desc_evidence_extraction}
- reasoning_error (28.6%): {desc_reasoning_error}
- output_format (12.2%): {desc_output_format}
- iteration_limit (8.2%): {desc_iteration_limit}
- evidence_utilization (4.1%): {desc_evidence_utilization}
- task_understanding (3.1%): {desc_task_understanding}
- api_error (4.0%): {desc_api_error}
- tool_limitation (2.1%): {desc_tool_limitation}
- partial_answer: {desc_partial_answer}
- data_unavailable: {desc_data_unavailable}
- other_needs_review: {desc_other_needs_review}

## Instructions
Classify into exactly ONE category. Be specific:
- If the agent found the right data source but extracted wrong value → evidence_extraction
- If the agent made a calculation/logic error → reasoning_error
- If the answer is correct but formatted wrong (e.g., "100,000" vs "100000") → output_format
- If the agent ran out of steps or gave up → iteration_limit

Respond in JSON:
{{
  "category": "category_name",
  "confidence": 0.0-1.0,
  "brief_reason": "One sentence explaining why this category",
  "key_indicator": "The specific evidence that led to this classification"
}}"""


STAGE2_DEEP_ANALYSIS_PROMPT = """The quick classification was uncertain. Perform deeper analysis.

## Quick Classification Result
Category: {quick_category}
Confidence: {quick_confidence}
Reason: {quick_reason}

## Task Details
Question: {question}
Expected Answer: {expected}
Actual Answer: {actual}

## Full Execution Trace
{spans}

## Instructions
Perform thorough analysis following this structure:

1. **Narrative**: Describe what the agent tried to do step by step
2. **Turning Point**: Identify the exact moment/decision where things went wrong
3. **Root Cause**: Determine the fundamental cause of failure
4. **Alternative Causes**: Consider other possible explanations

Categories:
- evidence_extraction: {desc_evidence_extraction}
- reasoning_error: {desc_reasoning_error}
- output_format: {desc_output_format}
- iteration_limit: {desc_iteration_limit}
- evidence_utilization: {desc_evidence_utilization}
- task_understanding: {desc_task_understanding}
- api_error: {desc_api_error}
- tool_limitation: {desc_tool_limitation}
- partial_answer: {desc_partial_answer}
- data_unavailable: {desc_data_unavailable}
- other_needs_review: {desc_other_needs_review}

If none of these categories fit well, you may suggest a NEW category.

Respond in JSON:
{{
  "narrative": "Step-by-step description of agent's execution",
  "turning_point": "The critical moment where the agent's approach led to failure",
  "final_category": "The most accurate category",
  "confidence": 0.0-1.0,
  "explanation": "Detailed explanation of why this category",
  "alternative_causes": [
    {{"cause": "alternative cause 1", "evidence_for": "...", "evidence_against": "..."}}
  ],
  "suggested_new_category": null or {{"name": "new_category_name", "description": "...", "reason": "why existing categories don't fit"}},
  "fix_suggestions": ["suggestion1", "suggestion2"],
  "key_evidence": ["evidence1", "evidence2"]
}}"""


@dataclass
class NewCategorySuggestion:
    """A suggested new category that doesn't fit existing taxonomy."""

    task_id: str
    suggested_name: str
    description: str
    reason: str
    example_question: str
    example_expected: str
    example_actual: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class HybridAnalysisResult(AnalysisResult):
    """Extended result with hybrid-specific metadata."""

    # Stage information
    stage1_category: str = ""
    stage1_confidence: float = 0.0
    stage1_reason: str = ""
    deep_analysis_triggered: bool = False
    trigger_reason: str = ""

    # New category suggestion
    suggested_new_category: NewCategorySuggestion | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary including hybrid-specific fields."""
        base = super().to_dict()
        base.update({
            "stage1_category": self.stage1_category,
            "stage1_confidence": self.stage1_confidence,
            "stage1_reason": self.stage1_reason,
            "deep_analysis_triggered": self.deep_analysis_triggered,
            "trigger_reason": self.trigger_reason,
            "suggested_new_category": {
                "task_id": self.suggested_new_category.task_id,
                "suggested_name": self.suggested_new_category.suggested_name,
                "description": self.suggested_new_category.description,
                "reason": self.suggested_new_category.reason,
            } if self.suggested_new_category else None,
        })
        return base


class CategoryManager:
    """Manages category taxonomy and collects new category suggestions.

    This class handles:
    - Tracking predefined categories
    - Collecting suggestions for new categories
    - Persisting suggestions for human review
    """

    def __init__(self, suggestions_path: Path | None = None):
        """Initialize the category manager.

        Args:
            suggestions_path: Path to save new category suggestions.
        """
        self.suggestions_path = suggestions_path or Path("new_category_suggestions.jsonl")
        self.suggestions: list[NewCategorySuggestion] = []

    def add_suggestion(self, suggestion: NewCategorySuggestion) -> None:
        """Add a new category suggestion.

        Args:
            suggestion: The new category suggestion.
        """
        self.suggestions.append(suggestion)
        logger.info(f"New category suggested: {suggestion.suggested_name} for task {suggestion.task_id}")

    def save_suggestions(self) -> None:
        """Save all suggestions to file."""
        if not self.suggestions:
            return

        with open(self.suggestions_path, "a") as f:
            for suggestion in self.suggestions:
                f.write(json.dumps({
                    "task_id": suggestion.task_id,
                    "suggested_name": suggestion.suggested_name,
                    "description": suggestion.description,
                    "reason": suggestion.reason,
                    "example_question": suggestion.example_question,
                    "example_expected": suggestion.example_expected,
                    "example_actual": suggestion.example_actual,
                    "timestamp": suggestion.timestamp,
                }, ensure_ascii=False) + "\n")

        logger.info(f"Saved {len(self.suggestions)} suggestions to {self.suggestions_path}")

    def get_category_stats(self) -> dict[str, int]:
        """Get statistics on suggested categories.

        Returns:
            Dict mapping suggested category names to counts.
        """
        stats: dict[str, int] = {}
        for suggestion in self.suggestions:
            stats[suggestion.suggested_name] = stats.get(suggestion.suggested_name, 0) + 1
        return stats


class HybridFailureAnalyzer:
    """Hybrid failure analyzer combining fast classification with deep analysis.

    This analyzer implements the recommended hybrid architecture:
    - Stage 1: Quick classification using gpt-4o-mini (always runs)
    - Stage 2: Deep analysis using gpt-4o (conditional, triggered when uncertain)

    The hybrid approach achieves:
    - Fast classification for clear cases (saves cost and time)
    - Deep analysis for ambiguous cases (maintains accuracy)
    - Collection of new category suggestions (enables taxonomy evolution)
    """

    def __init__(
        self,
        quick_model: str = "gpt-4o-mini",
        deep_model: str = "gpt-4o",
        confidence_threshold: float = 0.8,
        category_manager: CategoryManager | None = None,
    ):
        """Initialize the hybrid analyzer.

        Args:
            quick_model: Model for Stage 1 quick classification.
            deep_model: Model for Stage 2 deep analysis.
            confidence_threshold: Confidence threshold for triggering Stage 2.
            category_manager: Manager for handling new category suggestions.
        """
        self.quick_model = quick_model
        self.deep_model = deep_model
        self.confidence_threshold = confidence_threshold
        self.category_manager = category_manager or CategoryManager()
        self.client = AsyncOpenAI()

    async def analyze(self, packet: FailurePacket) -> HybridAnalysisResult:
        """Analyze a failure case using hybrid approach.

        Args:
            packet: The failure packet to analyze.

        Returns:
            HybridAnalysisResult with classification and analysis.
        """
        start_time = time.time()
        api_calls = 0

        spans_compact = format_spans_compact(packet.spans)

        # Stage 1: Quick Classification (always runs)
        stage1_result = await self._stage1_classify(packet, spans_compact)
        api_calls += 1

        # Determine if Stage 2 is needed
        needs_deep_analysis = (
            stage1_result.get("confidence", 0) < self.confidence_threshold
            or stage1_result.get("category", "other_needs_review") == "other_needs_review"
        )

        trigger_reason = ""
        if needs_deep_analysis:
            if stage1_result.get("confidence", 0) < self.confidence_threshold:
                trigger_reason = f"Low confidence: {stage1_result.get('confidence', 0):.2f} < {self.confidence_threshold}"
            else:
                trigger_reason = "Category is 'other_needs_review'"

        # Stage 2: Deep Analysis (conditional)
        if needs_deep_analysis:
            logger.info(f"[{packet.task_id[:8]}] Triggering deep analysis: {trigger_reason}")
            spans_detailed = format_spans_detailed(packet.spans)
            stage2_result = await self._stage2_analyze(packet, stage1_result, spans_detailed)
            api_calls += 1

            # Extract final results
            category = stage2_result.get("final_category", stage1_result.get("category", "other_needs_review"))
            confidence = stage2_result.get("confidence", stage1_result.get("confidence", 0.5))
            explanation = stage2_result.get("explanation", stage1_result.get("brief_reason", ""))
            turning_point = stage2_result.get("turning_point", "")
            narrative = stage2_result.get("narrative", "")
            fix_suggestions = stage2_result.get("fix_suggestions", [])
            key_evidence = stage2_result.get("key_evidence", [])

            # Handle new category suggestion
            suggested_new_category = None
            if stage2_result.get("suggested_new_category"):
                suggestion_data = stage2_result["suggested_new_category"]
                suggested_new_category = NewCategorySuggestion(
                    task_id=packet.task_id,
                    suggested_name=suggestion_data.get("name", "unknown"),
                    description=suggestion_data.get("description", ""),
                    reason=suggestion_data.get("reason", ""),
                    example_question=packet.user_request[:500],
                    example_expected=packet.expected_output[:200],
                    example_actual=packet.actual_output[:200],
                )
                self.category_manager.add_suggestion(suggested_new_category)

            stages_used = 2
        else:
            # Use Stage 1 results directly
            category = stage1_result.get("category", "other_needs_review")
            confidence = stage1_result.get("confidence", 0.5)
            explanation = stage1_result.get("brief_reason", "")
            turning_point = stage1_result.get("key_indicator", "")
            narrative = ""
            fix_suggestions = []
            key_evidence = [stage1_result.get("key_indicator", "")] if stage1_result.get("key_indicator") else []
            suggested_new_category = None
            stages_used = 1

        total_time = (time.time() - start_time) * 1000

        return HybridAnalysisResult(
            task_id=packet.task_id,
            category=category,
            confidence=confidence,
            explanation=explanation,
            turning_point=turning_point,
            fix_suggestions=fix_suggestions,
            key_evidence=key_evidence,
            stages_used=stages_used,
            total_time_ms=total_time,
            api_calls=api_calls,
            narrative=narrative,
            error_recovery={},
            # Hybrid-specific fields
            stage1_category=stage1_result.get("category", ""),
            stage1_confidence=stage1_result.get("confidence", 0.0),
            stage1_reason=stage1_result.get("brief_reason", ""),
            deep_analysis_triggered=needs_deep_analysis,
            trigger_reason=trigger_reason,
            suggested_new_category=suggested_new_category,
        )

    async def _stage1_classify(
        self, packet: FailurePacket, spans_compact: str
    ) -> dict[str, Any]:
        """Stage 1: Quick classification.

        Args:
            packet: The failure packet.
            spans_compact: Compact span representation.

        Returns:
            Classification result dict.
        """
        # Build prompt with category descriptions
        prompt = STAGE1_QUICK_CLASSIFY_PROMPT.format(
            question=packet.user_request,
            expected=packet.expected_output,
            actual=packet.actual_output,
            spans=spans_compact,
            **{f"desc_{cat.value}": desc for cat, desc in CATEGORY_DESCRIPTIONS.items()},
        )

        response = await self._call_llm(
            prompt,
            model=self.quick_model,
            max_tokens=400,
            json_mode=True,
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Stage 1 response: {response[:200]}")
            return {
                "category": "other_needs_review",
                "confidence": 0.3,
                "brief_reason": "Failed to parse classification",
                "key_indicator": "",
            }

    async def _stage2_analyze(
        self,
        packet: FailurePacket,
        stage1_result: dict[str, Any],
        spans_detailed: str,
    ) -> dict[str, Any]:
        """Stage 2: Deep analysis.

        Args:
            packet: The failure packet.
            stage1_result: Result from Stage 1.
            spans_detailed: Detailed span representation.

        Returns:
            Deep analysis result dict.
        """
        prompt = STAGE2_DEEP_ANALYSIS_PROMPT.format(
            quick_category=stage1_result.get("category", "unknown"),
            quick_confidence=stage1_result.get("confidence", 0),
            quick_reason=stage1_result.get("brief_reason", ""),
            question=packet.user_request,
            expected=packet.expected_output,
            actual=packet.actual_output,
            spans=spans_detailed,
            **{f"desc_{cat.value}": desc for cat, desc in CATEGORY_DESCRIPTIONS.items()},
        )

        response = await self._call_llm(
            prompt,
            model=self.deep_model,
            max_tokens=1200,
            json_mode=True,
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Stage 2 response: {response[:200]}")
            return {
                "final_category": stage1_result.get("category", "other_needs_review"),
                "confidence": stage1_result.get("confidence", 0.5),
                "explanation": response[:500],
                "turning_point": "",
                "narrative": "",
                "fix_suggestions": [],
                "key_evidence": [],
            }

    async def _call_llm(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 500,
        json_mode: bool = False,
    ) -> str:
        """Make LLM API call.

        Args:
            prompt: The prompt to send.
            model: Model identifier.
            max_tokens: Maximum tokens in response.
            json_mode: Whether to request JSON response format.

        Returns:
            LLM response content.
        """
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def save_category_suggestions(self) -> None:
        """Save accumulated category suggestions to file."""
        self.category_manager.save_suggestions()


async def run_hybrid_analysis(
    packets: list[FailurePacket],
    output_dir: Path,
    concurrency: int = 5,
    confidence_threshold: float = 0.8,
) -> dict[str, Any]:
    """Run hybrid analysis on a batch of failure packets.

    Args:
        packets: List of failure packets to analyze.
        output_dir: Directory to save results.
        concurrency: Maximum concurrent API calls.
        confidence_threshold: Threshold for triggering deep analysis.

    Returns:
        Statistics dictionary.
    """
    category_manager = CategoryManager(output_dir / "new_category_suggestions.jsonl")
    analyzer = HybridFailureAnalyzer(
        confidence_threshold=confidence_threshold,
        category_manager=category_manager,
    )

    semaphore = asyncio.Semaphore(concurrency)

    async def analyze_with_semaphore(packet: FailurePacket) -> HybridAnalysisResult:
        async with semaphore:
            try:
                logger.info(f"Analyzing {packet.task_id[:8]}...")
                result = await analyzer.analyze(packet)

                # Update packet with classification results
                packet.failure_category = result.category
                packet.classification_source = f"hybrid_stage{result.stages_used}"
                packet.llm_analysis = {
                    "confidence": result.confidence,
                    "explanation": result.explanation,
                    "turning_point": result.turning_point,
                    "fix_suggestions": result.fix_suggestions,
                    "key_evidence": result.key_evidence,
                    "deep_analysis_triggered": result.deep_analysis_triggered,
                }

                logger.info(
                    f"{packet.task_id[:8]} -> {result.category} "
                    f"(conf={result.confidence:.2f}, stages={result.stages_used})"
                )
                return result
            except Exception as e:
                logger.error(f"Error analyzing {packet.task_id[:8]}: {e}")
                packet.failure_category = "error"
                packet.classification_source = "hybrid_error"
                return HybridAnalysisResult(
                    task_id=packet.task_id,
                    category="error",
                    confidence=0.0,
                    explanation=str(e),
                    stages_used=0,
                    total_time_ms=0,
                    api_calls=0,
                )

    # Run analysis
    start_time = time.time()
    results = await asyncio.gather(*[analyze_with_semaphore(p) for p in packets])
    total_time = time.time() - start_time

    # Save results
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "hybrid_analysis_results.json", "w") as f:
        json.dump([r.to_dict() for r in results], f, indent=2, ensure_ascii=False)

    # Save category suggestions
    analyzer.save_category_suggestions()

    # Calculate statistics
    stats = {
        "total_cases": len(packets),
        "total_time_s": total_time,
        "avg_time_ms": sum(r.total_time_ms for r in results) / len(results) if results else 0,
        "total_api_calls": sum(r.api_calls for r in results),
        "avg_confidence": sum(r.confidence for r in results) / len(results) if results else 0,
        "deep_analysis_triggered": sum(1 for r in results if r.deep_analysis_triggered),
        "deep_analysis_rate": sum(1 for r in results if r.deep_analysis_triggered) / len(results) if results else 0,
        "stages_distribution": {
            1: sum(1 for r in results if r.stages_used == 1),
            2: sum(1 for r in results if r.stages_used == 2),
        },
        "category_distribution": {},
        "new_categories_suggested": len(category_manager.suggestions),
    }

    for r in results:
        stats["category_distribution"][r.category] = stats["category_distribution"].get(r.category, 0) + 1

    with open(output_dir / "hybrid_analysis_stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    # Print summary
    print("\n" + "=" * 70)
    print("HYBRID ANALYSIS RESULTS")
    print("=" * 70)
    print(f"\nTotal cases analyzed: {len(packets)}")
    print(f"Total time: {total_time:.2f}s")
    print(f"Average time per case: {stats['avg_time_ms']:.0f}ms")
    print(f"Total API calls: {stats['total_api_calls']}")
    print(f"Average confidence: {stats['avg_confidence']:.2f}")
    print(f"\nDeep analysis triggered: {stats['deep_analysis_triggered']} ({stats['deep_analysis_rate']*100:.1f}%)")
    print(f"Stages distribution: {stats['stages_distribution']}")
    print(f"New categories suggested: {stats['new_categories_suggested']}")

    print("\nCategory Distribution:")
    print(f"{'Category':<25} {'Count':<10} {'Percentage':<10}")
    print("-" * 45)
    for cat, count in sorted(stats["category_distribution"].items(), key=lambda x: -x[1]):
        pct = count / len(results) * 100 if results else 0
        print(f"{cat:<25} {count:<10} {pct:.1f}%")

    print("=" * 70)

    return stats
