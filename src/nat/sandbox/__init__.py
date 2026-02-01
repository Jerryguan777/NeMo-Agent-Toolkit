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

"""Sandbox module for isolated execution environments.

This module provides sandbox implementations for running code in isolated
environments. Available implementations:

- DockerSandbox: Local Docker container-based sandbox
  Requires: pip install nvidia-nat[sandbox-docker]

- DaytonaSandbox: Cloud-based sandbox via Daytona service
  Requires: pip install nvidia-nat[sandbox-daytona]

Example YAML configuration:

    sandboxes:
      my_sandbox:
        _type: docker
        image: python:3.12-slim
        memory_limit: 1g

    function_groups:
      sandbox_tools:
        _type: sandbox_tools
        sandbox_name: my_sandbox
"""

# Workspace constants
from nat.sandbox.config import DEFAULT_SCRIPT_PATH
from nat.sandbox.config import WORKSPACE_DOWNLOADS
from nat.sandbox.config import WORKSPACE_INIT_COMMAND
from nat.sandbox.config import WORKSPACE_INPUT
from nat.sandbox.config import WORKSPACE_OUTPUT
from nat.sandbox.config import WORKSPACE_ROOT
from nat.sandbox.config import WORKSPACE_TEMP

# Core interfaces
from nat.sandbox.base import BaseSandbox
from nat.sandbox.base import CommandResult

# Implementations
from nat.sandbox.daytona_sandbox import DaytonaSandbox
from nat.sandbox.docker_sandbox import DockerSandbox

__all__ = [
    # Interfaces
    "BaseSandbox",
    "CommandResult",
    # Implementations
    "DockerSandbox",
    "DaytonaSandbox",
    # Workspace constants
    "WORKSPACE_ROOT",
    "WORKSPACE_INPUT",
    "WORKSPACE_OUTPUT",
    "WORKSPACE_TEMP",
    "WORKSPACE_DOWNLOADS",
    "WORKSPACE_INIT_COMMAND",
    "DEFAULT_SCRIPT_PATH",
]
