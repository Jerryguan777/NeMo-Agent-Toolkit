# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for hybrid failure analyzer."""

import pytest
from pathlib import Path
import tempfile

from nat_sandbox_agent.analysis.hybrid_analyzer import (
    CategoryManager,
    NewCategorySuggestion,
    HybridAnalysisResult,
    CATEGORY_DESCRIPTIONS,
)
from nat_sandbox_agent.analysis.llm_analyzer import RootCauseCategory


class TestRootCauseCategory:
    """Tests for RootCauseCategory enum."""

    def test_core_categories_exist(self):
        assert RootCauseCategory.EVIDENCE_EXTRACTION.value == "evidence_extraction"
        assert RootCauseCategory.REASONING_ERROR.value == "reasoning_error"
        assert RootCauseCategory.OUTPUT_FORMAT.value == "output_format"
        assert RootCauseCategory.ITERATION_LIMIT.value == "iteration_limit"
        assert RootCauseCategory.EVIDENCE_UTILIZATION.value == "evidence_utilization"
        assert RootCauseCategory.TASK_UNDERSTANDING.value == "task_understanding"
        assert RootCauseCategory.API_ERROR.value == "api_error"
        assert RootCauseCategory.TOOL_LIMITATION.value == "tool_limitation"

    def test_new_categories_exist(self):
        assert RootCauseCategory.PARTIAL_ANSWER.value == "partial_answer"
        assert RootCauseCategory.DATA_UNAVAILABLE.value == "data_unavailable"

    def test_fallback_category_exists(self):
        assert RootCauseCategory.OTHER_NEEDS_REVIEW.value == "other_needs_review"


class TestCategoryDescriptions:
    """Tests for category descriptions."""

    def test_all_categories_have_descriptions(self):
        for category in RootCauseCategory:
            assert category in CATEGORY_DESCRIPTIONS, f"Missing description for {category}"

    def test_descriptions_are_meaningful(self):
        for category, description in CATEGORY_DESCRIPTIONS.items():
            assert len(description) > 20, f"Description too short for {category}"


class TestNewCategorySuggestion:
    """Tests for NewCategorySuggestion dataclass."""

    def test_creation(self):
        suggestion = NewCategorySuggestion(
            task_id="test-123",
            suggested_name="new_category",
            description="A new category description",
            reason="Existing categories don't fit",
            example_question="What is X?",
            example_expected="Y",
            example_actual="Z"
        )

        assert suggestion.task_id == "test-123"
        assert suggestion.suggested_name == "new_category"
        assert suggestion.timestamp is not None  # Auto-generated

    def test_timestamp_auto_generated(self):
        suggestion = NewCategorySuggestion(
            task_id="test",
            suggested_name="test",
            description="test",
            reason="test",
            example_question="test",
            example_expected="test",
            example_actual="test"
        )

        assert suggestion.timestamp is not None
        assert len(suggestion.timestamp) > 0


class TestCategoryManager:
    """Tests for CategoryManager."""

    def test_init_with_default_path(self):
        manager = CategoryManager()
        assert manager.suggestions_path == Path("new_category_suggestions.jsonl")
        assert manager.suggestions == []

    def test_init_with_custom_path(self):
        custom_path = Path("/tmp/suggestions.jsonl")
        manager = CategoryManager(suggestions_path=custom_path)
        assert manager.suggestions_path == custom_path

    def test_add_suggestion(self):
        manager = CategoryManager()
        suggestion = NewCategorySuggestion(
            task_id="test-123",
            suggested_name="new_cat",
            description="desc",
            reason="reason",
            example_question="q",
            example_expected="e",
            example_actual="a"
        )

        manager.add_suggestion(suggestion)

        assert len(manager.suggestions) == 1
        assert manager.suggestions[0].suggested_name == "new_cat"

    def test_get_category_stats(self):
        manager = CategoryManager()

        # Add multiple suggestions
        for i in range(3):
            manager.add_suggestion(NewCategorySuggestion(
                task_id=f"test-{i}",
                suggested_name="category_a",
                description="desc",
                reason="reason",
                example_question="q",
                example_expected="e",
                example_actual="a"
            ))

        manager.add_suggestion(NewCategorySuggestion(
            task_id="test-4",
            suggested_name="category_b",
            description="desc",
            reason="reason",
            example_question="q",
            example_expected="e",
            example_actual="a"
        ))

        stats = manager.get_category_stats()

        assert stats["category_a"] == 3
        assert stats["category_b"] == 1

    def test_save_suggestions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suggestions.jsonl"
            manager = CategoryManager(suggestions_path=path)

            manager.add_suggestion(NewCategorySuggestion(
                task_id="test-1",
                suggested_name="new_cat",
                description="desc",
                reason="reason",
                example_question="q",
                example_expected="e",
                example_actual="a"
            ))

            manager.save_suggestions()

            assert path.exists()
            content = path.read_text()
            assert "new_cat" in content
            assert "test-1" in content

    def test_save_empty_suggestions_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suggestions.jsonl"
            manager = CategoryManager(suggestions_path=path)

            manager.save_suggestions()

            assert not path.exists()


class TestHybridAnalysisResult:
    """Tests for HybridAnalysisResult dataclass."""

    def test_extends_analysis_result(self):
        result = HybridAnalysisResult(
            task_id="test-123",
            category="evidence_extraction",
            confidence=0.85,
            explanation="Test explanation",
            stages_used=1,
            total_time_ms=500.0,
            api_calls=1
        )

        # Base fields
        assert result.task_id == "test-123"
        assert result.category == "evidence_extraction"
        assert result.confidence == 0.85

        # Extended fields
        assert result.stage1_category == ""
        assert result.stage1_confidence == 0.0
        assert result.deep_analysis_triggered is False

    def test_with_deep_analysis(self):
        result = HybridAnalysisResult(
            task_id="test-123",
            category="reasoning_error",
            confidence=0.9,
            explanation="Deep analysis result",
            stages_used=2,
            total_time_ms=1500.0,
            api_calls=2,
            stage1_category="other_needs_review",
            stage1_confidence=0.5,
            stage1_reason="Uncertain",
            deep_analysis_triggered=True,
            trigger_reason="Low confidence: 0.50 < 0.80"
        )

        assert result.deep_analysis_triggered is True
        assert result.stages_used == 2
        assert result.stage1_category == "other_needs_review"
        assert "Low confidence" in result.trigger_reason

    def test_with_new_category_suggestion(self):
        suggestion = NewCategorySuggestion(
            task_id="test-123",
            suggested_name="new_failure_type",
            description="A new type of failure",
            reason="Doesn't fit existing categories",
            example_question="q",
            example_expected="e",
            example_actual="a"
        )

        result = HybridAnalysisResult(
            task_id="test-123",
            category="other_needs_review",
            confidence=0.6,
            explanation="Suggested new category",
            stages_used=2,
            total_time_ms=2000.0,
            api_calls=2,
            suggested_new_category=suggestion
        )

        assert result.suggested_new_category is not None
        assert result.suggested_new_category.suggested_name == "new_failure_type"

    def test_to_dict_includes_all_fields(self):
        result = HybridAnalysisResult(
            task_id="test-123",
            category="output_format",
            confidence=0.95,
            explanation="Format issue",
            stages_used=1,
            total_time_ms=300.0,
            api_calls=1,
            stage1_category="output_format",
            stage1_confidence=0.95,
            deep_analysis_triggered=False
        )

        d = result.to_dict()

        assert d["task_id"] == "test-123"
        assert d["category"] == "output_format"
        assert d["confidence"] == 0.95
        assert d["stages_used"] == 1
