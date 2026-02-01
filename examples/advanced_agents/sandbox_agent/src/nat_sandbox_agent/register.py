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

"""Host-side tools registration for sandbox agent.

This module registers tools that run on the host (not in sandbox) for security.
Sandbox tools (shell, python, file_read, file_write, web_browse) are provided
by NAT core via `nat.sandbox.tools`.

Example YAML configuration:

    functions:
      # Core sandbox tools (from nat.sandbox.tools)
      sandbox_tools:
        _type: sandbox_tools
        sandbox_name: code_sandbox
        include_tools: [shell, python, file_read, file_write]

      # Host-side web search (from this module)
      web_search:
        _type: web_search
        max_results: 5
"""

import logging
import os
from typing import Any

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

logger = logging.getLogger(__name__)


class WebSearchConfig(FunctionBaseConfig, name="web_search"):
    """Configuration for web search tool.

    This tool runs on the host (not in sandbox) for security - API keys
    are not exposed to the sandbox environment.
    """

    api_key: str | None = Field(
        default=None,
        description="Tavily API key. If None, uses TAVILY_API_KEY env var.",
    )

    max_results: int = Field(
        default=5,
        description="Maximum number of search results to return.",
        ge=1,
        le=10,
    )


@register_function(config_type=WebSearchConfig)
async def web_search_tool(config: WebSearchConfig, builder: Builder):
    """Register web search tool (runs on host, not in sandbox).

    Uses Tavily API for high-quality search results optimized for AI agents.
    """
    api_key = config.api_key or os.environ.get("TAVILY_API_KEY")

    async def web_search(query: str, num_results: int = 5) -> dict[str, Any]:
        """Search the web using Tavily API (runs on host, not in sandbox). Returns titles, URLs, and snippets for search results. Use this to find information, research topics, or locate relevant URLs before using web_browse for details."""
        if not api_key:
            return {"status": "error", "error": "TAVILY_API_KEY not set"}

        try:
            from tavily import AsyncTavilyClient

            client = AsyncTavilyClient(api_key=api_key)
            response = await client.search(
                query=query,
                max_results=min(num_results, config.max_results),
                include_answer=True,
            )

            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                }
                for r in response.get("results", [])
            ]

            logger.info(f"Web search returned {len(results)} results")

            return {
                "status": "success",
                "results": results,
                "answer": response.get("answer"),
            }

        except Exception as e:
            logger.exception("Web search error")
            return {"status": "error", "error": str(e)}

    yield FunctionInfo.from_fn(
        web_search,
        description=(
            "Search the web using Tavily API (runs on host, not in sandbox). "
            "Returns titles, URLs, and snippets for search results. "
            "Use this to find information, research topics, or locate relevant URLs "
            "before using sandbox_tools__web_browse for details."
        ),
    )
