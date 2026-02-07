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

"""Tests for utility functions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nat_sandbox_agent.utils.answer_cleaning import clean_answer_with_llm


def _make_mock_llm(response_text: str) -> MagicMock:
    """Create a mock LLM that returns the given text."""
    mock_llm = MagicMock()
    mock_result = MagicMock()
    mock_result.content = response_text
    mock_llm.ainvoke = AsyncMock(return_value=mock_result)
    return mock_llm


class TestCleanAnswerWithLLM:
    """Tests for the LLM-based clean_answer_with_llm function."""

    @pytest.mark.asyncio
    async def test_empty_string(self):
        """Test that empty string returns empty string."""
        llm = _make_mock_llm("")
        assert await clean_answer_with_llm(llm, "What?", "") == ""
        # LLM should not be called for empty input
        llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_input(self):
        """Test that None input returns None."""
        llm = _make_mock_llm("")
        assert await clean_answer_with_llm(llm, "What?", None) is None
        llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_short_numeric_bypass(self):
        """Test that very short numeric answers skip the LLM call."""
        llm = _make_mock_llm("")
        assert await clean_answer_with_llm(llm, "How many?", "42") == "42"
        llm.ainvoke.assert_not_called()

        assert await clean_answer_with_llm(llm, "How many?", "-5") == "-5"
        llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_called_with_question_and_answer(self):
        """Test that the LLM receives both question and raw answer."""
        llm = _make_mock_llm("Paris")
        result = await clean_answer_with_llm(llm, "What is the capital?", "The answer is Paris")
        assert result == "Paris"

        # Verify the LLM was called with messages containing the question and answer
        call_args = llm.ainvoke.call_args[0][0]
        assert len(call_args) == 2  # system + human
        human_msg = call_args[1].content
        assert "What is the capital?" in human_msg
        assert "The answer is Paris" in human_msg

    @pytest.mark.asyncio
    async def test_llm_removes_prefix(self):
        """Test that LLM-based cleaning removes common prefixes."""
        llm = _make_mock_llm("Paris")
        result = await clean_answer_with_llm(llm, "What city?", "The answer is: Paris")
        assert result == "Paris"

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self):
        """Test that raw answer is returned when LLM call fails."""
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=RuntimeError("API error"))
        result = await clean_answer_with_llm(llm, "What?", "  Paris  ")
        assert result == "Paris"  # stripped raw answer

    @pytest.mark.asyncio
    async def test_fallback_on_empty_llm_response(self):
        """Test fallback when LLM returns empty content."""
        llm = _make_mock_llm("")
        result = await clean_answer_with_llm(llm, "What?", "Paris")
        assert result == "Paris"

    @pytest.mark.asyncio
    async def test_fallback_on_suspiciously_long_response(self):
        """Test fallback when LLM returns overly long output."""
        llm = _make_mock_llm("A" * 500)
        result = await clean_answer_with_llm(llm, "What?", "Paris")
        assert result == "Paris"

    @pytest.mark.asyncio
    async def test_preserves_formula(self):
        """Test that LLM preserves logical formulas (the key bug in rule-based)."""
        formula = "(¬A → B) ↔ (A ∨ ¬B)"
        llm = _make_mock_llm(formula)
        result = await clean_answer_with_llm(
            llm,
            "Which formula is not logically equivalent?",
            formula,
        )
        assert result == formula

    @pytest.mark.asyncio
    async def test_extracts_setting_name(self):
        """Test that LLM extracts setting from scene heading."""
        llm = _make_mock_llm("THE CASTLE")
        result = await clean_answer_with_llm(
            llm,
            "What is this location called?",
            "INT. THE CASTLE - DAY",
        )
        assert result == "THE CASTLE"

    @pytest.mark.asyncio
    async def test_preserves_chess_notation(self):
        """Test that LLM does not strip chess notation to just a number."""
        llm = _make_mock_llm("h5")
        result = await clean_answer_with_llm(
            llm,
            "Provide the correct next move in algebraic notation.",
            "h5",
        )
        assert result == "h5"
