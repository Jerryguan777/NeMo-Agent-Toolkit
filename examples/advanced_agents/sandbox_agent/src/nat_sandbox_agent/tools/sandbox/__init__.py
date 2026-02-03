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

"""Sandbox-side tools that run inside the Docker sandbox.

These tools require sandbox isolation:
- shell: Execute bash commands
- python: Execute Python code
- file_read: Read files
- file_write: Write files
- web_browse: Browse web pages with Playwright
"""


from langchain_core.tools import StructuredTool

from nat_sandbox_agent.sandbox.base import BaseSandbox
from nat_sandbox_agent.tools.common import DEFAULT_MAX_OUTPUT_CHARS
from nat_sandbox_agent.tools.sandbox.browser import create_web_browse_tool
from nat_sandbox_agent.tools.sandbox.execution import create_python_tool
from nat_sandbox_agent.tools.sandbox.execution import create_shell_tool
from nat_sandbox_agent.tools.sandbox.executor import SandboxToolExecutor
from nat_sandbox_agent.tools.sandbox.file_ops import create_file_read_tool
from nat_sandbox_agent.tools.sandbox.file_ops import create_file_write_tool
from nat_sandbox_agent.tools.sandbox.structured_extractor import (
    create_structured_extractor_tools,
    StructuredDataExtractor,
)
from nat_sandbox_agent.tools.sandbox.calculation_verifier import (
    create_calculation_verifier_tools,
    CalculationVerifier,
)


def create_sandbox_tools(
    sandbox: BaseSandbox,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    include_tools: list[str] | None = None,
    include_advanced_tools: bool = False,
) -> list[StructuredTool]:
    """Create all sandbox-side tools.

    Args:
        sandbox: The sandbox instance to bind tools to.
        max_output_chars: Maximum characters for tool output truncation.
        include_tools: Optional list of tool names to include.
            If None, all tools are included.
        include_advanced_tools: Whether to include advanced tools
            (structured extractor, calculation verifier).

    Returns:
        List of sandbox tools.
    """
    executor = SandboxToolExecutor(
        sandbox=sandbox,
        max_output_chars=max_output_chars,
    )

    all_tools = {
        "shell": create_shell_tool(executor),
        "python": create_python_tool(executor),
        "file_read": create_file_read_tool(executor),
        "file_write": create_file_write_tool(executor),
        "web_browse": create_web_browse_tool(executor),
    }

    # Add advanced tools if requested
    if include_advanced_tools:
        extractor_tools = create_structured_extractor_tools(executor)
        for tool in extractor_tools:
            all_tools[tool.name] = tool

        verifier_tools = create_calculation_verifier_tools(executor)
        for tool in verifier_tools:
            all_tools[tool.name] = tool

    if include_tools:
        return [all_tools[name] for name in include_tools if name in all_tools]

    return list(all_tools.values())

__all__ = [
    "create_sandbox_tools",
    "SandboxToolExecutor",
    "create_shell_tool",
    "create_python_tool",
    "create_file_read_tool",
    "create_file_write_tool",
    "create_web_browse_tool",
    # Advanced tools
    "create_structured_extractor_tools",
    "StructuredDataExtractor",
    "create_calculation_verifier_tools",
    "CalculationVerifier",
]
