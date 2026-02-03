# SPDX-FileCopyrightText: Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

"""Workflow output exporter - extracts FailurePackets from workflow_output.json."""

import json
import logging
from pathlib import Path

from nat_sandbox_agent.analysis.models import EvalResult
from nat_sandbox_agent.analysis.models import FailurePacket
from nat_sandbox_agent.analysis.models import SpanSummary

logger = logging.getLogger(__name__)

# Maximum length for summary fields
MAX_SUMMARY_LENGTH = 500

def truncate(text: str, max_length: int = MAX_SUMMARY_LENGTH) -> str:
    """Truncate text to max_length, adding ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."

class WorkflowExporter:
    """Extract FailurePackets from workflow_output.json for failure analysis."""

    def load_from_workflow_output(
        self,
        workflow_output_path: Path,
    ) -> list[FailurePacket]:
        """Load failure packets from workflow_output.json.

        Args:
            workflow_output_path: Path to workflow_output.json file.

        Returns:
            List of FailurePackets for failed cases only.
        """
        with open(workflow_output_path) as f:
            data = json.load(f)

        packets = []
        for task in data:
            task_id = task.get("task_id", "")
            question = task.get("Question", "")
            expected = task.get("Final answer", "")
            actual = task.get("generated_answer", "")

            # Determine if this is a failure (simple string comparison for now)
            is_failure = self._normalize_answer(expected) != self._normalize_answer(actual)

            if not is_failure:
                continue

            # Extract spans from intermediate_steps
            spans = self._extract_spans(task.get("intermediate_steps", []))

            # Extract system prompt from first LLM call if available
            system_prompt = self._extract_system_prompt(task.get("intermediate_steps", []))

            # Create EvalResult
            eval_result = EvalResult(
                passed=False,
                reason=f"Expected '{expected}', got '{actual}'",
                evaluator="string_match",
            )

            packet = FailurePacket(
                task_id=task_id,
                user_request=question,
                system_prompt=system_prompt,
                expected_output=expected,
                actual_output=actual,
                eval_result=eval_result,
                spans=spans,
            )

            packets.append(packet)

        logger.info(
            f"Loaded {len(packets)} failure packets from {workflow_output_path} "
            f"(out of {len(data)} total tasks)"
        )

        return packets

    def _normalize_answer(self, answer: str) -> str:
        """Normalize answer for comparison."""
        if not answer:
            return ""
        return answer.strip().lower()

    def _extract_spans(self, intermediate_steps: list[dict]) -> list[SpanSummary]:
        """Extract SpanSummary objects from intermediate_steps."""
        spans = []

        for i, step in enumerate(intermediate_steps):
            payload = step.get("payload", {})
            event_type = payload.get("event_type", "")
            data = payload.get("data", {})
            metadata = payload.get("metadata", {})
            usage_info = payload.get("usage_info", {})

            span_id = payload.get("UUID", str(i))
            name = payload.get("name", "unknown")
            start_time = payload.get("span_event_timestamp")

            # Determine span type and status
            if event_type == "LLM_END":
                span = self._create_llm_span(span_id, name, data, metadata, usage_info, start_time)
            elif event_type == "TOOL_END":
                span = self._create_tool_span(span_id, name, data, metadata, start_time)
            elif event_type == "RETRIEVER_END":
                span = self._create_retriever_span(span_id, name, data, metadata, start_time)
            else:
                # Generic span
                span = SpanSummary(
                    span_id=span_id,
                    span_type="chain",
                    name=name,
                    status="OK",
                    duration_ms=0,
                    start_time=start_time,
                )

            spans.append(span)

        return spans

    def _create_llm_span(
        self,
        span_id: str,
        name: str,
        data: dict,
        metadata: dict,
        usage_info: dict,
        start_time: float | None,
    ) -> SpanSummary:
        """Create SpanSummary for LLM event."""
        token_usage = usage_info.get("token_usage", {})

        # Extract input/output
        input_text = str(data.get("input", ""))
        output_text = str(data.get("output", ""))

        return SpanSummary(
            span_id=span_id,
            span_type="llm",
            name=name,
            status="OK",
            duration_ms=0,
            start_time=start_time,
            model=name,
            prompt_tokens=token_usage.get("prompt_tokens"),
            completion_tokens=token_usage.get("completion_tokens"),
            input_summary=truncate(input_text),
            output_summary=truncate(output_text),
        )

    def _create_tool_span(
        self,
        span_id: str,
        name: str,
        data: dict,
        metadata: dict,
        start_time: float | None,
    ) -> SpanSummary:
        """Create SpanSummary for Tool event."""
        # Parse tool input
        tool_input = data.get("input", "")
        tool_args = {}
        if isinstance(tool_input, str):
            try:
                # Try to parse as Python dict literal
                import ast

                tool_args = ast.literal_eval(tool_input)
            except (ValueError, SyntaxError):
                tool_args = {"raw_input": tool_input}
        elif isinstance(tool_input, dict):
            tool_args = tool_input

        # Extract tool output
        tool_output = data.get("output", {})
        if isinstance(tool_output, dict):
            content = tool_output.get("content", str(tool_output))
        else:
            content = str(tool_output)

        # Check for errors - use more sophisticated detection
        error_message = None
        span_status = "OK"

        # First check the explicit status field from tool output
        if isinstance(tool_output, dict):
            output_status = tool_output.get("status", "").lower()
            if output_status in ("error", "failure", "failed"):
                span_status = "ERROR"
                error_content = tool_output.get("error", tool_output.get("message", str(tool_output)))
                error_message = truncate(str(error_content))

        # If status not determined from dict, check string content for error patterns
        # Only check if content looks like an error message (short and starts with error indicators)
        if span_status == "OK" and isinstance(content, str):
            content_lower = content.lower().strip()
            # Only check for error patterns if content is relatively short (likely an error message)
            # or if the content starts with a JSON that indicates error
            if len(content) < 2000 or content_lower.startswith('{"status":') or content_lower.startswith("error"):
                error_patterns = [
                    '"status": "error"',
                    '"status":"error"',
                    '"error":',  # JSON error field
                    "traceback (most recent call last)",
                    "exception: ",
                    "error: ",  # With space to avoid matching "error:" in URLs
                ]
                for pattern in error_patterns:
                    if pattern in content_lower:
                        span_status = "ERROR"
                        error_message = truncate(content)
                        break

        return SpanSummary(
            span_id=span_id,
            span_type="tool",
            name=name,
            status=span_status,
            duration_ms=0,
            start_time=start_time,
            tool_name=name,
            tool_args=tool_args,
            tool_result_summary=truncate(content if isinstance(content, str) else str(content)),
            error_message=error_message,
        )

    def _create_retriever_span(
        self,
        span_id: str,
        name: str,
        data: dict,
        metadata: dict,
        start_time: float | None,
    ) -> SpanSummary:
        """Create SpanSummary for Retriever event."""
        output = data.get("output", [])
        docs_returned = len(output) if isinstance(output, list) else 0

        return SpanSummary(
            span_id=span_id,
            span_type="retriever",
            name=name,
            status="OK" if docs_returned > 0 else "ERROR",
            duration_ms=0,
            start_time=start_time,
            docs_returned=docs_returned,
        )

    def _extract_system_prompt(self, intermediate_steps: list[dict]) -> str:
        """Extract system prompt from intermediate steps if available."""
        for step in intermediate_steps:
            payload = step.get("payload", {})
            metadata = payload.get("metadata", {})
            chat_inputs = metadata.get("chat_inputs")

            if chat_inputs and isinstance(chat_inputs, dict):
                messages = chat_inputs.get("messages", [])
                for msg in messages:
                    if isinstance(msg, dict) and msg.get("role") == "system":
                        return msg.get("content", "")

        return ""

    def save_packets(self, packets: list[FailurePacket], output_path: Path) -> None:
        """Save failure packets to JSONL file.

        Args:
            packets: List of FailurePacket objects.
            output_path: Output file path (.jsonl).
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            for packet in packets:
                f.write(packet.model_dump_json() + "\n")

        logger.info(f"Saved {len(packets)} failure packets to {output_path}")

    def load_packets(self, input_path: Path) -> list[FailurePacket]:
        """Load failure packets from JSONL file.

        Args:
            input_path: Input file path (.jsonl).

        Returns:
            List of FailurePacket objects.
        """
        packets = []
        with open(input_path) as f:
            for line in f:
                if line.strip():
                    packet = FailurePacket.model_validate_json(line)
                    packets.append(packet)

        logger.info(f"Loaded {len(packets)} failure packets from {input_path}")
        return packets
