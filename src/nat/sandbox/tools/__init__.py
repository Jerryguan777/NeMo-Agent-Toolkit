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

"""Sandbox tools module - provides shell, python, file operations, and browser tools."""

from nat.sandbox.tools.config import SandboxToolsConfig
from nat.sandbox.tools.executor import SandboxToolExecutor
from nat.sandbox.tools.executor import truncate_output

# Execution tools
from nat.sandbox.tools.execution import ShellInput
from nat.sandbox.tools.execution import PythonInput
from nat.sandbox.tools.execution import execute_shell
from nat.sandbox.tools.execution import execute_python

# File operation tools
from nat.sandbox.tools.file_ops import FileReadInput
from nat.sandbox.tools.file_ops import FileWriteInput
from nat.sandbox.tools.file_ops import read_file
from nat.sandbox.tools.file_ops import write_file

# Browser tool
from nat.sandbox.tools.browser import WebBrowseInput
from nat.sandbox.tools.browser import web_browse

__all__ = [
    # Config and executor
    "SandboxToolsConfig",
    "SandboxToolExecutor",
    "truncate_output",
    # Execution tools
    "ShellInput",
    "PythonInput",
    "execute_shell",
    "execute_python",
    # File operation tools
    "FileReadInput",
    "FileWriteInput",
    "read_file",
    "write_file",
    # Browser tool
    "WebBrowseInput",
    "web_browse",
]
