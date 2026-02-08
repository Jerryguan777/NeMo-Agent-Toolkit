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

"""Workflow output exporter - extracts TaskAnalysis objects from workflow_output.json."""

import ast
import json
import logging
from pathlib import Path
from typing import Any

from nat.analyze.models import StepDetail, TaskAnalysis

logger = logging.getLogger(__name__)

# Target token budget for compressed trajectory sent to LLM
COMPRESSED_TRAJECTORY_MAX_CHARS = 15000
STEP_INPUT_MAX_CHARS = 2000
STEP_OUTPUT_MAX_CHARS = 2000


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max_length, adding ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def load_from_workflow_output(
    workflow_output_path: Path,
    accuracy_output_path: Path | None = None,
) -> tuple[list[TaskAnalysis], int]:
    """Load failed task analyses from workflow_output.json.

    Args:
        workflow_output_path: Path to workflow_output.json file.
        accuracy_output_path: Optional path to accuracy_output.json for scores.

    Returns:
        Tuple of (list of TaskAnalysis for failed cases, total task count).
    """
    with open(workflow_output_path) as f:
        data = json.load(f)

    scores = {}
    if accuracy_output_path and accuracy_output_path.exists():
        with open(accuracy_output_path) as f:
            acc_data = json.load(f)
            for item in acc_data.get("eval_output_items", []):
                scores[str(item.get("id"))] = item.get("score", 0)

    analyses = []
    for task in data:
        task_id = str(task.get("task_id") or task.get("id", ""))
        question = task.get("Question") or task.get("question", "")
        expected = task.get("Final answer") or task.get("answer", "")
        actual = task.get("generated_answer", "")

        if task_id in scores:
            is_failure = scores[task_id] < 1.0
        else:
            is_failure = _normalize_answer(expected) != _normalize_answer(actual)

        if not is_failure:
            continue

        step_details = _extract_step_details(task.get("intermediate_steps", []))

        analysis = TaskAnalysis(
            task_id=task_id,
            question=question,
            expected_answer=expected,
            actual_answer=actual,
            step_details=step_details,
        )
        analyses.append(analysis)

    logger.info(
        f"Loaded {len(analyses)} failed tasks from {workflow_output_path} "
        f"(out of {len(data)} total tasks)"
    )
    return analyses, len(data)


def _normalize_answer(answer: str) -> str:
    """Normalize answer for comparison."""
    if not answer:
        return ""
    return answer.strip().lower()


def _extract_step_details(intermediate_steps: list[dict]) -> list[StepDetail]:
    """Extract StepDetail objects from intermediate_steps, preserving full data."""
    details = []

    for i, step in enumerate(intermediate_steps):
        payload = step.get("payload", {})
        event_type = payload.get("event_type", "")
        data = payload.get("data", {})
        usage_info = payload.get("usage_info", {})
        name = payload.get("name", "unknown")

        if event_type == "LLM_END":
            detail = _create_llm_detail(i, name, data, usage_info)
        elif event_type == "TOOL_END":
            detail = _create_tool_detail(i, name, data)
        elif event_type == "RETRIEVER_END":
            detail = _create_retriever_detail(i, name, data)
        else:
            continue

        details.append(detail)

    return details


def _create_llm_detail(
    index: int, name: str, data: dict, usage_info: dict
) -> StepDetail:
    """Create StepDetail for LLM event, keeping full input/output."""
    token_usage = usage_info.get("token_usage", {})
    return StepDetail(
        step_index=index,
        event_type="LLM_END",
        name=name,
        full_input=str(data.get("input", "")),
        full_output=str(data.get("output", "")),
        model=name,
        prompt_tokens=token_usage.get("prompt_tokens"),
        completion_tokens=token_usage.get("completion_tokens"),
    )


def _create_tool_detail(index: int, name: str, data: dict) -> StepDetail:
    """Create StepDetail for Tool event, keeping full data."""
    tool_input = data.get("input", "")
    tool_args = _parse_tool_args(tool_input)

    tool_output = data.get("output", {})
    if isinstance(tool_output, dict):
        output_str = json.dumps(tool_output, ensure_ascii=False)
    else:
        output_str = str(tool_output)

    error_message = _detect_error(tool_output)

    return StepDetail(
        step_index=index,
        event_type="TOOL_END",
        name=name,
        full_input=str(tool_input),
        full_output=output_str,
        tool_args=tool_args,
        error_message=error_message,
    )


