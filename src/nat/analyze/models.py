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

from typing import Any

from pydantic import BaseModel, Field


class StepDetail(BaseModel):
    """Complete raw data for a single execution step (preserved for HTML detail view)."""

    step_index: int
    event_type: str  # "LLM_END" | "TOOL_END" | "RETRIEVER_END" | etc.
    name: str
    full_input: str = ""
    full_output: str = ""
    tool_args: dict[str, Any] | None = None
    error_message: str | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class StepSummary(BaseModel):
    """LLM-generated summary for a single step."""

    step_index: int
    event_type: str
    name: str
    summary: str  # 1-2 sentence summary
    is_root_cause: bool = False


class TaskAnalysis(BaseModel):
    """Complete analysis result for a single failed task."""

    task_id: str
    question: str
    expected_answer: str
    actual_answer: str

    # Raw step data (filled by exporter)
    step_details: list[StepDetail] = Field(default_factory=list)

    # LLM-generated analysis (filled by analyzer)
    step_summaries: list[StepSummary] = Field(default_factory=list)
    fingerprint: str = ""  # Free-form short phrase, e.g. "Agent used too vague a search query"
    group_name: str = ""  # Cluster name assigned after fingerprint grouping
    root_cause: str = ""  # 2-4 sentence root cause explanation
    root_cause_step_indices: list[int] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class FingerprintGroup(BaseModel):
    """A cluster of similar fingerprints after LLM-based grouping."""

    group_name: str
    description: str
    count: int
    task_ids: list[str] = Field(default_factory=list)
    representative_root_cause: str = ""
    common_suggestions: list[str] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    """Top-level analysis report containing all results."""

    total_tasks: int
    total_failures: int
    task_analyses: list[TaskAnalysis] = Field(default_factory=list)
    fingerprint_groups: list[FingerprintGroup] = Field(default_factory=list)
    model_used: str = ""
    analysis_timestamp: str = ""
