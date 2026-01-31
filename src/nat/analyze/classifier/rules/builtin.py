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

"""Built-in classification rules for common failure patterns."""

from nat.analyze.classifier.base import ClassificationRule, PatternRule, RuleResult
from nat.analyze.classifier.registry import RuleRegistry
from nat.analyze.models import FailurePacket


# ============ Tool Error Rules ============


@RuleRegistry.register
class ToolTimeoutRule(PatternRule):
    """Detect tool execution timeouts."""

    name = "tool_timeout"
    category = "tool_timeout"
    priority = 10
    description = "Tool execution exceeded timeout limit"

    patterns = [
        r"timeout",
        r"timed?\s*out",
        r"deadline\s*exceeded",
        r"request\s*took\s*too\s*long",
        r"operation\s*timed?\s*out",
    ]
    fix_suggestions = [
        "Increase timeout limit for this tool",
        "Add retry logic with exponential backoff",
        "Consider using a more reliable alternative service",
    ]


@RuleRegistry.register
class ToolRateLimitRule(PatternRule):
    """Detect API rate limit errors."""

    name = "tool_rate_limit"
    category = "tool_rate_limit"
    priority = 10
    description = "API rate limit or quota exceeded"

    patterns = [
        r"rate\s*limit",
        r"too\s*many\s*requests",
        r"quota\s*exceeded",
        r"usage\s*limit",
        r"\b429\b",
        r"throttl",
    ]
    fix_suggestions = [
        "Add rate limiting and request queuing",
        "Implement exponential backoff with jitter",
        "Consider upgrading API quota or using fallback service",
    ]


@RuleRegistry.register
class ToolServerErrorRule(PatternRule):
    """Detect server-side errors (5xx)."""

    name = "tool_server_error"
    category = "tool_server_error"
    priority = 10
    description = "Tool service returned server error"

    patterns = [
        r"\b5\d{2}\b",  # 5xx status codes
        r"internal\s*server\s*error",
        r"service\s*unavailable",
        r"bad\s*gateway",
        r"gateway\s*timeout",
        r"server\s*error",
    ]
    fix_suggestions = [
        "Add retry with exponential backoff",
        "Implement circuit breaker pattern",
        "Add fallback to alternative service",
    ]


@RuleRegistry.register
class ToolParameterErrorRule(PatternRule):
    """Detect invalid parameter errors."""

    name = "tool_parameter_error"
    category = "tool_parameter_error"
    priority = 15
    description = "Tool received invalid parameters"

    patterns = [
        r"invalid\s*(parameter|argument|input)",
        r"missing\s*required",
        r"validation\s*error",
        r"type\s*error",
        r"400\s*bad\s*request",
        r"bad\s*request",
    ]
    fix_suggestions = [
        "Improve tool description to clarify expected parameters",
        "Add parameter validation before tool call",
        "Provide few-shot examples of correct tool usage",
    ]


@RuleRegistry.register
class NetworkErrorRule(PatternRule):
    """Detect network connectivity errors."""

    name = "network_error"
    category = "network_error"
    priority = 10
    description = "Network connectivity failure"

    patterns = [
        r"connection\s*(refused|reset|failed)",
        r"dns\s*(lookup|resolution)\s*failed",
        r"ssl\s*(error|certificate)",
        r"network\s*(unreachable|error)",
        r"econnrefused",
        r"enotfound",
        r"etimedout",
    ]
    fix_suggestions = [
        "Check network connectivity",
        "Verify DNS configuration",
        "Add retry with network error handling",
    ]


@RuleRegistry.register
class AuthFailureRule(PatternRule):
    """Detect authentication failures."""

    name = "auth_failure"
    category = "auth_failure"
    priority = 15
    description = "Authentication or authorization failed"

    patterns = [
        r"\b401\b",
        r"\b403\b",
        r"unauthorized",
        r"authentication\s*failed",
        r"invalid\s*.*api\s*key",
        r"token\s*expired",
        r"access\s*denied",
        r"permission\s*denied",
    ]
    fix_suggestions = [
        "Check API key configuration",
        "Refresh authentication token",
        "Verify permissions for the requested operation",
    ]


# ============ Output Format Rules ============


@RuleRegistry.register
class OutputFormatRule(PatternRule):
    """Detect output format/parsing errors."""

    name = "output_format"
    category = "output_format"
    priority = 20
    description = "Output format or parsing error"

    patterns = [
        r"json\s*(parse|decode|syntax)\s*error",
        r"invalid\s*json",
        r"expecting\s*(value|property)",
        r"unterminated\s*string",
        r"schema\s*(validation|mismatch)",
        r"parse\s*error",
    ]
    check_fields = ["error_message", "tool_result_summary"]
    fix_suggestions = [
        "Enforce JSON schema in output parsing",
        "Add output repair loop for malformed responses",
        "Improve prompt to specify exact output format required",
    ]