def _create_retriever_detail(index: int, name: str, data: dict) -> StepDetail:
    """Create StepDetail for Retriever event."""
    output = data.get("output", [])
    output_str = json.dumps(output, ensure_ascii=False) if isinstance(output, list) else str(output)

    return StepDetail(
        step_index=index,
        event_type="RETRIEVER_END",
        name=name,
        full_input=str(data.get("input", "")),
        full_output=output_str,
    )


def _parse_tool_args(tool_input: Any) -> dict[str, Any]:
    """Parse tool input into args dict."""
    if isinstance(tool_input, dict):
        return tool_input
    if isinstance(tool_input, str):
        try:
            parsed = ast.literal_eval(tool_input)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, SyntaxError):
            pass
        return {"raw_input": tool_input}
    return {"raw_input": str(tool_input)}


def _detect_error(tool_output: Any) -> str | None:
    """Detect error in tool output."""
    if isinstance(tool_output, dict):
        status = tool_output.get("status", "").lower()
        if status in ("error", "failure", "failed"):
            return str(tool_output.get("error", tool_output.get("message", str(tool_output))))

    content = str(tool_output)
    content_lower = content.lower()
    error_patterns = [
        '"status": "error"', '"status":"error"', '"error":',
        "traceback (most recent call last)", "exception: ", "error: ",
    ]
    for pattern in error_patterns:
        if pattern in content_lower:
            return _truncate(content, 500)
    return None


def compress_step_for_llm(
    detail: StepDetail,
    input_max: int = STEP_INPUT_MAX_CHARS,
    output_max: int = STEP_OUTPUT_MAX_CHARS,
) -> dict[str, Any]:
    """Compress a single step for LLM consumption.

    Keeps essential information but truncates large inputs/outputs.
    """
    compressed: dict[str, Any] = {
        "step": detail.step_index,
        "type": detail.event_type,
        "name": detail.name,
    }

    if detail.event_type == "LLM_END":
        compressed["input"] = _truncate(detail.full_input, input_max)
        compressed["output"] = _truncate(detail.full_output, output_max)
        if detail.model:
            compressed["model"] = detail.model
        if detail.prompt_tokens:
            compressed["tokens"] = {
                "prompt": detail.prompt_tokens,
                "completion": detail.completion_tokens,
            }
    elif detail.event_type == "TOOL_END":
        if detail.tool_args:
            args_str = json.dumps(detail.tool_args, ensure_ascii=False)
            if len(args_str) > input_max:
                compressed["args"] = _truncate(args_str, input_max)
            else:
                compressed["args"] = detail.tool_args
        compressed["output"] = _truncate(detail.full_output, output_max)
        if detail.error_message:
            compressed["error"] = _truncate(detail.error_message, min(300, output_max))
    elif detail.event_type == "RETRIEVER_END":
        compressed["input"] = _truncate(detail.full_input, input_max)
        compressed["output"] = _truncate(detail.full_output, output_max)

    return compressed


def build_compressed_trajectory(details: list[StepDetail]) -> str:
    """Build a compressed trajectory string for LLM analysis.

    Adaptively truncates steps to fit within the token budget.
    """
    compressed = [compress_step_for_llm(d) for d in details]
    result = json.dumps(compressed, indent=1, ensure_ascii=False)

    if len(result) <= COMPRESSED_TRAJECTORY_MAX_CHARS:
        return result

    # Adaptive truncation: calculate per-step budget and retry
    per_step_limit = max(100, COMPRESSED_TRAJECTORY_MAX_CHARS // max(len(details), 1) - 50)
    compressed = [compress_step_for_llm(d, input_max=per_step_limit, output_max=per_step_limit) for d in details]
    result = json.dumps(compressed, indent=1, ensure_ascii=False)

    # Final hard truncation if still over budget
    if len(result) > COMPRESSED_TRAJECTORY_MAX_CHARS:
        result = result[:COMPRESSED_TRAJECTORY_MAX_CHARS] + "\n... (truncated)]"

    return result
