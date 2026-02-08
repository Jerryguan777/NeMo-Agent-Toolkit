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

"""NAT Analyze - LLM-based failure analysis tool for NeMo Agent Toolkit."""

__version__ = "0.2.0"

__all__ = [
    "AnalysisReport",
    "FailureAnalyzer",
    "FingerprintGroup",
    "StepDetail",
    "StepSummary",
    "TaskAnalysis",
]


def __getattr__(name: str):
    if name in ("AnalysisReport", "FingerprintGroup", "StepDetail", "StepSummary", "TaskAnalysis"):
        from nat.analyze.models import (
            AnalysisReport,
            FingerprintGroup,
            StepDetail,
            StepSummary,
            TaskAnalysis,
        )

        _model_exports = {
            "AnalysisReport": AnalysisReport,
            "FingerprintGroup": FingerprintGroup,
            "StepDetail": StepDetail,
            "StepSummary": StepSummary,
            "TaskAnalysis": TaskAnalysis,
        }
        globals().update(_model_exports)
        return _model_exports[name]

    if name == "FailureAnalyzer":
        from nat.analyze.analyzer import FailureAnalyzer

        globals()["FailureAnalyzer"] = FailureAnalyzer
        return FailureAnalyzer

    raise AttributeError(f"module 'nat.analyze' has no attribute {name!r}")
