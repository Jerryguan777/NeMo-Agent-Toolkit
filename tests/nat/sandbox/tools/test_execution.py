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
"""Tests for shell and Python execution tools."""

from unittest.mock import AsyncMock

import pytest

from nat.sandbox import CommandResult
from nat.sandbox.tools import SandboxToolExecutor
from nat.sandbox.tools.execution import execute_python
from nat.sandbox.tools.execution import execute_shell


class TestShellTool:
    """Tests for shell command execution tool."""

    @pytest.mark.asyncio
    async def test_execute_shell_success(self, mock_sandbox):
        """Test successful shell command execution."""
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout="file1.txt\nfile2.py", stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await execute_shell(executor, "ls -la", "/workspace")

        assert result["status"] == "success"
        assert "file1.txt" in result["stdout"]
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_execute_shell_failure(self, mock_sandbox):
        """Test shell command failure."""
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=1, stdout="", stderr="Command not found")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await execute_shell(executor, "invalid_command")

        assert result["status"] == "error"
        assert result["exit_code"] == 1
        assert "Command not found" in result["stderr"]

    @pytest.mark.asyncio
    async def test_execute_shell_respects_working_dir(self, mock_sandbox):
        """Test that working directory is passed correctly."""
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout="", stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        await execute_shell(executor, "pwd", working_dir="/custom/dir")

        mock_sandbox.run_command.assert_called_once()
        call_kwargs = mock_sandbox.run_command.call_args[1]
        assert call_kwargs["working_dir"] == "/custom/dir"

    @pytest.mark.asyncio
    async def test_execute_shell_truncates_output(self, mock_sandbox):
        """Test that long output is truncated."""
        long_output = "X" * 20000
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout=long_output, stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox, max_output_chars=100)

        result = await execute_shell(executor, "cat bigfile.txt")

        assert len(result["stdout"]) < 20000
        assert "truncated" in result["stdout"]

    @pytest.mark.asyncio
    async def test_execute_shell_uses_default_working_dir(self, mock_sandbox):
        """Test that default working directory is /workspace."""
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout="", stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        await execute_shell(executor, "ls")

        call_kwargs = mock_sandbox.run_command.call_args[1]
        assert call_kwargs["working_dir"] == "/workspace"


class TestPythonTool:
    """Tests for Python code execution tool."""

    @pytest.mark.asyncio
    async def test_execute_python_success(self, mock_sandbox):
        """Test successful Python code execution."""
        mock_sandbox.write_file = AsyncMock()
        # First call is python execution, second is ls for generated files
        mock_sandbox.run_command = AsyncMock(
            side_effect=[
                CommandResult(exit_code=0, stdout="42", stderr=""),
                CommandResult(exit_code=0, stdout="result.txt\n", stderr=""),
            ]
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await execute_python(executor, "print(6 * 7)")

        assert result["status"] == "success"
        assert "42" in result["stdout"]
        assert "generated_files" in result

    @pytest.mark.asyncio
    async def test_execute_python_writes_script(self, mock_sandbox):
        """Test that Python code is written to script file."""
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            side_effect=[
                CommandResult(exit_code=0, stdout="", stderr=""),
                CommandResult(exit_code=0, stdout="", stderr=""),
            ]
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        code = "print('hello')"
        await execute_python(executor, code)

        mock_sandbox.write_file.assert_called_once()
        call_args = mock_sandbox.write_file.call_args
        assert call_args[0][0] == "/workspace/temp/_script.py"
        assert call_args[0][1] == code

    @pytest.mark.asyncio
    async def test_execute_python_error(self, mock_sandbox):
        """Test Python execution with error."""
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            side_effect=[
                CommandResult(
                    exit_code=1,
                    stdout="",
                    stderr="NameError: name 'undefined_var' is not defined",
                ),
                CommandResult(exit_code=0, stdout="", stderr=""),
            ]
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await execute_python(executor, "print(undefined_var)")

        assert result["status"] == "error"
        assert "NameError" in result["stderr"]

    @pytest.mark.asyncio
    async def test_execute_python_write_file_error(self, mock_sandbox):
        """Test handling of write file errors."""
        mock_sandbox.write_file = AsyncMock(side_effect=Exception("Disk full"))
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await execute_python(executor, "print('hello')")

        assert result["status"] == "error"
        assert "Disk full" in result["stderr"]

    @pytest.mark.asyncio
    async def test_execute_python_truncates_output(self, mock_sandbox):
        """Test that long Python output is truncated."""
        long_output = "X" * 20000
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            side_effect=[
                CommandResult(exit_code=0, stdout=long_output, stderr=""),
                CommandResult(exit_code=0, stdout="", stderr=""),
            ]
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox, max_output_chars=100)

        result = await execute_python(executor, "print('x' * 20000)")

        assert len(result["stdout"]) < 20000
        assert "truncated" in result["stdout"]
