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
"""Tests for SandboxToolExecutor."""

from unittest.mock import AsyncMock

import pytest

from nat.sandbox import CommandResult
from nat.sandbox.tools import SandboxToolExecutor
from nat.sandbox.tools import truncate_output


class TestTruncateOutput:
    """Tests for truncate_output utility function."""

    def test_short_text_not_truncated(self):
        """Test that short text is not truncated."""
        result = truncate_output("Short text", max_chars=100)
        assert result == "Short text"

    def test_long_text_truncated(self):
        """Test that long text is truncated with indicator."""
        long_text = "A" * 100
        result = truncate_output(long_text, max_chars=20)

        assert len(result) < 100
        assert "truncated" in result.lower()

    def test_empty_text(self):
        """Test handling of empty text."""
        result = truncate_output("", max_chars=100)
        assert result == ""

    def test_exact_length_not_truncated(self):
        """Test text at exact max length is not truncated."""
        text = "A" * 100
        result = truncate_output(text, max_chars=100)
        assert result == text


class TestSandboxToolExecutor:
    """Tests for SandboxToolExecutor."""

    def test_init_with_defaults(self, mock_sandbox):
        """Test executor initialization with default values."""
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        assert executor.sandbox is mock_sandbox
        assert executor.max_output_chars == 16000
        assert executor.default_timeout == 120

    def test_init_with_custom_values(self, mock_sandbox):
        """Test executor initialization with custom values."""
        executor = SandboxToolExecutor(
            sandbox=mock_sandbox,
            max_output_chars=5000,
            default_timeout=60,
        )

        assert executor.max_output_chars == 5000
        assert executor.default_timeout == 60

    def test_truncate_short_text(self, mock_sandbox):
        """Test that short text is not truncated."""
        executor = SandboxToolExecutor(sandbox=mock_sandbox, max_output_chars=100)

        result = executor.truncate("Short text")

        assert result == "Short text"

    def test_truncate_long_text(self, mock_sandbox):
        """Test that long text is truncated with indicator."""
        executor = SandboxToolExecutor(sandbox=mock_sandbox, max_output_chars=20)

        long_text = "A" * 100
        result = executor.truncate(long_text)

        assert len(result) < 100
        assert "truncated" in result

    @pytest.mark.asyncio
    async def test_list_generated_files_success(self, mock_sandbox):
        """Test listing generated files using shell command."""
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout="output.txt\ndata.json\n", stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        files = await executor.list_generated_files()

        assert files == ["/workspace/output/output.txt", "/workspace/output/data.json"]
        mock_sandbox.run_command.assert_called_once_with("ls -1 /workspace/output", timeout=120)

    @pytest.mark.asyncio
    async def test_list_generated_files_handles_exception(self, mock_sandbox):
        """Test that list_generated_files handles exceptions gracefully."""
        mock_sandbox.run_command = AsyncMock(side_effect=Exception("Directory not found"))
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        files = await executor.list_generated_files()

        assert files == []

    @pytest.mark.asyncio
    async def test_list_generated_files_empty_on_error(self, mock_sandbox):
        """Test that list_generated_files returns empty list on command failure."""
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=1, stdout="", stderr="ls: cannot access")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        files = await executor.list_generated_files()

        assert files == []

    @pytest.mark.asyncio
    async def test_list_generated_files_empty_directory(self, mock_sandbox):
        """Test listing empty output directory."""
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout="", stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        files = await executor.list_generated_files()

        assert files == []
