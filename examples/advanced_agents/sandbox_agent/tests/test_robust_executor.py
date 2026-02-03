# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for robust tool execution with retry and fallback."""

import pytest
import asyncio

from nat_sandbox_agent.tools.robust_executor import (
    RobustToolExecutor,
    MeteredToolExecutor,
    RetryConfig,
    ExecutionResult,
    ErrorType,
    CloudflareBypass,
    ToolExecutionMetrics,
)


class TestErrorType:
    """Tests for ErrorType enum."""

    def test_enum_values(self):
        assert ErrorType.TIMEOUT == "timeout"
        assert ErrorType.RATE_LIMIT == "rate_limit"
        assert ErrorType.SERVER_ERROR == "server_error"
        assert ErrorType.CLOUDFLARE == "cloudflare"
        assert ErrorType.AUTHENTICATION == "authentication"
        assert ErrorType.NOT_FOUND == "not_found"
        assert ErrorType.CONNECTION == "connection"
        assert ErrorType.UNKNOWN == "unknown"


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self):
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_delay_ms == 1000
        assert config.max_delay_ms == 30000
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_values(self):
        config = RetryConfig(max_retries=5, initial_delay_ms=500)
        assert config.max_retries == 5
        assert config.initial_delay_ms == 500


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_success_result(self):
        result = ExecutionResult(
            success=True,
            result="test data",
            attempts=1,
            total_time_ms=100.0
        )
        assert result.success is True
        assert result.result == "test data"
        assert result.error is None

    def test_failure_result(self):
        result = ExecutionResult(
            success=False,
            error="Connection failed",
            error_type=ErrorType.CONNECTION,
            attempts=3,
            total_time_ms=5000.0
        )
        assert result.success is False
        assert result.error == "Connection failed"
        assert result.error_type == ErrorType.CONNECTION

    def test_fallback_result(self):
        result = ExecutionResult(
            success=True,
            result="cached data",
            fallback_used="archive.org",
            attempts=4,
            total_time_ms=2000.0
        )
        assert result.success is True
        assert result.fallback_used == "archive.org"


class TestErrorClassification:
    """Tests for error classification."""

    def setup_method(self):
        self.executor = RobustToolExecutor()

    def test_classify_timeout_error(self):
        error = "Request timed out after 30 seconds"
        assert self.executor.classify_error(error) == ErrorType.TIMEOUT

    def test_classify_rate_limit_error(self):
        error = "Rate limit exceeded, please try again later"
        assert self.executor.classify_error(error) == ErrorType.RATE_LIMIT

    def test_classify_429_error(self):
        error = "HTTP 429: Too Many Requests"
        assert self.executor.classify_error(error) == ErrorType.RATE_LIMIT

    def test_classify_server_error(self):
        error = "HTTP 500 Internal Server Error"
        assert self.executor.classify_error(error) == ErrorType.SERVER_ERROR

    def test_classify_502_error(self):
        error = "502 Bad Gateway"
        assert self.executor.classify_error(error) == ErrorType.SERVER_ERROR

    def test_classify_cloudflare_error(self):
        error = "Cloudflare challenge detected, checking your browser"
        assert self.executor.classify_error(error) == ErrorType.CLOUDFLARE

    def test_classify_authentication_error(self):
        error = "HTTP 401 Unauthorized"
        assert self.executor.classify_error(error) == ErrorType.AUTHENTICATION

    def test_classify_forbidden_error(self):
        error = "HTTP 403 Forbidden - Access denied"
        assert self.executor.classify_error(error) == ErrorType.AUTHENTICATION

    def test_classify_not_found_error(self):
        error = "HTTP 404 Not Found"
        assert self.executor.classify_error(error) == ErrorType.NOT_FOUND

    def test_classify_connection_error(self):
        error = "Connection refused by remote host"
        assert self.executor.classify_error(error) == ErrorType.CONNECTION

    def test_classify_dns_error(self):
        error = "DNS resolution failed: could not resolve host"
        assert self.executor.classify_error(error) == ErrorType.CONNECTION

    def test_classify_unknown_error(self):
        error = "Some random unexpected error"
        assert self.executor.classify_error(error) == ErrorType.UNKNOWN


