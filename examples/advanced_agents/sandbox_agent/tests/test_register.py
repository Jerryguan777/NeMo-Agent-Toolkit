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
"""Tests for function registration configuration."""

import pytest

from nat_sandbox_agent.register import WebSearchConfig


class TestWebSearchConfig:
    """Tests for WebSearchConfig class."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        config = WebSearchConfig()

        assert config.api_key is None
        assert config.max_results == 5

    def test_custom_api_key(self):
        """Test custom API key configuration."""
        config = WebSearchConfig(api_key="test-key")
        assert config.api_key == "test-key"

    def test_custom_max_results(self):
        """Test custom max_results configuration."""
        config = WebSearchConfig(max_results=10)
        assert config.max_results == 10

    def test_max_results_bounds(self):
        """Test max_results validation bounds."""
        # Should accept valid values
        config = WebSearchConfig(max_results=1)
        assert config.max_results == 1

        config = WebSearchConfig(max_results=10)
        assert config.max_results == 10

        # Should reject out-of-bounds values
        with pytest.raises(Exception):
            WebSearchConfig(max_results=0)

        with pytest.raises(Exception):
            WebSearchConfig(max_results=11)
