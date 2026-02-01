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

"""Registration module for sandbox implementations."""

from nat.builder.builder import Builder
from nat.cli.register_workflow import register_sandbox
from nat.data_models.sandbox import DaytonaSandboxConfig
from nat.data_models.sandbox import DockerSandboxConfig
from nat.sandbox.daytona_sandbox import DaytonaSandbox
from nat.sandbox.docker_sandbox import DockerSandbox


@register_sandbox(config_type=DockerSandboxConfig)
async def docker_sandbox(config: DockerSandboxConfig, builder: Builder):
    """Build and yield a Docker sandbox instance.

    Args:
        config: Docker sandbox configuration.
        builder: The workflow builder instance.

    Yields:
        DockerSandbox: A started Docker sandbox instance.
    """
    sandbox = DockerSandbox(
        image=config.image,
        memory_limit=config.memory_limit,
        cpu_limit=config.cpu_limit,
        network_enabled=config.network_enabled,
        work_dir=config.work_dir,
        container_name=config.container_name,
        auto_remove=config.auto_remove,
        environment=config.environment,
        volumes=config.volumes,
    )

    await sandbox.start()

    try:
        yield sandbox
    finally:
        await sandbox.cleanup()


@register_sandbox(config_type=DaytonaSandboxConfig)
async def daytona_sandbox(config: DaytonaSandboxConfig, builder: Builder):
    """Build and yield a Daytona sandbox instance.

    Args:
        config: Daytona sandbox configuration.
        builder: The workflow builder instance.

    Yields:
        DaytonaSandbox: A started Daytona sandbox instance.
    """
    sandbox = DaytonaSandbox(
        api_key=config.api_key,
        server_url=config.server_url,
        target=config.target,
        image=config.image,
        cpu=config.cpu,
        memory=config.memory,
        disk=config.disk,
        auto_stop_interval=config.auto_stop_interval,
    )

    await sandbox.start()

    try:
        yield sandbox
    finally:
        await sandbox.cleanup()
