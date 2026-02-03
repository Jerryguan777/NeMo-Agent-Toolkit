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

"""Data models for failure analysis pipeline."""

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import Field


class FailureCategory(str, Enum):
    """Failure category taxonomy (9 main categories)."""

    # Rule-detectable categories
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_RATE_LIMIT = "tool_rate_limit"
    TOOL_SERVER_ERROR = "tool_server_error"
    TOOL_PARAMETER_ERROR = "tool_parameter_error"
    OUTPUT_FORMAT = "output_format"
    RETRIEVAL_EMPTY = "retrieval_empty"
    CONTEXT_OVERFLOW = "context_overflow"

    # LLM-triage categories
    TASK_UNDERSTANDING = "task_understanding"
    PLANNING_DECOMPOSITION = "planning_decomposition"
    TOOL_SELECTION = "tool_selection"
    EVIDENCE_UTILIZATION = "evidence_utilization"
    REASONING_CALCULATION = "reasoning_calculation"
    STATE_MEMORY = "state_memory"
    POLICY_SAFETY = "policy_safety"

    # Unknown/uncategorized
    UNKNOWN = "unknown"

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
    duration_ms: float
    start_time: float | None = None

    # LLM-specific fields
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    input_summary: str | None = None  # Truncated to 500 chars
    output_summary: str | None = None  # Truncated to 500 chars

    # Tool-specific fields
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result_summary: str | None = None  # Truncated to 500 chars
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
    user_request: str  # Original user request/question
    system_prompt: str = ""  # Complete system prompt
    config: dict[str, Any] = Field(default_factory=dict)  # Model, temperature, tool list

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
    code_version: str = ""  # git commit
    tool_schema_version: str = ""
    random_seed: int | None = None

    # 6. Classification result (filled by classifier)
    failure_category: FailureCategory | str | None = None  # Accept both enum and string for hybrid analyzer
    classification_source: str | None = None  # "rule" | "llm" | "hybrid_stage1" | "hybrid_stage2"
    classification_confidence: float | None = None

    # 7. Root cause analysis (filled by classifier/triage)
    root_cause_evidence: str = ""  # Explanation of why this category was assigned
    key_span_ids: list[str] = Field(default_factory=list)  # Span IDs that are critical to the failure
    fix_suggestions: list[str] = Field(default_factory=list)  # Recommended fixes

    # 8. Hybrid LLM analysis details (filled by hybrid analyzer)
    llm_analysis: dict[str, Any] = Field(default_factory=dict)  # Detailed analysis from hybrid LLM

class TriageResult(BaseModel):
    """Result of LLM-based failure triage."""

    category: FailureCategory
    confidence: float = Field(ge=0.0, le=1.0)
    key_spans: list[str] = Field(default_factory=list)  # Span IDs that are turning points
    evidence: str = ""  # Explanation of why this category
    fix_suggestions: list[str] = Field(default_factory=list)

class CategoryStats(BaseModel):
    """Statistics for a failure category."""

    category: FailureCategory
    count: int
    percentage: float
    example_task_ids: list[str] = Field(default_factory=list)
    has_test_cases: bool = True

class PriorityScore(BaseModel):
    """ROI priority score for a failure category."""

    category: FailureCategory
    score: float
    frequency: float
    impact: float
    fixability: float
    verifiability: float
    fix_template: str = ""
    effort_level: str = ""  # "Low" | "Medium" | "High"
