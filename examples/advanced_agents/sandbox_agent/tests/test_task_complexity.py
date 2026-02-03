# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for task complexity estimation."""

import pytest

from nat_sandbox_agent.utils.task_complexity import (
    TaskComplexityEstimator,
    TaskComplexity,
    ComplexityLevel,
    estimate_task_complexity,
    get_recommended_iterations,
)


class TestComplexityLevel:
    """Tests for ComplexityLevel enum."""

    def test_enum_values(self):
        assert ComplexityLevel.SIMPLE == "simple"
        assert ComplexityLevel.MODERATE == "moderate"
        assert ComplexityLevel.COMPLEX == "complex"
        assert ComplexityLevel.VERY_COMPLEX == "very_complex"


class TestTaskComplexity:
    """Tests for TaskComplexity dataclass."""

    def test_default_values(self):
        tc = TaskComplexity(level=ComplexityLevel.SIMPLE, score=0.1)
        assert tc.indicators == {}
        assert tc.recommended_max_iterations == 20
        assert tc.recommended_tools == []
        assert tc.warnings == []

    def test_to_dict(self):
        tc = TaskComplexity(
            level=ComplexityLevel.MODERATE,
            score=0.35,
            indicators={"multi_hop": True},
            recommended_max_iterations=25,
        )
        d = tc.to_dict()
        assert d["level"] == "moderate"
        assert d["score"] == 0.35
        assert d["indicators"]["multi_hop"] is True
        assert d["recommended_max_iterations"] == 25


class TestTaskComplexityEstimator:
    """Tests for TaskComplexityEstimator."""

    def setup_method(self):
        self.estimator = TaskComplexityEstimator()

    def test_simple_question(self):
        question = "What is the capital of France?"
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.level == ComplexityLevel.SIMPLE
        assert complexity.score < 0.2

    def test_multi_hop_detection(self):
        question = "First find the CEO of Apple, then search for their net worth."
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.indicators["multi_hop"] is True
        assert complexity.level in (ComplexityLevel.MODERATE, ComplexityLevel.COMPLEX)

    def test_video_audio_detection(self):
        question = "Watch this YouTube video and summarize the main points."
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.indicators["video_audio"] is True
        assert "youtube_transcript" in complexity.recommended_tools

    def test_calculation_detection(self):
        question = "Calculate the percentage change in population from 2010 to 2020."
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.indicators["calculation"] is True

    def test_file_processing_detection(self):
        question = "Extract data from the attached Excel spreadsheet."
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.indicators["file_processing"] is True
        assert "file_read" in complexity.recommended_tools

    def test_research_detection(self):
        question = "Find all Nobel Prize winners in Physics since 2000."
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.indicators["research"] is True
        assert "web_search" in complexity.recommended_tools

    def test_advanced_reasoning_detection(self):
        question = "Analyze why the company's stock price dropped and explain the consequences."
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.indicators["advanced_reasoning"] is True

    def test_constraint_detection(self):
        question = "List all countries with population between 10 and 50 million."
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.indicators["has_constraints"] is True

    def test_long_question_detection(self):
        question = "A" * 600  # Long question
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.indicators["long_question"] is True

    def test_multiple_questions_detection(self):
        question = "What is the capital of France? And what is its population?"
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.indicators["multiple_questions"] is True

    def test_complex_task_increases_iterations(self):
        simple_q = "What is 2+2?"
        complex_q = (
            "First, watch this YouTube video about quantum computing. "
            "Then calculate the percentage of qubits mentioned. "
            "Finally, explain why this matters."
        )

        simple_complexity = self.estimator.estimate_complexity(simple_q)
        complex_complexity = self.estimator.estimate_complexity(complex_q)

        assert complex_complexity.recommended_max_iterations > simple_complexity.recommended_max_iterations

    def test_very_complex_task(self):
        question = (
            "First, download the PDF from the given URL. "
            "Then watch the YouTube video to understand the context. "
            "Calculate the percentage change in the values mentioned. "
            "Finally, analyze why these changes occurred and explain the implications."
        )
        complexity = self.estimator.estimate_complexity(question)
        assert complexity.level in (ComplexityLevel.COMPLEX, ComplexityLevel.VERY_COMPLEX)
        assert complexity.recommended_max_iterations >= 40

    def test_warnings_for_video_tasks(self):
        question = "Watch this YouTube video and extract the main points."
        complexity = self.estimator.estimate_complexity(question)
        assert any("video" in w.lower() or "youtube" in w.lower() for w in complexity.warnings)

    def test_warnings_for_file_tasks(self):
        question = "Read the attached PDF and summarize it."
        complexity = self.estimator.estimate_complexity(question)
        assert any("file" in w.lower() for w in complexity.warnings)

    def test_adjust_config(self):
        question = "Download the PDF, calculate totals, then analyze results step by step."
        base_config = {"max_iterations": 15, "other_setting": "value"}

        adjusted = self.estimator.adjust_config(question, base_config)

        assert adjusted["max_iterations"] > 15  # Should be increased
        assert adjusted["other_setting"] == "value"  # Preserved
        assert "_complexity" in adjusted


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_estimate_task_complexity(self):
        complexity = estimate_task_complexity("What is the capital of France?")
        assert isinstance(complexity, TaskComplexity)
        assert complexity.level == ComplexityLevel.SIMPLE

    def test_get_recommended_iterations_simple(self):
        iterations = get_recommended_iterations("What is the capital of France?")
        assert iterations <= 20  # Simple tasks get fewer iterations

    def test_get_recommended_iterations_complex(self):
        iterations = get_recommended_iterations(
            "First watch the YouTube video, then calculate percentages, "
            "and finally analyze the results with multiple steps."
        )
        assert iterations >= 25  # Complex tasks get more iterations
