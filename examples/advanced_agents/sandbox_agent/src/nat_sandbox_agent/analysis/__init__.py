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

"""
Failure Analysis Module - Hybrid LLM-based failure analysis.

This module provides a pipeline for:
1. Exporting failure data from workflow_output.json
2. Hybrid LLM-based classification with 2-stage analysis
3. Dashboard generation with ROI-prioritized recommendations

Usage:
    # Run analysis using nat CLI (recommended)
    nat analyze -w .tmp/workflow_output.json

    # Or use the standalone CLI
    python -m nat_sandbox_agent.analysis.cli analyze \\
        --workflow-output .tmp/workflow_output.json
"""

from nat_sandbox_agent.analysis.models import (
    EvalResult,
    FailureCategory,
    FailurePacket,
    SpanSummary,
    TriageResult,
)
from nat_sandbox_agent.analysis.workflow_exporter import WorkflowExporter
from nat_sandbox_agent.analysis.hybrid_analyzer import (
    HybridFailureAnalyzer,
    HybridAnalysisResult,
    CategoryManager,
    NewCategorySuggestion,
    run_hybrid_analysis,
    RootCauseCategory,
    CATEGORY_DESCRIPTIONS,
)

__all__ = [
    # Models
    "EvalResult",
    "FailureCategory",
    "FailurePacket",
    "SpanSummary",
    "TriageResult",
    # Exporters
    "WorkflowExporter",
    # Hybrid Analyzer (recommended)
    "HybridFailureAnalyzer",
    "HybridAnalysisResult",
    "CategoryManager",
    "NewCategorySuggestion",
    "run_hybrid_analysis",
    "RootCauseCategory",
    "CATEGORY_DESCRIPTIONS",
]
