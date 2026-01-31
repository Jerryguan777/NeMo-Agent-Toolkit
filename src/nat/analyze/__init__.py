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

"""NAT Analyze - Failure analysis tool for NeMo Agent Toolkit."""

__version__ = "0.1.0"

from nat.analyze.models import FailureCategory, FailurePacket, SpanSummary
from nat.analyze.classifier.registry import RuleRegistry
from nat.analyze.classifier.base import ClassificationRule, PatternRule, RuleResult

__all__ = [
    "FailureCategory",
    "FailurePacket",
    "SpanSummary",
    "RuleRegistry",
    "ClassificationRule",
    "PatternRule",
    "RuleResult",
]
