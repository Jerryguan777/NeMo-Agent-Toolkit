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

"""LLM-based triage for semantic failure analysis with extensibility."""

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from nat.analyze.models import FailureCategory, FailurePacket, TriageResult

logger = logging.getLogger(__name__)

# Built-in LLM categories
BUILTIN_LLM_CATEGORIES = [
    {
        "id": "task_understanding",
        "description": "Agent misunderstood the task requirements, constraints, or goals",
    },
    {
        "id": "planning_decomposition",
        "description": "Agent failed to break down the task properly, wrong order, missing steps",
    },
    {
        "id": "tool_selection",
        "description": "Agent chose the wrong tool or tried to guess instead of using available tools",
    },
    {
        "id": "evidence_utilization",
        "description": "Agent found relevant information but failed to use it correctly",
    },
    {
        "id": "reasoning_calculation",
        "description": "Agent made logical errors, calculation mistakes, or wrong inferences",
    },
    {
        "id": "state_memory",
        "description": "Agent lost track of context across steps or overwrote important state",
    },
    {
        "id": "policy_safety",
        "description": "Agent refused due to safety policy or generated harmful content",
    },
]

DEFAULT_TRIAGE_TEMPLATE = """You are an expert at analyzing AI agent failures. Analyze the following \
failed task and determine the root cause.

## Failure Categories (choose exactly ONE):

{categories}

## Task Information

**User Request:** {user_request}

**Expected Output:** {expected_output}

**Actual Output:** {actual_output}

**Evaluation Reason:** {eval_reason}

## Execution Trace

{spans_json}

## Your Analysis

Respond with a JSON object containing:
- "category": one of the category IDs listed above
- "confidence": your confidence level from 0.0 to 1.0
- "key_spans": list of span_ids that are critical turning points
- "evidence": brief explanation of why you chose this category
- "fix_suggestions": list of 1-3 actionable suggestions

Respond ONLY with the JSON object, no other text."""


