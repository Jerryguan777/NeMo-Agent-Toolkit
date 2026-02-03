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

"""Robust tool execution with retry and fallback strategies.

This module provides error recovery mechanisms to improve agent robustness,
addressing failures caused by transient errors, rate limiting, and blocked URLs.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """Types of errors that can be handled."""

    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    CLOUDFLARE = "cloudflare"
    AUTHENTICATION = "authentication"
    NOT_FOUND = "not_found"
    CONNECTION = "connection"
    UNKNOWN = "unknown"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    initial_delay_ms: int = 1000
    max_delay_ms: int = 30000
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class ExecutionResult:
    """Result of a tool execution attempt."""

    success: bool
    result: Any = None
    error: str | None = None
    error_type: ErrorType = ErrorType.UNKNOWN
    attempts: int = 1
    total_time_ms: float = 0
    fallback_used: str | None = None


@dataclass
class FallbackStrategy:
    """A fallback strategy for a specific error type."""

    error_type: ErrorType
    fallback_fn: Callable[..., Any]
    description: str


class RobustToolExecutor:
    """Executor with retry logic and fallback strategies.

    This class wraps tool execution to provide:
    - Exponential backoff retry for transient failures
    - Fallback strategies for specific error types
    - Error classification and reporting
    - Cloudflare bypass using archive services
    """

    # Patterns to detect specific error types
    ERROR_PATTERNS = {
        ErrorType.TIMEOUT: [
            r"timeout",
            r"timed out",
            r"deadline exceeded",
        ],
        ErrorType.RATE_LIMIT: [
            r"rate limit",
            r"too many requests",
            r"429",
            r"quota exceeded",
        ],
        ErrorType.SERVER_ERROR: [
            r"500",
            r"502",
            r"503",
            r"504",
            r"internal server error",
            r"service unavailable",
            r"bad gateway",
        ],
        ErrorType.CLOUDFLARE: [
            r"cloudflare",
            r"cf-ray",
            r"checking your browser",
            r"just a moment",
            r"please wait",
            r"ddos protection",
        ],
        ErrorType.AUTHENTICATION: [
            r"401",
            r"403",
            r"unauthorized",
            r"forbidden",
            r"access denied",
            r"login required",
        ],
        ErrorType.NOT_FOUND: [
            r"404",
            r"not found",
            r"page does not exist",
        ],
        ErrorType.CONNECTION: [
            r"connection refused",
            r"connection reset",
            r"network unreachable",
            r"dns",
            r"could not resolve",
        ],
    }

    # Retryable error types
    RETRYABLE_ERRORS = {
        ErrorType.TIMEOUT,
        ErrorType.RATE_LIMIT,
        ErrorType.SERVER_ERROR,
        ErrorType.CONNECTION,
    }

    def __init__(
        self,
        retry_config: RetryConfig | None = None,
        fallback_strategies: list[FallbackStrategy] | None = None,
    ):
        """Initialize the robust executor.

        Args:
            retry_config: Configuration for retry behavior.
            fallback_strategies: List of fallback strategies.
        """
        self.retry_config = retry_config or RetryConfig()
        self.fallback_strategies = {s.error_type: s for s in (fallback_strategies or [])}

    def classify_error(self, error: str | Exception) -> ErrorType:
        """Classify an error into a known type.

        Args:
            error: Error message or exception.

        Returns:
            Classified error type.
        """
        error_str = str(error).lower()

        for error_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_str, re.IGNORECASE):
                    return error_type

        return ErrorType.UNKNOWN

    async def execute_with_retry(
        self,
        tool_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> ExecutionResult:
        """Execute a tool function with retry logic.

        Args:
            tool_fn: The tool function to execute.
            *args: Positional arguments for the tool.
            **kwargs: Keyword arguments for the tool.

        Returns:
            ExecutionResult with outcome details.
        """
        start_time = time.time()
        last_error: str | None = None
        last_error_type = ErrorType.UNKNOWN

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Execute the tool
                if asyncio.iscoroutinefunction(tool_fn):
                    result = await tool_fn(*args, **kwargs)
                else:
                    result = tool_fn(*args, **kwargs)

                total_time = (time.time() - start_time) * 1000

                return ExecutionResult(
                    success=True,
                    result=result,
                    attempts=attempt + 1,
                    total_time_ms=total_time,
                )

            except Exception as e:
                last_error = str(e)
                last_error_type = self.classify_error(e)

                logger.warning(
                    f"Attempt {attempt + 1}/{self.retry_config.max_retries + 1} failed: "
                    f"{last_error_type.value} - {last_error[:100]}"
                )

                # Check if error is retryable
                if last_error_type not in self.RETRYABLE_ERRORS:
                    break

                # Check if we have more retries
                if attempt < self.retry_config.max_retries:
                    # Calculate delay with exponential backoff
                    delay_ms = min(
                        self.retry_config.initial_delay_ms * (self.retry_config.exponential_base ** attempt),
                        self.retry_config.max_delay_ms,
                    )

                    # Add jitter to prevent thundering herd
                    if self.retry_config.jitter:
                        import random
                        delay_ms *= (0.5 + random.random())

                    logger.info(f"Retrying in {delay_ms:.0f}ms...")
                    await asyncio.sleep(delay_ms / 1000)

        # All retries exhausted, try fallback
        total_time = (time.time() - start_time) * 1000

        if last_error_type in self.fallback_strategies:
            strategy = self.fallback_strategies[last_error_type]
            logger.info(f"Attempting fallback: {strategy.description}")

            try:
                if asyncio.iscoroutinefunction(strategy.fallback_fn):
                    result = await strategy.fallback_fn(*args, **kwargs)
                else:
                    result = strategy.fallback_fn(*args, **kwargs)

                return ExecutionResult(
                    success=True,
                    result=result,
                    attempts=self.retry_config.max_retries + 1,
                    total_time_ms=(time.time() - start_time) * 1000,
                    fallback_used=strategy.description,
                )
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                last_error = f"Original: {last_error}; Fallback: {fallback_error}"

        return ExecutionResult(
            success=False,
            error=last_error,
            error_type=last_error_type,
            attempts=self.retry_config.max_retries + 1,
            total_time_ms=total_time,
        )


class CloudflareBypass:
    """Strategies for bypassing Cloudflare protection.

    Provides alternative methods to access content that is blocked by Cloudflare
    or similar protection services.
    """

    # Alternative URL services
    ARCHIVE_SERVICES = [
        "https://web.archive.org/web/",
        "https://webcache.googleusercontent.com/search?q=cache:",
    ]

    @classmethod
    def get_archive_url(cls, url: str, service_index: int = 0) -> str:
        """Get an archive service URL for the given URL.

        Args:
            url: Original URL to access.
            service_index: Index of archive service to use.

        Returns:
            Archive service URL.
        """
        if service_index < len(cls.ARCHIVE_SERVICES):
            return f"{cls.ARCHIVE_SERVICES[service_index]}{url}"
        return url

    @classmethod
    def get_alternative_urls(cls, url: str) -> list[str]:
        """Get all alternative URLs for accessing content.

        Args:
            url: Original URL.

        Returns:
            List of alternative URLs to try.
        """
        alternatives = []
        for service in cls.ARCHIVE_SERVICES:
            alternatives.append(f"{service}{url}")
        return alternatives


def create_url_fallback_strategy(browse_fn: Callable[..., Any]) -> FallbackStrategy:
    """Create a fallback strategy for URL browsing that uses archive services.

    Args:
        browse_fn: The original browse function.

    Returns:
        FallbackStrategy for Cloudflare errors.
    """
    async def archive_fallback(url: str, *args: Any, **kwargs: Any) -> Any:
        """Try to access URL via archive services."""
        alternatives = CloudflareBypass.get_alternative_urls(url)

        for alt_url in alternatives:
            try:
                logger.info(f"Trying archive URL: {alt_url[:50]}...")
                if asyncio.iscoroutinefunction(browse_fn):
                    result = await browse_fn(alt_url, *args, **kwargs)
                else:
                    result = browse_fn(alt_url, *args, **kwargs)
                return result
            except Exception as e:
                logger.warning(f"Archive fallback failed: {e}")
                continue

        raise RuntimeError("All archive fallbacks exhausted")

    return FallbackStrategy(
        error_type=ErrorType.CLOUDFLARE,
        fallback_fn=archive_fallback,
        description="Try archive.org or Google cache",
    )


@dataclass
class ToolExecutionMetrics:
    """Metrics for tool execution."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    retried_calls: int = 0
    fallback_used: int = 0
    total_time_ms: float = 0
    error_distribution: dict[str, int] = field(default_factory=dict)

    def record(self, result: ExecutionResult) -> None:
        """Record metrics from an execution result."""
        self.total_calls += 1
        self.total_time_ms += result.total_time_ms

        if result.success:
            self.successful_calls += 1
            if result.fallback_used:
                self.fallback_used += 1
        else:
            self.failed_calls += 1
            error_key = result.error_type.value
            self.error_distribution[error_key] = self.error_distribution.get(error_key, 0) + 1

        if result.attempts > 1:
            self.retried_calls += 1

    def summary(self) -> dict[str, Any]:
        """Get metrics summary."""
        return {
            "total_calls": self.total_calls,
            "success_rate": self.successful_calls / self.total_calls if self.total_calls > 0 else 0,
            "retry_rate": self.retried_calls / self.total_calls if self.total_calls > 0 else 0,
            "fallback_rate": self.fallback_used / self.total_calls if self.total_calls > 0 else 0,
            "avg_time_ms": self.total_time_ms / self.total_calls if self.total_calls > 0 else 0,
            "error_distribution": self.error_distribution,
        }


class MeteredToolExecutor(RobustToolExecutor):
    """RobustToolExecutor with metrics collection."""

    def __init__(
        self,
        retry_config: RetryConfig | None = None,
        fallback_strategies: list[FallbackStrategy] | None = None,
    ):
        super().__init__(retry_config, fallback_strategies)
        self.metrics = ToolExecutionMetrics()

    async def execute_with_retry(
        self,
        tool_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> ExecutionResult:
        result = await super().execute_with_retry(tool_fn, *args, **kwargs)
        self.metrics.record(result)
        return result

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics summary."""
        return self.metrics.summary()

    def reset_metrics(self) -> None:
        """Reset metrics to initial state."""
        self.metrics = ToolExecutionMetrics()