@RuleRegistry.register
class OutputEmptyRule(ClassificationRule):
    """Detect empty output."""

    name = "output_empty"
    category = "output_empty"
    priority = 25
    description = "Agent produced empty output"

    def match(self, packet: FailurePacket) -> RuleResult:
        actual = packet.actual_output.strip()
        if not actual:
            return RuleResult(
                matched=True,
                category=self.category,
                evidence="Agent produced empty output",
                fix_suggestions=[
                    "Check if agent terminated prematurely",
                    "Add validation to ensure non-empty response",
                    "Review execution trace for early termination cause",
                ],
            )
        return RuleResult(matched=False, category=self.category)


# ============ Context Rules ============


@RuleRegistry.register
class ContextOverflowRule(ClassificationRule):
    """Detect context length overflow."""

    name = "context_overflow"
    category = "context_overflow"
    priority = 30
    description = "Context token limit exceeded"

    def __init__(self, token_limit: int = 128000) -> None:
        self.token_limit = token_limit

    def match(self, packet: FailurePacket) -> RuleResult:
        total_tokens = 0
        llm_span_ids = []

        for span in packet.spans:
            if span.span_type == "llm":
                prompt_tokens = span.prompt_tokens or 0
                completion_tokens = span.completion_tokens or 0
                total_tokens += prompt_tokens + completion_tokens
                llm_span_ids.append(span.span_id)

        # Check if approaching or exceeding limit (95% threshold)
        if total_tokens > self.token_limit * 0.95:
            return RuleResult(
                matched=True,
                category=self.category,
                evidence=(
                    f"Total tokens ({total_tokens}) exceeded 95% of "
                    f"context limit ({self.token_limit})"
                ),
                key_span_ids=llm_span_ids[-3:] if llm_span_ids else [],
                fix_suggestions=[
                    "Add context summarization middleware",
                    "Implement sliding window for conversation history",
                    "Truncate tool outputs before adding to context",
                ],
            )

        return RuleResult(matched=False, category=self.category)


# ============ Retrieval Rules ============


@RuleRegistry.register
class RetrievalEmptyRule(ClassificationRule):
    """Detect empty retrieval results."""

    name = "retrieval_empty"
    category = "retrieval_empty"
    priority = 30
    description = "Retriever returned no documents"

    def match(self, packet: FailurePacket) -> RuleResult:
        for span in packet.spans:
            if span.span_type == "retriever" and span.docs_returned == 0:
                return RuleResult(
                    matched=True,
                    category=self.category,
                    evidence=f"Retriever '{span.name}' returned 0 documents",
                    key_span_ids=[span.span_id],
                    fix_suggestions=[
                        "Improve query generation for better recall",
                        "Expand knowledge base coverage",
                        "Add fallback to web search when retrieval is empty",
                    ],
                )

        return RuleResult(matched=False, category=self.category)


# ============ Agent Loop Rules ============


@RuleRegistry.register
class RecursionLimitRule(PatternRule):
    """Detect agent iteration/recursion limit."""

    name = "recursion_limit"
    category = "recursion_limit"
    priority = 20
    description = "Agent reached iteration or recursion limit"

    patterns = [
        r"maximum\s*iterations?\s*(reached|exceeded)",
        r"recursion\s*limit",
        r"max\s*steps?\s*(reached|exceeded)",
        r"agent\s*loop\s*limit",
        r"iteration\s*limit",
    ]
    fix_suggestions = [
        "Increase max_iterations configuration",
        "Improve task decomposition to require fewer steps",
        "Add early termination conditions for completed tasks",
    ]


# ============ Resource Rules ============


@RuleRegistry.register
class ResourceExhaustionRule(PatternRule):
    """Detect resource exhaustion (memory, CPU, disk)."""

    name = "resource_exhaustion"
    category = "resource_exhaustion"
    priority = 15
    description = "System resource exhaustion"

    patterns = [
        r"out\s*of\s*memory",
        r"memory\s*(error|exhausted|limit)",
        r"oom\s*killer",
        r"disk\s*(full|quota)",
        r"no\s*space\s*left",
        r"cpu\s*limit",
        r"killed.*memory",
    ]
    fix_suggestions = [
        "Increase memory limit in sandbox configuration",
        "Optimize memory usage in tool implementation",
        "Add streaming for large data processing",
    ]


# ============ Generic Error Rule (lowest priority) ============


@RuleRegistry.register
class GenericToolErrorRule(ClassificationRule):
    """Catch-all for tool errors not matched by other rules."""

    name = "generic_tool_error"
    category = "tool_server_error"
    priority = 999  # Lowest priority - runs last
    description = "Generic tool error (catch-all)"

    def match(self, packet: FailurePacket) -> RuleResult:
        for span in packet.spans:
            if span.span_type == "tool" and span.status == "ERROR":
                error_msg = span.error_message or span.tool_result_summary or "Unknown error"
                snippet = error_msg[:200] + "..." if len(error_msg) > 200 else error_msg

                return RuleResult(
                    matched=True,
                    category=self.category,
                    evidence=f"Tool '{span.tool_name}' failed with error: {snippet}",
                    key_span_ids=[span.span_id],
                    fix_suggestions=[
                        "Add retry with fallback mechanism",
                        "Improve error handling for this tool",
                        "Check tool service availability",
                    ],
                )

        return RuleResult(matched=False, category=self.category)