class LLMTriage:
    """LLM-based triage for semantic failure analysis.

    Supports extensibility through:
    - Custom categories via YAML config or programmatic registration
    - Custom prompt templates
    - Pluggable LLM backends

    Example:
        ```python
        from nat.analyze import LLMTriage

        # Basic usage
        triage = LLMTriage(model="gpt-4o-mini")

        # With custom config
        triage = LLMTriage(
            model="gpt-4o-mini",
            config_path=Path("analyze_config.yaml"),
        )

        # Add custom category programmatically
        triage.add_category(
            "domain_knowledge",
            "Agent lacks specific domain expertise",
        )
        ```
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        config: dict[str, Any] | None = None,
        config_path: Path | None = None,
    ) -> None:
        """Initialize the LLM triage.

        Args:
            model: Model name to use for triage.
            api_key: Optional API key (uses env var if not provided).
            base_url: Optional base URL for API.
            config: Optional config dictionary.
            config_path: Optional path to YAML config file.
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self._client = None

        # Load config
        self.config = config or {}
        if config_path:
            self._load_config(config_path)

        # Custom categories from config
        self.custom_categories: list[dict] = self.config.get("custom_categories", [])
        self.custom_prompt_file: str | None = self.config.get("custom_prompt_file")

        # Register custom categories with FailureCategory
        for cat in self.custom_categories:
            FailureCategory.register_custom(cat["id"], cat.get("description", ""))

    def _load_config(self, path: Path) -> None:
        """Load configuration from YAML file."""
        with open(path) as f:
            full_config = yaml.safe_load(f) or {}
            self.config = full_config.get("llm_triage", {})

            # Also apply model config if present
            if "model" in self.config:
                self.model = self.config["model"]

    def add_category(
        self,
        category_id: str,
        description: str,
        examples: list[str] | None = None,
        fix_suggestions: list[str] | None = None,
    ) -> None:
        """Add a custom category programmatically.

        Args:
            category_id: Unique identifier for the category.
            description: Human-readable description.
            examples: Optional example failure scenarios.
            fix_suggestions: Optional fix suggestions.
        """
        cat = {
            "id": category_id,
            "description": description,
        }
        if examples:
            cat["examples"] = examples
        if fix_suggestions:
            cat["fix_suggestions"] = fix_suggestions

        self.custom_categories.append(cat)
        FailureCategory.register_custom(category_id, description)

    def _get_client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI

                kwargs = {}
                if self.api_key:
                    kwargs["api_key"] = self.api_key
                if self.base_url:
                    kwargs["base_url"] = self.base_url

                self._client = OpenAI(**kwargs)
            except ImportError:
                logger.error("OpenAI client not available. Install with: pip install openai")
                raise
        return self._client

    def _build_categories_text(self) -> str:
        """Build categories text for the prompt."""
        all_categories = BUILTIN_LLM_CATEGORIES + self.custom_categories

        lines = []
        for i, cat in enumerate(all_categories, 1):
            desc = cat["description"]
            examples = cat.get("examples", [])

            line = f'{i}. **{cat["id"]}** - {desc}'
            if examples:
                line += f'\n   Examples: {"; ".join(examples)}'
            lines.append(line)

        return "\n".join(lines)

    def _build_prompt(self, packet: FailurePacket) -> str:
        """Build the LLM prompt."""
        # Use custom template if provided
        if self.custom_prompt_file:
            with open(self.custom_prompt_file) as f:
                template = f.read()
        else:
            template = DEFAULT_TRIAGE_TEMPLATE

        categories_text = self._build_categories_text()
        spans_json = self._format_spans_json(packet)

        return template.format(
            categories=categories_text,
            user_request=packet.user_request,
            expected_output=packet.expected_output,
            actual_output=packet.actual_output,
            eval_reason=packet.eval_result.reason,
            spans_json=spans_json,
        )

    def _format_spans_json(self, packet: FailurePacket) -> str:
        """Format spans as JSON for the prompt."""
        spans_data = []
        for span in packet.spans:
            span_dict = {
                "span_id": span.span_id,
                "type": span.span_type,
                "name": span.name,
                "status": span.status,
            }

            if span.span_type == "llm":
                span_dict["model"] = span.model
                span_dict["input"] = span.input_summary
                span_dict["output"] = span.output_summary
                span_dict["tokens"] = {
                    "prompt": span.prompt_tokens,
                    "completion": span.completion_tokens,
                }
            elif span.span_type == "tool":
                span_dict["tool"] = span.tool_name
                span_dict["args"] = span.tool_args
                span_dict["result"] = span.tool_result_summary
                if span.error_message:
                    span_dict["error"] = span.error_message

            spans_data.append(span_dict)

        return json.dumps(spans_data, indent=2, ensure_ascii=False)

    def triage(self, packet: FailurePacket) -> TriageResult:
        """Perform LLM triage on a failure packet.

        Args:
            packet: The failure packet to analyze.

        Returns:
            TriageResult with category and analysis.
        """
        prompt = self._build_prompt(packet)

        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.get("temperature", 0.1),
                max_tokens=self.config.get("max_tokens", 1000),
            )

            content = response.choices[0].message.content.strip()
            return self._parse_response(content)

        except Exception as e:
            logger.error(f"LLM triage failed: {e}")
            return TriageResult(
                category=FailureCategory.UNKNOWN,
                confidence=0.0,
                evidence=f"LLM triage failed: {e}",
            )

    def _parse_response(self, content: str) -> TriageResult:
        """Parse LLM response into TriageResult."""
        try:
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content)

            category_str = data.get("category", "unknown")
            category = FailureCategory.get(category_str)

            return TriageResult(
                category=category,
                confidence=float(data.get("confidence", 0.5)),
                key_spans=data.get("key_spans", []),
                evidence=data.get("evidence", ""),
                fix_suggestions=data.get("fix_suggestions", []),
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return TriageResult(
                category=FailureCategory.UNKNOWN,
                confidence=0.0,
                evidence=f"Failed to parse response: {content[:200]}",
            )

    def triage_batch(self, packets: list[FailurePacket]) -> list[FailurePacket]:
        """Perform LLM triage on a batch of packets.

        Args:
            packets: List of failure packets to analyze.

        Returns:
            List of packets with classification filled in.
        """
        results = []

        for i, packet in enumerate(packets):
            logger.info(f"Triaging packet {i + 1}/{len(packets)}: {packet.task_id}")

            result = self.triage(packet)

            packet.failure_category = result.category
            packet.classification_source = "llm"
            packet.classification_confidence = result.confidence
            packet.root_cause_evidence = result.evidence
            packet.key_span_ids = result.key_spans
            packet.fix_suggestions = result.fix_suggestions

            results.append(packet)

        logger.info(f"LLM triage completed for {len(results)} packets")
        return results

    def get_all_categories(self) -> list[str]:
        """Get all category IDs (built-in + custom)."""
        all_cats = BUILTIN_LLM_CATEGORIES + self.custom_categories
        return [cat["id"] for cat in all_cats]
