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
"""Tests for file operation tools (read_file, write_file)."""

from unittest.mock import AsyncMock

import pytest

from nat.sandbox.tools import SandboxToolExecutor
from nat.sandbox.tools.file_ops import read_file
from nat.sandbox.tools.file_ops import write_file


class TestFileReadTool:
    """Tests for file read tool."""

    @pytest.mark.asyncio
    async def test_read_file_success(self, mock_sandbox):
        """Test successful file read."""
        mock_sandbox.read_file = AsyncMock(return_value="File content here")
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await read_file(executor, "/workspace/test.txt")

        assert result["status"] == "success"
        assert result["content"] == "File content here"
        assert result["path"] == "/workspace/test.txt"

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, mock_sandbox):
        """Test file not found error."""
        mock_sandbox.read_file = AsyncMock(side_effect=FileNotFoundError("No such file"))
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await read_file(executor, "/workspace/nonexistent.txt")

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_file_other_error(self, mock_sandbox):
        """Test handling of other errors."""
        mock_sandbox.read_file = AsyncMock(side_effect=PermissionError("Access denied"))
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await read_file(executor, "/workspace/protected.txt")

        assert result["status"] == "error"
        assert "Access denied" in result["error"]

    @pytest.mark.asyncio
    async def test_read_file_truncates_long_content(self, mock_sandbox):
        """Test that long file content is truncated."""
        long_content = "X" * 20000
        mock_sandbox.read_file = AsyncMock(return_value=long_content)
        executor = SandboxToolExecutor(sandbox=mock_sandbox, max_output_chars=100)

        result = await read_file(executor, "/workspace/bigfile.txt")

        assert result["status"] == "success"
        assert len(result["content"]) < 20000
        assert "truncated" in result["content"]

    @pytest.mark.asyncio
    async def test_read_file_path_traversal_blocked(self, mock_sandbox):
        """Test that path traversal attempts are blocked."""
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await read_file(executor, "/etc/passwd")

        assert result["status"] == "error"
        assert "outside allowed directories" in result["error"]

    @pytest.mark.asyncio
    async def test_read_file_workspace_subdirectories_allowed(self, mock_sandbox):
        """Test that workspace subdirectories are allowed."""
        mock_sandbox.read_file = AsyncMock(return_value="content")
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await read_file(executor, "/workspace/input/data.txt")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_read_file_empty_content(self, mock_sandbox):
        """Test reading an empty file."""
        mock_sandbox.read_file = AsyncMock(return_value="")
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await read_file(executor, "/workspace/empty.txt")

        assert result["status"] == "success"
        assert result["content"] == ""


class TestFileWriteTool:
    """Tests for file write tool."""

    @pytest.mark.asyncio
    async def test_write_file_success(self, mock_sandbox):
        """Test successful file write."""
        mock_sandbox.write_file = AsyncMock()
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await write_file(executor, "/workspace/output.txt", "Hello World")

        assert result["status"] == "success"
        assert result["path"] == "/workspace/output.txt"
        assert result["size"] == 11

        mock_sandbox.write_file.assert_called_once_with("/workspace/output.txt", "Hello World")

    @pytest.mark.asyncio
    async def test_write_file_error(self, mock_sandbox):
        """Test file write error handling."""
        mock_sandbox.write_file = AsyncMock(side_effect=PermissionError("Cannot write to directory"))
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await write_file(executor, "/workspace/readonly/file.txt", "content")

        assert result["status"] == "error"
        assert "Cannot write" in result["error"]

    @pytest.mark.asyncio
    async def test_write_file_path_traversal_blocked(self, mock_sandbox):
        """Test that path traversal attempts are blocked."""
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await write_file(executor, "/etc/passwd", "content")

        assert result["status"] == "error"
        assert "outside allowed directories" in result["error"]

    @pytest.mark.asyncio
    async def test_write_file_empty_content(self, mock_sandbox):
        """Test writing empty content."""
        mock_sandbox.write_file = AsyncMock()
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await write_file(executor, "/workspace/empty.txt", "")

        assert result["status"] == "success"
        assert result["size"] == 0

    @pytest.mark.asyncio
    async def test_write_file_large_content(self, mock_sandbox):
        """Test writing large content."""
        mock_sandbox.write_file = AsyncMock()
        executor = SandboxToolExecutor(sandbox=mock_sandbox)
        large_content = "X" * 100000

        result = await write_file(executor, "/workspace/large.txt", large_content)

        assert result["status"] == "success"
        assert result["size"] == 100000

    @pytest.mark.asyncio
    async def test_write_file_output_directory_allowed(self, mock_sandbox):
        """Test writing to output directory."""
        mock_sandbox.write_file = AsyncMock()
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await write_file(executor, "/workspace/output/result.json", '{"key": "value"}')

        assert result["status"] == "success"
