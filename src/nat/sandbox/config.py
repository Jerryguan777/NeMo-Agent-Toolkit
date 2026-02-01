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

"""Workspace constants for sandbox implementations.

These constants define the standard workspace directory structure.
All sandbox implementations should use these paths.
"""

# Root workspace directory
WORKSPACE_ROOT = "/workspace"

# Standard workspace subdirectories
WORKSPACE_INPUT = f"{WORKSPACE_ROOT}/input"
WORKSPACE_OUTPUT = f"{WORKSPACE_ROOT}/output"
WORKSPACE_TEMP = f"{WORKSPACE_ROOT}/temp"
WORKSPACE_DOWNLOADS = f"{WORKSPACE_ROOT}/downloads"

# Command to initialize workspace directories
WORKSPACE_INIT_COMMAND = (
    f"mkdir -p {WORKSPACE_INPUT} {WORKSPACE_OUTPUT} {WORKSPACE_TEMP} {WORKSPACE_DOWNLOADS}"
)

# Default script path for Python execution
DEFAULT_SCRIPT_PATH = f"{WORKSPACE_TEMP}/_script.py"