class TestRobustExecution:
    """Tests for robust execution with retry."""

    def setup_method(self):
        self.executor = RobustToolExecutor(
            retry_config=RetryConfig(max_retries=2, initial_delay_ms=10)
        )

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        async def success_fn():
            return "success"

        result = await self.executor.execute_with_retry(success_fn)

        assert result.success is True
        assert result.result == "success"
        assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self):
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Connection refused")
            return "success"

        result = await self.executor.execute_with_retry(fail_then_succeed)

        assert result.success is True
        assert result.result == "success"
        assert result.attempts == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_error(self):
        call_count = 0

        async def auth_failure():
            nonlocal call_count
            call_count += 1
            raise Exception("HTTP 401 Unauthorized")

        result = await self.executor.execute_with_retry(auth_failure)

        assert result.success is False
        assert result.error_type == ErrorType.AUTHENTICATION
        # Should not retry authentication errors
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise Exception("Connection timed out")

        result = await self.executor.execute_with_retry(always_fail)

        assert result.success is False
        assert result.error_type == ErrorType.TIMEOUT
        assert result.attempts == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_sync_function_support(self):
        def sync_fn():
            return "sync result"

        result = await self.executor.execute_with_retry(sync_fn)

        assert result.success is True
        assert result.result == "sync result"


class TestCloudflareBypass:
    """Tests for Cloudflare bypass strategies."""

    def test_get_archive_url(self):
        url = "https://example.com/page"
        archive_url = CloudflareBypass.get_archive_url(url)
        assert archive_url.startswith("https://web.archive.org/web/")
        assert url in archive_url

    def test_get_alternative_urls(self):
        url = "https://example.com/page"
        alternatives = CloudflareBypass.get_alternative_urls(url)

        assert len(alternatives) >= 2
        assert any("archive.org" in alt for alt in alternatives)
        assert any("googleusercontent" in alt for alt in alternatives)


class TestToolExecutionMetrics:
    """Tests for execution metrics tracking."""

    def test_initial_state(self):
        metrics = ToolExecutionMetrics()
        assert metrics.total_calls == 0
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 0

    def test_record_success(self):
        metrics = ToolExecutionMetrics()
        result = ExecutionResult(success=True, result="data", total_time_ms=100)
        metrics.record(result)

        assert metrics.total_calls == 1
        assert metrics.successful_calls == 1
        assert metrics.failed_calls == 0

    def test_record_failure(self):
        metrics = ToolExecutionMetrics()
        result = ExecutionResult(
            success=False,
            error="failed",
            error_type=ErrorType.TIMEOUT,
            total_time_ms=100
        )
        metrics.record(result)

        assert metrics.total_calls == 1
        assert metrics.failed_calls == 1
        assert metrics.error_distribution[ErrorType.TIMEOUT.value] == 1

    def test_record_retry(self):
        metrics = ToolExecutionMetrics()
        result = ExecutionResult(success=True, result="data", attempts=3, total_time_ms=100)
        metrics.record(result)

        assert metrics.retried_calls == 1

    def test_record_fallback(self):
        metrics = ToolExecutionMetrics()
        result = ExecutionResult(
            success=True,
            result="data",
            fallback_used="archive",
            total_time_ms=100
        )
        metrics.record(result)

        assert metrics.fallback_used == 1

    def test_summary(self):
        metrics = ToolExecutionMetrics()
        metrics.record(ExecutionResult(success=True, total_time_ms=100))
        metrics.record(ExecutionResult(
            success=False, error="err", error_type=ErrorType.TIMEOUT, total_time_ms=200
        ))

        summary = metrics.summary()

        assert summary["total_calls"] == 2
        assert summary["success_rate"] == 0.5
        assert summary["avg_time_ms"] == 150


class TestMeteredToolExecutor:
    """Tests for MeteredToolExecutor."""

    @pytest.mark.asyncio
    async def test_metrics_collected(self):
        executor = MeteredToolExecutor(
            retry_config=RetryConfig(max_retries=0)
        )

        async def success_fn():
            return "data"

        await executor.execute_with_retry(success_fn)
        await executor.execute_with_retry(success_fn)

        metrics = executor.get_metrics()
        assert metrics["total_calls"] == 2
        assert metrics["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_reset_metrics(self):
        executor = MeteredToolExecutor()

        async def fn():
            return "data"

        await executor.execute_with_retry(fn)
        executor.reset_metrics()

        metrics = executor.get_metrics()
        assert metrics["total_calls"] == 0
