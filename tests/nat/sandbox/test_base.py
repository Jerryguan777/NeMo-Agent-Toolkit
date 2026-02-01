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
"""Tests for sandbox interfaces (CommandResult, BaseSandbox)."""

from nat.sandbox import BaseSandbox
from nat.sandbox import CommandResult


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_property_true(self):
        """Test success property when exit code is 0."""
        result = CommandResult(exit_code=0, stdout="output", stderr="")
        assert result.success is True

    def test_success_property_false(self):
        """Test success property when exit code is non-zero."""
        result = CommandResult(exit_code=1, stdout="", stderr="error")
        assert result.success is False

    def test_success_property_negative_exit_code(self):
        """Test success property with negative exit code (e.g., timeout)."""
        result = CommandResult(exit_code=-1, stdout="", stderr="timeout")
        assert result.success is False

    def test_to_dict(self):
        """Test to_dict method."""
        result = CommandResult(exit_code=0, stdout="output", stderr="error")
        d = result.to_dict()

        assert d["exit_code"] == 0
        assert d["stdout"] == "output"
        assert d["stderr"] == "error"
        assert d["success"] is True

    def test_to_dict_failure(self):
        """Test to_dict method for failed command."""
        result = CommandResult(exit_code=127, stdout="", stderr="command not found")
        d = result.to_dict()

        assert d["exit_code"] == 127
        assert d["success"] is False

    def test_required_fields(self):
        """Test that CommandResult requires exit_code, stdout, and stderr."""
        # All fields are required
        result = CommandResult(exit_code=0, stdout="out", stderr="err")
        assert result.exit_code == 0
        assert result.stdout == "out"
        assert result.stderr == "err"


class TestBaseSandbox:
    """Tests for BaseSandbox abstract class."""

    def test_is_abstract(self):
        """Test that BaseSandbox cannot be instantiated directly."""
        import pytest

        with pytest.raises(TypeError, match="abstract"):
            BaseSandbox()

    def test_has_required_methods(self):
        """Test that BaseSandbox defines required abstract methods."""
        from abc import ABC
        import inspect

        assert issubclass(BaseSandbox, ABC)

        # Check abstract methods exist
        abstract_methods = {
            name
            for name, method in inspect.getmembers(BaseSandbox)
            if getattr(method, "__isabstractmethod__", False)
        }

        expected_methods = {"start", "cleanup", "run_command", "read_file", "write_file"}
        assert expected_methods == abstract_methods
