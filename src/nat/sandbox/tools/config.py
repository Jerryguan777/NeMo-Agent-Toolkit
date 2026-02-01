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

"""Configuration for sandbox tools function group."""

from pydantic import Field

from nat.data_models.component_ref import SandboxRef
from nat.data_models.function import FunctionGroupBaseConfig


class SandboxToolsConfig(FunctionGroupBaseConfig, name="sandbox_tools"):
    """Configuration for sandbox tools function group.

    Provides shell, python, file_read, and file_write tools that execute
    inside a sandbox environment.
    """

    sandbox_name: SandboxRef = Field(
        description="Name of the sandbox instance from the workflow configuration.",
    )
    max_output_chars: int = Field(
        default=16000,
        description="Maximum characters for tool output truncation (16000 chars ≈ 4000 tokens).",
    )
    default_timeout: float = Field(
        default=120,
        description="Default timeout for operations in seconds.",
    )
    include_tools: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of tool names to include. "
            "Available: shell, python, file_read, file_write, web_browse. "
            "If None, includes shell, python, file_read, file_write (not web_browse). "
            "Note: web_browse requires Playwright installed in the sandbox image."
        ),
    )
