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

"""Registration module for sandbox tools function group."""

from nat.builder.builder import Builder
from nat.builder.function import FunctionGroup
from nat.cli.register_workflow import register_function_group
from nat.sandbox.config import WORKSPACE_ROOT
from nat.sandbox.tools.config import SandboxToolsConfig
from nat.sandbox.tools.execution import PythonInput
from nat.sandbox.tools.execution import ShellInput
from nat.sandbox.tools.execution import execute_python
from nat.sandbox.tools.execution import execute_shell
from nat.sandbox.tools.executor import SandboxToolExecutor
from nat.sandbox.tools.file_ops import FileReadInput
from nat.sandbox.tools.file_ops import FileWriteInput
from nat.sandbox.tools.file_ops import read_file
from nat.sandbox.tools.file_ops import write_file
from nat.sandbox.tools.browser import WebBrowseInput
from nat.sandbox.tools.browser import web_browse


@register_function_group(config_type=SandboxToolsConfig)
async def sandbox_tools(config: SandboxToolsConfig, builder: Builder):
    """Register the sandbox_tools function group.

    Provides shell, python, file_read, file_write, and web_browse tools that
    execute inside a sandbox environment.

    Args:
        config: Sandbox tools configuration.
        builder: The workflow builder instance.

    Yields:
        FunctionGroup: The sandbox tools function group.
    """
    # Get the sandbox instance from the builder
    sandbox = await builder.get_sandbox(config.sandbox_name)

    # Create the executor
    executor = SandboxToolExecutor(
        sandbox=sandbox,
        max_output_chars=config.max_output_chars,
        default_timeout=config.default_timeout,
    )

    # Define all available tools
    all_tool_names = {"shell", "python", "file_read", "file_write", "web_browse"}
    # Default tools (all tools enabled by default)
    default_tool_names = {"shell", "python", "file_read", "file_write", "web_browse"}

    # Determine which tools to include
    if config.include_tools is not None:
        # Validate tool names
        unknown_tools = set(config.include_tools) - all_tool_names
        if unknown_tools:
            raise ValueError(
                f"Unknown tool names: {unknown_tools}. "
                f"Available tools: {list(all_tool_names)}"
            )
        include_tools = set(config.include_tools)
    else:
        include_tools = default_tool_names

    # Create the function group
    group = FunctionGroup(config=config)

    # Add shell tool
    if "shell" in include_tools:
        async def shell_fn(command: str, working_dir: str = WORKSPACE_ROOT) -> dict:
            return await execute_shell(executor, command, working_dir)

        group.add_function(
            "shell",
            shell_fn,
            description=(
                "Execute bash/shell commands for SYSTEM OPERATIONS: "
                "file management (ls, cp, mv, rm, mkdir, chmod), "
                "package installation (pip install, apt-get), "
                "downloads (curl, wget), "
                "process management (ps, kill), "
                "git operations. "
                "Do NOT use for data processing - use python instead."
            ),
            input_schema=ShellInput,
        )

    # Add python tool
    if "python" in include_tools:
        async def python_fn(code: str) -> dict:
            return await execute_python(executor, code)

        group.add_function(
            "python",
            python_fn,
            description=(
                "Execute Python code for DATA PROCESSING and COMPUTATION: "
                "data analysis (pandas, numpy), "
                "calculations and math, "
                "file parsing (JSON, CSV, XML, Excel), "
                "API calls (requests), "
                "text processing (regex), "
                "image processing (PIL, OpenCV). "
                "Generated files should be saved to /workspace/output/. "
                "Do NOT use for simple system commands - use shell instead."
            ),
            input_schema=PythonInput,
        )

    # Add file_read tool
    if "file_read" in include_tools:
        async def file_read_fn(path: str) -> dict:
            return await read_file(executor, path)

        group.add_function(
            "file_read",
            file_read_fn,
            description=(
                "Read the contents of a file from the sandbox. "
                "Returns the file content as text."
            ),
            input_schema=FileReadInput,
        )

    # Add file_write tool
    if "file_write" in include_tools:
        async def file_write_fn(path: str, content: str) -> dict:
            return await write_file(executor, path, content)

        group.add_function(
            "file_write",
            file_write_fn,
            description=(
                "Write content to a file in the sandbox. "
                "Parent directories are created automatically if needed."
            ),
            input_schema=FileWriteInput,
        )

    # Add web_browse tool (optional, requires Playwright in sandbox)
    if "web_browse" in include_tools:
        async def web_browse_fn(url: str, selector: str | None = None) -> dict:
            return await web_browse(executor, url, selector)

        group.add_function(
            "web_browse",
            web_browse_fn,
            description=(
                "Browse a webpage and extract its content. "
                "Returns page title and text content (or selected element content). "
                "Use 'selector' parameter to target specific CSS elements. "
                "Use this after web_search to get detailed information from URLs."
            ),
            input_schema=WebBrowseInput,
        )

    yield group
