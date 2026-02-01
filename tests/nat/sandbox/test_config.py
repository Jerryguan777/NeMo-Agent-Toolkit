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
"""Tests for sandbox configuration constants."""

from nat.sandbox import DEFAULT_SCRIPT_PATH
from nat.sandbox import WORKSPACE_DOWNLOADS
from nat.sandbox import WORKSPACE_INIT_COMMAND
from nat.sandbox import WORKSPACE_INPUT
from nat.sandbox import WORKSPACE_OUTPUT
from nat.sandbox import WORKSPACE_ROOT
from nat.sandbox import WORKSPACE_TEMP


class TestWorkspaceConstants:
    """Tests for workspace path constants."""

    def test_workspace_root(self):
        """Test WORKSPACE_ROOT is /workspace."""
        assert WORKSPACE_ROOT == "/workspace"

    def test_workspace_input(self):
        """Test WORKSPACE_INPUT is under workspace root."""
        assert WORKSPACE_INPUT == "/workspace/input"
        assert WORKSPACE_INPUT.startswith(WORKSPACE_ROOT)

    def test_workspace_output(self):
        """Test WORKSPACE_OUTPUT is under workspace root."""
        assert WORKSPACE_OUTPUT == "/workspace/output"
        assert WORKSPACE_OUTPUT.startswith(WORKSPACE_ROOT)

    def test_workspace_temp(self):
        """Test WORKSPACE_TEMP is under workspace root."""
        assert WORKSPACE_TEMP == "/workspace/temp"
        assert WORKSPACE_TEMP.startswith(WORKSPACE_ROOT)

    def test_workspace_downloads(self):
        """Test WORKSPACE_DOWNLOADS is under workspace root."""
        assert WORKSPACE_DOWNLOADS == "/workspace/downloads"
        assert WORKSPACE_DOWNLOADS.startswith(WORKSPACE_ROOT)

    def test_default_script_path(self):
        """Test DEFAULT_SCRIPT_PATH is under workspace temp."""
        assert DEFAULT_SCRIPT_PATH == "/workspace/temp/_script.py"
        assert DEFAULT_SCRIPT_PATH.startswith(WORKSPACE_TEMP)

    def test_workspace_init_command_creates_directories(self):
        """Test WORKSPACE_INIT_COMMAND creates all required directories."""
        assert "mkdir" in WORKSPACE_INIT_COMMAND
        assert WORKSPACE_INPUT in WORKSPACE_INIT_COMMAND
        assert WORKSPACE_OUTPUT in WORKSPACE_INIT_COMMAND
        assert WORKSPACE_TEMP in WORKSPACE_INIT_COMMAND
        assert WORKSPACE_DOWNLOADS in WORKSPACE_INIT_COMMAND
