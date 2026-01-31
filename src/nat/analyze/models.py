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

"""Data models for failure analysis pipeline."""

from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class FailureCategory(str, Enum):
    """Failure category taxonomy.

    Supports both built-in categories and runtime-registered custom categories.
    """

    # === Rule-based categories (12) ===
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_RATE_LIMIT = "tool_rate_limit"
    TOOL_SERVER_ERROR = "tool_server_error"
    TOOL_PARAMETER_ERROR = "tool_parameter_error"
    OUTPUT_FORMAT = "output_format"
    OUTPUT_EMPTY = "output_empty"
    CONTEXT_OVERFLOW = "context_overflow"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    RECURSION_LIMIT = "recursion_limit"
    NETWORK_ERROR = "network_error"
    AUTH_FAILURE = "auth_failure"
    RETRIEVAL_EMPTY = "retrieval_empty"

    # === LLM-based categories (7) ===
    TASK_UNDERSTANDING = "task_understanding"
    PLANNING_DECOMPOSITION = "planning_decomposition"
    TOOL_SELECTION = "tool_selection"
    EVIDENCE_UTILIZATION = "evidence_utilization"
    REASONING_CALCULATION = "reasoning_calculation"
    STATE_MEMORY = "state_memory"
    POLICY_SAFETY = "policy_safety"

    # Unknown/uncategorized
    UNKNOWN = "unknown"


# Custom categories storage (module-level to avoid Enum issues)
_custom_categories: dict[str, str] = {}


def register_custom_category(category_id: str, description: str = "") -> None:
    """Register a custom failure category.

    Args:
        category_id: Unique identifier for the category.
        description: Human-readable description.
    """
    _custom_categories[category_id] = description


def get_category(value: str) -> FailureCategory | str:
    """Get a category by value, supporting custom categories.

    Args:
        value: Category string value.

    Returns:
        FailureCategory enum or string for custom categories.
    """
    try:
        return FailureCategory(value)
    except ValueError:
        if value in _custom_categories:
            return value
        return FailureCategory.UNKNOWN


def all_categories() -> list[str]:
    """Get all category IDs (built-in + custom).

    Returns:
        List of all category string values.
    """
    builtin = [c.value for c in FailureCategory]
    custom = list(_custom_categories.keys())
    return builtin + custom


def is_custom_category(value: str) -> bool:
    """Check if a category is custom (not built-in).

    Args:
        value: Category string value.

    Returns:
        True if custom category.
    """
    return value in _custom_categories


# Add convenience methods to FailureCategory for backwards compatibility
FailureCategory.register_custom = staticmethod(register_custom_category)  # type: ignore
FailureCategory.get = staticmethod(get_category)  # type: ignore
FailureCategory.all_categories = staticmethod(all_categories)  # type: ignore
FailureCategory.is_custom = staticmethod(is_custom_category)  # type: ignore
FailureCategory._custom_categories = _custom_categories  # type: ignore


class EvalResult(BaseModel):
    """Evaluation result for a single task."""

    passed: bool
    score: float | None = None
    reason: str = ""
    evaluator: str = "unknown"


class SpanSummary(BaseModel):
    """Compressed span information for analysis."""

    span_id: str
    span_type: str  # "llm" | "tool" | "chain" | "retriever"
    name: str
    status: str  # "OK" | "ERROR"
    duration_ms: float = 0.0
    start_time: float | None = None

    # LLM-specific fields
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    input_summary: str | None = None
    output_summary: str | None = None

    # Tool-specific fields
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result_summary: str | None = None
    error_message: str | None = None

    # Retriever-specific fields
    docs_returned: int | None = None


class StateDiff(BaseModel):
    """State change between steps."""

    step_index: int
    key: str
    old_value: Any | None = None
    new_value: Any | None = None


class FailurePacket(BaseModel):
    """Complete evidence packet for a single failure case."""

    # 1. Input context
    task_id: str
    user_request: str
    system_prompt: str = ""
    config: dict[str, Any] = Field(default_factory=dict)

    # 2. Execution trace
    trace_id: str = ""
    spans: list[SpanSummary] = Field(default_factory=list)

    # 3. State snapshots
    state_diffs: list[StateDiff] = Field(default_factory=list)

    # 4. Evaluation results
    expected_output: str
    actual_output: str
    eval_result: EvalResult

    # 5. Replay information
    run_id: str = ""
    prompt_version: str = ""
    code_version: str = ""
    tool_schema_version: str = ""
    random_seed: int | None = None

    # 6. Classification result (filled by classifier)
    failure_category: FailureCategory | str | None = None
    classification_source: str | None = None  # "rule" | "llm"
    classification_confidence: float | None = None

    # 7. Root cause analysis (filled by classifier/triage)
    root_cause_evidence: str = ""
    key_span_ids: list[str] = Field(default_factory=list)
    fix_suggestions: list[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    """Result of LLM-based failure triage."""

    category: FailureCategory | str
    confidence: float = Field(ge=0.0, le=1.0)
    key_spans: list[str] = Field(default_factory=list)
    evidence: str = ""
    fix_suggestions: list[str] = Field(default_factory=list)


class CategoryStats(BaseModel):
    """Statistics for a failure category."""

    category: FailureCategory | str
    count: int
    percentage: float
    example_task_ids: list[str] = Field(default_factory=list)
    has_test_cases: bool = True


class PriorityScore(BaseModel):
    """ROI priority score for a failure category."""

    category: FailureCategory | str
    score: float
    frequency: float
    impact: float
    fixability: float
    verifiability: float
    fix_template: str = ""
    effort_level: str = ""  # "Low" | "Medium" | "High"
