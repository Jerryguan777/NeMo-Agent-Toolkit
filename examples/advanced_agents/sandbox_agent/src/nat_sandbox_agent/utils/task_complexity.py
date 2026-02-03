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

"""Task complexity estimation for dynamic resource allocation.

This module provides tools to estimate the complexity of a task based on
question patterns, allowing for dynamic adjustment of iteration limits
and other resources.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ComplexityLevel(str, Enum):
    """Task complexity levels."""

    SIMPLE = "simple"  # Single-step, straightforward tasks
    MODERATE = "moderate"  # Multi-step but well-defined tasks
    COMPLEX = "complex"  # Multi-hop reasoning, multiple sources
    VERY_COMPLEX = "very_complex"  # Level 3 tasks, advanced reasoning


@dataclass
class TaskComplexity:
    """Detailed complexity assessment for a task."""

    level: ComplexityLevel
    score: float  # 0.0 to 1.0
    indicators: dict[str, bool] = field(default_factory=dict)
    recommended_max_iterations: int = 20
    recommended_tools: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "level": self.level.value,
            "score": self.score,
            "indicators": self.indicators,
            "recommended_max_iterations": self.recommended_max_iterations,
            "recommended_tools": self.recommended_tools,
            "warnings": self.warnings,
        }


class TaskComplexityEstimator:
    """Estimates task complexity based on question patterns.

    This estimator analyzes questions to predict:
    - Expected complexity level
    - Required tools
    - Recommended iteration limits
    - Potential challenges

    Used to dynamically allocate resources and warn about potential issues.
    """

    # Patterns indicating different complexity factors
    MULTI_HOP_PATTERNS = [
        r"(then|after|using that|based on|with this|next|finally)",
        r"(first|second|third|finally|lastly)",
        r"(step \d|steps?:)",
        r"(and then|after that|following this)",
    ]

    VIDEO_AUDIO_PATTERNS = [
        r"(youtube|video|watch|audio|listen|mp3|mp4|wav)",
        r"(podcast|episode|clip|recording)",
        r"(transcript|subtitle|caption)",
    ]

    CALCULATION_PATTERNS = [
        r"(calculate|compute|how many|how much|percentage|ratio)",
        r"(sum|total|average|mean|median|standard deviation)",
        r"(multiply|divide|subtract|add|\+|\-|\*|\/)",
        r"(formula|equation|solve)",
    ]

    FILE_PROCESSING_PATTERNS = [
        r"(pdf|excel|csv|xml|json|spreadsheet)",
        r"(attached|uploaded|file|document)",
        r"(image|picture|photo|screenshot)",
        r"(download|extract from)",
    ]

    RESEARCH_PATTERNS = [
        r"(find|search|look up|research|investigate)",
        r"(who|what|when|where|which)",
        r"(compare|contrast|difference between)",
        r"(list all|name all|identify all)",
    ]

    ADVANCED_REASONING_PATTERNS = [
        r"(why|explain|analyze|evaluate|assess)",
        r"(cause|effect|reason|because)",
        r"(implication|consequence|result)",
        r"(hypothesis|theory|conclusion)",
    ]

    CONSTRAINT_PATTERNS = [
        r"(without|excluding|except|not including)",
        r"(only|just|exactly|precisely)",
        r"(between|range|from .* to)",
        r"(no more than|at least|at most)",
    ]

    def estimate_complexity(self, question: str) -> TaskComplexity:
        """Estimate the complexity of a task.

        Args:
            question: The task question or prompt.

        Returns:
            TaskComplexity with detailed assessment.
        """
        question_lower = question.lower()

        # Detect complexity indicators
        indicators = {
            "multi_hop": self._matches_any(question_lower, self.MULTI_HOP_PATTERNS),
            "video_audio": self._matches_any(question_lower, self.VIDEO_AUDIO_PATTERNS),
            "calculation": self._matches_any(question_lower, self.CALCULATION_PATTERNS),
            "file_processing": self._matches_any(question_lower, self.FILE_PROCESSING_PATTERNS),
            "research": self._matches_any(question_lower, self.RESEARCH_PATTERNS),
            "advanced_reasoning": self._matches_any(question_lower, self.ADVANCED_REASONING_PATTERNS),
            "has_constraints": self._matches_any(question_lower, self.CONSTRAINT_PATTERNS),
            "long_question": len(question) > 500,
            "multiple_questions": question.count("?") > 1,
        }

        # Calculate complexity score
        weights = {
            "multi_hop": 0.2,
            "video_audio": 0.15,
            "calculation": 0.1,
            "file_processing": 0.15,
            "research": 0.1,
            "advanced_reasoning": 0.15,
            "has_constraints": 0.05,
            "long_question": 0.05,
            "multiple_questions": 0.05,
        }

        score = sum(weights[k] for k, v in indicators.items() if v)

        # Determine complexity level
        if score < 0.2:
            level = ComplexityLevel.SIMPLE
            max_iterations = 15
        elif score < 0.4:
            level = ComplexityLevel.MODERATE
            max_iterations = 25
        elif score < 0.6:
            level = ComplexityLevel.COMPLEX
            max_iterations = 40
        else:
            level = ComplexityLevel.VERY_COMPLEX
            max_iterations = 50

        # Determine recommended tools
        recommended_tools = self._get_recommended_tools(indicators)

        # Generate warnings
        warnings = self._generate_warnings(indicators)

        return TaskComplexity(
            level=level,
            score=score,
            indicators=indicators,
            recommended_max_iterations=max_iterations,
            recommended_tools=recommended_tools,
            warnings=warnings,
        )

    def _matches_any(self, text: str, patterns: list[str]) -> bool:
        """Check if text matches any of the patterns."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _get_recommended_tools(self, indicators: dict[str, bool]) -> list[str]:
        """Get recommended tools based on indicators."""
        tools = ["shell", "python"]  # Always include basics

        if indicators.get("research"):
            tools.append("web_search")
            tools.append("web_browse")

        if indicators.get("video_audio"):
            tools.append("youtube_transcript")

        if indicators.get("file_processing"):
            tools.append("file_read")
            tools.append("file_write")

        if indicators.get("calculation"):
            tools.append("verify_calculation")

        return tools

    def _generate_warnings(self, indicators: dict[str, bool]) -> list[str]:
        """Generate warnings based on indicators."""
        warnings = []

        if indicators.get("video_audio"):
            warnings.append(
                "Task involves video/audio processing. Ensure yt-dlp and ffmpeg "
                "are available. Consider using youtube_transcript for YouTube videos."
            )

        if indicators.get("file_processing"):
            warnings.append(
                "Task involves file processing. Check /workspace/input for "
                "uploaded files. Use appropriate libraries for file types."
            )

        if indicators.get("multi_hop") and indicators.get("calculation"):
            warnings.append(
                "Complex multi-step calculation task. Use Python to verify "
                "intermediate results and track state across steps."
            )

        if indicators.get("advanced_reasoning"):
            warnings.append(
                "Task requires advanced reasoning. Break down into explicit "
                "steps and verify logic at each stage."
            )

        if indicators.get("multiple_questions"):
            warnings.append(
                "Question contains multiple sub-questions. Address each "
                "separately and combine answers at the end."
            )

        return warnings

    def adjust_config(
        self,
        question: str,
        base_config: dict[str, Any],
    ) -> dict[str, Any]:
        """Adjust configuration based on task complexity.

        Args:
            question: The task question.
            base_config: Base configuration to adjust.

        Returns:
            Adjusted configuration dictionary.
        """
        complexity = self.estimate_complexity(question)
        adjusted = base_config.copy()

        # Adjust max_iterations
        current_max = adjusted.get("max_iterations", 20)
        adjusted["max_iterations"] = max(current_max, complexity.recommended_max_iterations)

        # Add complexity metadata
        adjusted["_complexity"] = complexity.to_dict()

        return adjusted


def estimate_task_complexity(question: str) -> TaskComplexity:
    """Convenience function to estimate task complexity.

    Args:
        question: The task question or prompt.

    Returns:
        TaskComplexity assessment.
    """
    estimator = TaskComplexityEstimator()
    return estimator.estimate_complexity(question)


def get_recommended_iterations(question: str) -> int:
    """Get recommended max iterations for a task.

    Args:
        question: The task question.

    Returns:
        Recommended max iterations.
    """
    complexity = estimate_task_complexity(question)
    return complexity.recommended_max_iterations
