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

"""Sandbox configuration models."""

import typing

from pydantic import ConfigDict
from pydantic import Field

from nat.data_models.common import TypedBaseModel

# TypeVar for generic typing of sandbox configurations
SandboxBaseConfigT = typing.TypeVar("SandboxBaseConfigT", bound="SandboxBaseConfig")


class SandboxBaseConfig(TypedBaseModel):
    """Base configuration class for sandbox implementations.

    All sandbox implementations (Docker, Daytona, etc.) should derive their
    configuration classes from this base class.
    """

    model_config = ConfigDict(extra="forbid")


class DockerSandboxConfig(SandboxBaseConfig, name="docker"):
    """Configuration for Docker-based sandbox.

    This sandbox uses Docker containers to provide isolated execution
    environments for code execution.

    Requires: pip install nvidia-nat[sandbox-docker]
    """

    image: str = Field(
        default="python:3.12-slim",
        description="Docker image to use for the container.",
    )
    memory_limit: str = Field(
        default="512m",
        description="Memory limit for the container (e.g., '512m', '1g').",
    )
    cpu_limit: float = Field(
        default=1.0,
        description="CPU limit (number of CPUs).",
    )
    network_enabled: bool = Field(
        default=True,
        description="Whether to enable network access in the container.",
    )
    work_dir: str = Field(
        default="/workspace",
        description="Working directory inside the container.",
    )
    container_name: str | None = Field(
        default=None,
        description="Optional container name (auto-generated if None).",
    )
    auto_remove: bool = Field(
        default=False,
        description="Whether to automatically remove container on stop.",
    )
    environment: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to pass to the container.",
    )
    volumes: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Volume mounts dict {host_path: {'bind': container_path, 'mode': 'rw'}}.",
    )


class DaytonaSandboxConfig(SandboxBaseConfig, name="daytona"):
    """Configuration for Daytona cloud-based sandbox.

    This sandbox uses the Daytona cloud service to provide isolated
    execution environments.

    Requires: pip install nvidia-nat[sandbox-daytona]
    """

    api_key: str = Field(
        ...,
        description="Daytona API key for authentication.",
    )
    server_url: str = Field(
        default="https://api.daytona.io",
        description="Daytona API server URL.",
    )
    target: str = Field(
        default="us",
        description="Target region (e.g., 'us', 'eu').",
    )
    image: str = Field(
        default="daytonaio/workspace:latest",
        description="Docker image for the Daytona workspace.",
    )
    cpu: int = Field(
        default=2,
        description="Number of CPU cores.",
    )
    memory: int = Field(
        default=4,
        description="Memory in GB.",
    )
    disk: int = Field(
        default=10,
        description="Disk space in GB.",
    )
    auto_stop_interval: int = Field(
        default=30,
        description="Auto-stop interval in minutes (0 to disable).",
    )
