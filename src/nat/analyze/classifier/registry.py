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

"""Rule registry for managing classification rules."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Type

import yaml

if TYPE_CHECKING:
    from nat.analyze.classifier.base import ClassificationRule

logger = logging.getLogger(__name__)


class RuleRegistry:
    """Registry for classification rules.

    Manages rule registration from decorators, YAML config, and Python modules.

    Example usage:
        ```python
        from nat.analyze import RuleRegistry, PatternRule

        # Register via decorator
        @RuleRegistry.register
        class MyRule(PatternRule):
            name = "my_rule"
            category = "tool_server_error"
            patterns = [r"my_error"]

        # Load from YAML
        RuleRegistry.load_from_yaml(Path("config.yaml"))

        # Load from Python file
        RuleRegistry.load_from_python(Path("my_rules.py"))

        # Get all rules
        rules = RuleRegistry.get_rules()
        ```
    """

    _rules: list[Type[ClassificationRule]] = []
    _initialized: bool = False
    _disabled_rules: set[str] = set()

    @classmethod
    def register(cls, rule_class: Type[ClassificationRule]) -> Type[ClassificationRule]:
        """Decorator to register a rule class.

        Args:
            rule_class: The rule class to register.

        Returns:
            The registered rule class (unchanged).
        """
        cls._rules.append(rule_class)
        cls._rules.sort(key=lambda r: getattr(r, "priority", 100))
        logger.debug(f"Registered rule: {rule_class.name} (priority={getattr(rule_class, 'priority', 100)})")
        return rule_class

    @classmethod
    def load_builtin_rules(cls) -> None:
        """Load built-in rules from the rules subpackage."""
        if cls._initialized:
            return

        # Import builtin rules to get the rule classes
        from nat.analyze.classifier.rules import builtin

        # Get all rule classes from the module (those decorated with @register
        # may not re-register if module was already imported)
        import inspect
        from nat.analyze.classifier.base import ClassificationRule, PatternRule

        for name, obj in inspect.getmembers(builtin):
            if (
                inspect.isclass(obj)
                and issubclass(obj, ClassificationRule)
                and obj is not ClassificationRule
                and hasattr(obj, "name")
                and not any(r.name == obj.name for r in cls._rules)
            ):
                cls._rules.append(obj)

        cls._rules.sort(key=lambda r: getattr(r, "priority", 100))
        cls._initialized = True
        logger.info(f"Loaded {len(cls._rules)} built-in rules")

    @classmethod
    def load_from_yaml(cls, config_path: Path) -> None:
        """Load rules from a YAML configuration file.

        YAML format:
            ```yaml
            custom_rules:
              - name: my_rule
                category: tool_server_error
                priority: 50
                patterns:
                  - "my_error"
                  - "custom_failure"
                fix_suggestions:
                  - "Check the logs"

            disabled_rules:
              - tool_parameter_error
            ```

        Args:
            config_path: Path to the YAML config file.
        """
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}

        # Load custom rules
        for rule_def in config.get("custom_rules", []):
            rule_class = cls._create_rule_from_yaml(rule_def)
            cls._rules.append(rule_class)
            logger.debug(f"Loaded YAML rule: {rule_def['name']}")

        # Track disabled rules
        for rule_name in config.get("disabled_rules", []):
            cls._disabled_rules.add(rule_name)
            logger.debug(f"Disabled rule: {rule_name}")

        cls._rules.sort(key=lambda r: getattr(r, "priority", 100))

    @classmethod
    def load_from_python(cls, module_path: Path) -> None:
        """Load rules from a Python module file.

        The module should use @RuleRegistry.register decorators.

        Args:
            module_path: Path to the Python file.
        """
        spec = importlib.util.spec_from_file_location("custom_rules", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        logger.info(f"Loaded rules from {module_path}")

    @classmethod
    def _create_rule_from_yaml(cls, rule_def: dict) -> Type[ClassificationRule]:
        """Create a rule class from YAML definition.

        Args:
            rule_def: Dictionary with rule definition.

        Returns:
            A dynamically created PatternRule subclass.
        """
        from nat.analyze.classifier.base import PatternRule

        class YAMLRule(PatternRule):
            name = rule_def["name"]
            category = rule_def["category"]
            priority = rule_def.get("priority", 100)
            patterns = rule_def.get("patterns", [])
            check_fields = rule_def.get("check_fields", ["error_message", "tool_result_summary"])
            fix_suggestions = rule_def.get("fix_suggestions", [])
            description = rule_def.get("description", "")

        # Give the class a unique name for debugging
        YAMLRule.__name__ = f"YAMLRule_{rule_def['name']}"
        return YAMLRule

    @classmethod
    def get_rules(cls) -> list[Type[ClassificationRule]]:
        """Get all registered rules (excluding disabled ones).

        Returns:
            List of rule classes sorted by priority.
        """
        cls.load_builtin_rules()
        return [r for r in cls._rules if r.name not in cls._disabled_rules]

    @classmethod
    def get_all_rules(cls) -> list[Type[ClassificationRule]]:
        """Get all registered rules (including disabled ones).

        Returns:
            List of all rule classes.
        """
        cls.load_builtin_rules()
        return list(cls._rules)

    @classmethod
    def disable_rule(cls, rule_name: str) -> None:
        """Disable a rule by name.

        Args:
            rule_name: Name of the rule to disable.
        """
        cls._disabled_rules.add(rule_name)

    @classmethod
    def enable_rule(cls, rule_name: str) -> None:
        """Re-enable a disabled rule.

        Args:
            rule_name: Name of the rule to enable.
        """
        cls._disabled_rules.discard(rule_name)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered rules (for testing)."""
        cls._rules = []
        cls._initialized = False
        cls._disabled_rules = set()

    @classmethod
    def list_rules(cls) -> list[dict]:
        """List all rules with their metadata.

        Returns:
            List of rule info dictionaries.
        """
        cls.load_builtin_rules()
        return [
            {
                "name": r.name,
                "category": r.category,
                "priority": getattr(r, "priority", 100),
                "description": getattr(r, "description", ""),
                "enabled": r.name not in cls._disabled_rules,
            }
            for r in cls._rules
        ]
