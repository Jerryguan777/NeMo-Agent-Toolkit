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

"""Host-side image analysis tool using a vision model.

This tool runs on the host machine (not in the sandbox) for:
- Better security (API key not exposed to sandbox)
- Lower latency (no Docker exec overhead for API calls)

It reads image bytes from the sandbox via sandbox.read_file_bytes(),
encodes them as base64, and sends them to the OpenAI vision API.
"""

import base64
import logging
import os
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel
from pydantic import Field

from nat_sandbox_agent.sandbox.base import BaseSandbox
from nat_sandbox_agent.tools.common import DEFAULT_MAX_OUTPUT_CHARS
from nat_sandbox_agent.tools.common import truncate_output

logger = logging.getLogger(__name__)

# Supported image MIME types
SUPPORTED_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


class ImageAnalysisInput(BaseModel):
    """Input schema for image analysis."""

    image_path: str = Field(
        description=(
            "Path to the image file inside the sandbox "
            "(e.g., /workspace/input/image.png)."
        ),
    )
    instruction: str = Field(
        description=(
            "What to analyze in the image. Be specific about what information "
            "to extract (e.g., 'Read all text in this image', "
            "'List all numbers and their colors', 'Describe the chart data')."
        ),
    )


class HostVisionTool:
    """Image analysis tool that runs on host using a vision model.

    Reads images from the sandbox and sends them to the OpenAI vision API
    for analysis. The main agent retains reasoning control; the vision model
    is only used for "seeing" images.
    """

    def __init__(
        self,
        sandbox: BaseSandbox,
        api_key: str | None = None,
        model: str = "gpt-4o",
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ):
        """Initialize the vision tool.

        Args:
            sandbox: Sandbox instance for reading image files.
            api_key: OpenAI API key. If None, uses OPENAI_API_KEY env var.
            model: Vision model to use (default: gpt-4o).
            max_output_chars: Maximum characters in the output.
        """
        self._sandbox = sandbox
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._model = model
        self._max_output_chars = max_output_chars
        self._client = None

    def _get_client(self):
        """Lazily initialize OpenAI client."""
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "OPENAI_API_KEY not set. Please set the environment variable "
                    "or pass api_key to the tool."
                )
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
        return self._client

    async def analyze(
        self,
        image_path: str,
        instruction: str,
    ) -> dict[str, Any]:
        """Analyze an image using the vision model.

        Args:
            image_path: Path to the image file inside the sandbox.
            instruction: What to analyze in the image.

        Returns:
            Dict with status and analysis text.
        """
        logger.info(f"Analyzing image: {image_path}")

        try:
            # Read image bytes from sandbox
            image_bytes = await self._sandbox.read_file_bytes(image_path)

            # Detect MIME type from extension
            ext = os.path.splitext(image_path)[1].lower()
            mime_type = SUPPORTED_MIME_TYPES.get(ext, "image/png")

            # Base64 encode
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:{mime_type};base64,{image_b64}"

            # Call vision API
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": instruction},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                        ],
                    }
                ],
                max_tokens=4096,
            )

            analysis = response.choices[0].message.content
            analysis = truncate_output(analysis, self._max_output_chars)

            logger.info(f"Image analysis complete: {len(analysis)} chars")

            return {
                "status": "success",
                "analysis": analysis,
            }

        except FileNotFoundError:
            return {
                "status": "error",
                "error": f"Image file not found: {image_path}",
            }
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            return {
                "status": "error",
                "error": str(e),
            }


def create_vision_tool(
    sandbox: BaseSandbox,
    api_key: str | None = None,
    model: str = "gpt-4o",
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
) -> StructuredTool:
    """Create the image analysis tool.

    Args:
        sandbox: Sandbox instance for reading image files.
        api_key: OpenAI API key. If None, uses OPENAI_API_KEY env var.
        model: Vision model to use.
        max_output_chars: Maximum characters in the output.

    Returns:
        LangChain StructuredTool instance.
    """
    tool = HostVisionTool(
        sandbox=sandbox,
        api_key=api_key,
        model=model,
        max_output_chars=max_output_chars,
    )

    return StructuredTool.from_function(
        coroutine=tool.analyze,
        name="analyze_image",
        description=(
            "Analyze an image using a vision model. Reads the image from the sandbox "
            "and returns a text description based on your instructions. Use this for: "
            "reading text/numbers from images, identifying objects, reading charts/tables, "
            "understanding visual content that OCR cannot handle."
        ),
        args_schema=ImageAnalysisInput,
    )
