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

"""Rule-based classifier using the rule registry."""

import logging

from nat.analyze.classifier.registry import RuleRegistry
from nat.analyze.models import FailureCategory, FailurePacket

logger = logging.getLogger(__name__)


class RuleBasedClassifier:
    """Rule-based classifier for deterministic failure categorization.

    This classifier uses registered rules (both built-in and custom) to
    detect failure causes from span attributes without LLM analysis.

    Example:
        ```python
        from nat.analyze.classifier import RuleBasedClassifier

        classifier = RuleBasedClassifier()
        rule_classified, needs_llm = classifier.classify_batch(packets)
        ```
    """

    def __init__(self) -> None:
        """Initialize the classifier with all registered rules."""
        self._rule_instances = []

        # Instantiate all registered rules
        for rule_class in RuleRegistry.get_rules():
            try:
                rule = rule_class()
                self._rule_instances.append(rule)
            except Exception as e:
                logger.warning(f"Failed to instantiate rule {rule_class.name}: {e}")

        logger.info(f"Initialized classifier with {len(self._rule_instances)} rules")

    def classify(self, packet: FailurePacket) -> bool:
        """Classify a failure packet using registered rules.

        Args:
            packet: The failure packet to classify.

        Returns:
            True if a rule matched, False if LLM triage is needed.
        """
        for rule in self._rule_instances:
            try:
                result = rule.match(packet)
                if result.matched:
                    # Apply classification
                    packet.failure_category = FailureCategory.get(result.category)
                    packet.classification_source = "rule"
                    packet.classification_confidence = 1.0
                    packet.root_cause_evidence = result.evidence
                    packet.key_span_ids = result.key_span_ids
                    packet.fix_suggestions = result.fix_suggestions

                    logger.debug(
                        f"Rule '{rule.name}' matched packet {packet.task_id}: "
                        f"{result.category}"
                    )
                    return True

            except Exception as e:
                logger.warning(f"Rule {rule.name} raised exception: {e}")

        return False

    def classify_batch(
        self, packets: list[FailurePacket]
    ) -> tuple[list[FailurePacket], list[FailurePacket]]:
        """Classify a batch of packets.

        Args:
            packets: List of failure packets to classify.

        Returns:
            Tuple of (rule_classified, needs_llm_triage) packet lists.
        """
        rule_classified = []
        needs_llm = []

        for packet in packets:
            if self.classify(packet):
                rule_classified.append(packet)
            else:
                needs_llm.append(packet)

        logger.info(
            f"Rule classification: {len(rule_classified)} classified, "
            f"{len(needs_llm)} need LLM triage"
        )

        return rule_classified, needs_llm
