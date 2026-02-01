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
"""Tests for web browse tool."""

import json
from unittest.mock import AsyncMock

import pytest

from nat.sandbox import CommandResult
from nat.sandbox.tools import SandboxToolExecutor
from nat.sandbox.tools import web_browse


class TestWebBrowseTool:
    """Tests for web browse tool."""

    @pytest.mark.asyncio
    async def test_web_browse_success(self, mock_sandbox):
        """Test successful web browse."""
        mock_result = json.dumps(
            {
                "status": "success",
                "url": "https://example.com",
                "title": "Example Domain",
                "content": "This is example content.",
            }
        )
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout=mock_result, stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await web_browse(executor, "https://example.com")

        assert result["status"] == "success"
        assert result["title"] == "Example Domain"
        assert "example content" in result["content"]
        # Verify script was written
        mock_sandbox.write_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_web_browse_with_selector(self, mock_sandbox):
        """Test web browse with CSS selector."""
        mock_result = json.dumps(
            {
                "status": "success",
                "url": "https://example.com",
                "title": "Example",
                "content": "Selected content only",
            }
        )
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout=mock_result, stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await web_browse(executor, "https://example.com", selector="article")

        assert result["status"] == "success"
        # Check that selector was included in generated script
        write_call = mock_sandbox.write_file.call_args
        script_content = write_call[0][1]
        assert "article" in script_content

    @pytest.mark.asyncio
    async def test_web_browse_error(self, mock_sandbox):
        """Test web browse error handling."""
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=1, stdout="", stderr="Network error")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await web_browse(executor, "https://invalid-url.test")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_web_browse_playwright_not_installed(self, mock_sandbox):
        """Test error when Playwright is not installed in sandbox."""
        mock_result = json.dumps(
            {
                "status": "error",
                "error": "Playwright not installed. Run: pip install playwright && playwright install chromium",
            }
        )
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout=mock_result, stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await web_browse(executor, "https://example.com")

        assert result["status"] == "error"
        assert "Playwright" in result["error"]

    @pytest.mark.asyncio
    async def test_web_browse_invalid_json_response(self, mock_sandbox):
        """Test handling of invalid JSON response from script."""
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout="not valid json", stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        result = await web_browse(executor, "https://example.com")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_web_browse_script_path(self, mock_sandbox):
        """Test that browser script is written to correct path."""
        mock_result = json.dumps({"status": "success", "url": "", "title": "", "content": ""})
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout=mock_result, stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        await web_browse(executor, "https://example.com")

        write_call = mock_sandbox.write_file.call_args
        script_path = write_call[0][0]
        assert script_path == "/workspace/temp/_browser_script.py"

    @pytest.mark.asyncio
    async def test_web_browse_url_escaping(self, mock_sandbox):
        """Test that URL is properly escaped in generated script."""
        mock_result = json.dumps({"status": "success", "url": "", "title": "", "content": ""})
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout=mock_result, stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        # URL with special characters
        await web_browse(executor, 'https://example.com/search?q="test"&foo=bar')

        write_call = mock_sandbox.write_file.call_args
        script_content = write_call[0][1]
        # URL should be JSON-encoded (escaped)
        assert '\\"test\\"' in script_content or "\\u0022" in script_content

    @pytest.mark.asyncio
    async def test_web_browse_selector_escaping(self, mock_sandbox):
        """Test that CSS selector is properly escaped."""
        mock_result = json.dumps({"status": "success", "url": "", "title": "", "content": ""})
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout=mock_result, stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        # Selector with quotes
        await web_browse(executor, "https://example.com", selector='div[data-id="test"]')

        write_call = mock_sandbox.write_file.call_args
        script_content = write_call[0][1]
        # Selector should be escaped
        assert "data-id" in script_content

    @pytest.mark.asyncio
    async def test_web_browse_timeout(self, mock_sandbox):
        """Test that web browse uses 60 second timeout."""
        mock_result = json.dumps({"status": "success", "url": "", "title": "", "content": ""})
        mock_sandbox.write_file = AsyncMock()
        mock_sandbox.run_command = AsyncMock(
            return_value=CommandResult(exit_code=0, stdout=mock_result, stderr="")
        )
        executor = SandboxToolExecutor(sandbox=mock_sandbox)

        await web_browse(executor, "https://example.com")

        run_call = mock_sandbox.run_command.call_args
        assert run_call[1]["timeout"] == 60
