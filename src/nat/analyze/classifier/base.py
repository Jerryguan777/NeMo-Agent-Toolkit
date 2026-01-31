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

"""Base classes for classification rules."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from nat.analyze.models import FailurePacket


@dataclass
class RuleResult:
    """Result of a classification rule match."""

    matched: bool
    category: str
    evidence: str = ""
    key_span_ids: list[str] = field(default_factory=list)
    fix_suggestions: list[str] = field(default_factory=list)


class ClassificationRule(ABC):
    """Base class for classification rules.

    All custom rules must inherit from this class and implement the match() method.

    Example:
        ```python
        from nat.analyze import ClassificationRule, RuleRegistry, RuleResult

        @RuleRegistry.register
        class MyCustomRule(ClassificationRule):
            name = "my_custom_rule"
            category = "tool_server_error"
            priority = 50

            def match(self, packet):
                # Custom matching logic
                for span in packet.spans:
                    if "my_error" in (span.error_message or ""):
                        return RuleResult(
                            matched=True,
                            category=self.category,
                            evidence="Found my_error pattern",
                        )
                return RuleResult(matched=False, category=self.category)
        ```
    """

    # Subclasses must define these
    name: ClassVar[str]  # Rule name, e.g., "tool_timeout"
    category: ClassVar[str]  # Failure category to assign
    priority: ClassVar[int] = 100  # Lower = higher priority
    description: ClassVar[str] = ""  # Human-readable description

    @abstractmethod
    def match(self, packet: FailurePacket) -> RuleResult:
        """Check if this rule matches the failure packet.

        Args:
            packet: The failure packet to analyze.

        Returns:
            RuleResult with matched=True if the rule matches.
        """
        pass


class PatternRule(ClassificationRule):
    """Pattern-based classification rule.

    A convenience base class for rules that match regex patterns against
    span fields. Subclasses just need to define the patterns.

    Example:
        ```python
        @RuleRegistry.register
        class MyPatternRule(PatternRule):
            name = "my_pattern"
            category = "tool_server_error"
            patterns = [r"my_error_\\d+", r"custom_failure"]
            fix_suggestions = ["Check the logs", "Retry the operation"]
        ```
    """

    patterns: ClassVar[list[str]] = []
    check_fields: ClassVar[list[str]] = ["error_message", "tool_result_summary"]
    fix_suggestions: ClassVar[list[str]] = []

    def __init__(self) -> None:
        """Initialize the pattern rule and compile regex patterns."""
        if self.patterns:
            combined = "|".join(f"({p})" for p in self.patterns)
            self._compiled_re = re.compile(combined, re.IGNORECASE)
        else:
            self._compiled_re = None

    def match(self, packet: FailurePacket) -> RuleResult:
        """Match patterns against span fields.

        Args:
            packet: The failure packet to analyze.

        Returns:
            RuleResult with matched=True if any pattern matches.
        """
        if not self._compiled_re:
            return RuleResult(matched=False, category=self.category)

        for span in packet.spans:
            if span.span_type != "tool":
                continue

            for field_name in self.check_fields:
                text = getattr(span, field_name, "") or ""
                if not text:
                    continue

                if self._compiled_re.search(text):
                    snippet = text[:200] + "..." if len(text) > 200 else text
                    return RuleResult(
                        matched=True,
                        category=self.category,
                        evidence=f"Tool '{span.tool_name}' matched pattern. Text: {snippet}",
                        key_span_ids=[span.span_id],
                        fix_suggestions=list(self.fix_suggestions),
                    )

        return RuleResult(matched=False, category=self.category)
