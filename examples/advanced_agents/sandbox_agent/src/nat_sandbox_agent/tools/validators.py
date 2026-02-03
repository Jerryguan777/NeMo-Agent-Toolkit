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

"""Output format validation and correction utilities.

This module provides tools to validate and auto-correct answer formats
to address the 12.2% output_format failure category.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class NumberFormat(str, Enum):
    """Expected number format."""

    PLAIN = "plain"  # No commas, no formatting (e.g., "1000000")
    COMMA_SEPARATED = "comma_separated"  # With commas (e.g., "1,000,000")
    DECIMAL = "decimal"  # With decimal places (e.g., "3.14")
    SCIENTIFIC = "scientific"  # Scientific notation (e.g., "1.0e6")
    PERCENTAGE = "percentage"  # Percentage format (e.g., "50%")
    UNSPECIFIED = "unspecified"


class CaseFormat(str, Enum):
    """Expected case format."""

    LOWERCASE = "lowercase"
    UPPERCASE = "uppercase"
    TITLE_CASE = "title_case"
    AS_IS = "as_is"


@dataclass
class FormatRequirements:
    """Format requirements extracted from a question."""

    # Number formatting
    number_format: NumberFormat = NumberFormat.UNSPECIFIED
    decimal_places: int | None = None
    include_units: bool | None = None
    unit_type: str | None = None

    # Multiple answer formatting
    expected_multiple_answers: bool = False
    delimiter: str | None = None  # comma, semicolon, newline, etc.
    answer_count: int | None = None

    # Text formatting
    case_format: CaseFormat = CaseFormat.AS_IS

    # Specific constraints
    no_explanation: bool = True  # Default: just the answer
    specific_format: str | None = None  # e.g., "YYYY-MM-DD" for dates


class OutputFormatValidator:
    """Validates and corrects output formats based on question requirements.

    This validator addresses the 12.2% of failures caused by correct answers
    in wrong formats (e.g., "100,000,000" vs "100000000").
    """

    # Patterns for detecting format requirements in questions
    NUMBER_FORMAT_PATTERNS = [
        (r"(?:without|no)\s+commas?", NumberFormat.PLAIN),
        (r"comma[- ]?separated", NumberFormat.COMMA_SEPARATED),
        (r"(\d+)\s+decimal\s+places?", NumberFormat.DECIMAL),
        (r"as\s+(?:a\s+)?percent(?:age)?", NumberFormat.PERCENTAGE),
        (r"in\s+scientific\s+notation", NumberFormat.SCIENTIFIC),
    ]

    UNIT_PATTERNS = [
        (r"(?:without|no|exclude)\s+(?:the\s+)?units?", False),
        (r"(?:with|include)\s+(?:the\s+)?units?", True),
        (r"in\s+(meters?|km|miles?|feet|inches?|cm|mm)", True),
        (r"in\s+(kg|grams?|pounds?|ounces?|tons?)", True),
        (r"in\s+(seconds?|minutes?|hours?|days?|years?)", True),
        (r"in\s+(dollars?|\$|USD|EUR|€|GBP|£)", True),
    ]

    DELIMITER_PATTERNS = [
        (r"comma[- ]?separated", ","),
        (r"separated\s+by\s+commas?", ","),
        (r"semicolon[- ]?separated", ";"),
        (r"separated\s+by\s+semicolons?", ";"),
        (r"one\s+per\s+line", "\n"),
        (r"each\s+on\s+(?:a\s+)?(?:new|separate)\s+line", "\n"),
        (r"space[- ]?separated", " "),
    ]

    CASE_PATTERNS = [
        (r"(?:in\s+)?(?:all\s+)?lowercase", CaseFormat.LOWERCASE),
        (r"(?:in\s+)?(?:all\s+)?uppercase", CaseFormat.UPPERCASE),
        (r"(?:in\s+)?title\s+case", CaseFormat.TITLE_CASE),
    ]

    MULTIPLE_ANSWER_PATTERNS = [
        (r"list\s+(?:all|the)", True),
        (r"what\s+are\s+(?:the|all)", True),
        (r"name\s+(?:all|the)", True),
        (r"give\s+(?:all|the)", True),
        (r"(\d+)\s+(?:answers?|items?|things?)", True),
    ]

    def extract_format_requirements(self, question: str) -> FormatRequirements:
        """Extract format requirements from a question.

        Args:
            question: The question text to analyze.

        Returns:
            FormatRequirements with detected requirements.
        """
        question_lower = question.lower()
        requirements = FormatRequirements()

        # Check number format
        for pattern, format_type in self.NUMBER_FORMAT_PATTERNS:
            match = re.search(pattern, question_lower)
            if match:
                requirements.number_format = format_type
                if format_type == NumberFormat.DECIMAL and match.groups():
                    try:
                        requirements.decimal_places = int(match.group(1))
                    except (ValueError, IndexError):
                        pass
                break

        # Check unit requirements
        for pattern, include_units in self.UNIT_PATTERNS:
            match = re.search(pattern, question_lower)
            if match:
                requirements.include_units = include_units
                if include_units and match.groups():
                    requirements.unit_type = match.group(1)
                break

        # Check delimiter requirements
        for pattern, delimiter in self.DELIMITER_PATTERNS:
            if re.search(pattern, question_lower):
                requirements.delimiter = delimiter
                requirements.expected_multiple_answers = True
                break

        # Check case requirements
        for pattern, case_format in self.CASE_PATTERNS:
            if re.search(pattern, question_lower):
                requirements.case_format = case_format
                break

        # Check for multiple answers
        for pattern, is_multiple in self.MULTIPLE_ANSWER_PATTERNS:
            match = re.search(pattern, question_lower)
            if match:
                requirements.expected_multiple_answers = is_multiple
                if match.groups():
                    try:
                        requirements.answer_count = int(match.group(1))
                    except (ValueError, IndexError):
                        pass
                break

        # Check for date format requirements
        date_formats = [
            (r"YYYY-MM-DD", "YYYY-MM-DD"),
            (r"MM/DD/YYYY", "MM/DD/YYYY"),
            (r"DD/MM/YYYY", "DD/MM/YYYY"),
            (r"ISO\s*8601", "YYYY-MM-DD"),
        ]
        for pattern, fmt in date_formats:
            if re.search(pattern, question, re.IGNORECASE):
                requirements.specific_format = fmt
                break

        return requirements

    def validate_and_correct(
        self,
        answer: str,
        requirements: FormatRequirements | None = None,
        question: str | None = None,
    ) -> str:
        """Validate and auto-correct answer format.

        Args:
            answer: The answer to validate/correct.
            requirements: Pre-computed requirements, or None to extract from question.
            question: Question text (used if requirements is None).

        Returns:
            Corrected answer string.
        """
        corrected = answer.strip()

        # Always remove common prefixes/suffixes that shouldn't be in the answer
        corrected = self._remove_explanation_phrases(corrected)

        # Get requirements if needed for format-specific corrections
        if requirements is None and question is not None:
            requirements = self.extract_format_requirements(question)

        # Apply format-specific corrections if requirements are available
        if requirements is not None:
            # Apply number formatting
            corrected = self._format_number(corrected, requirements)

            # Apply case formatting
            corrected = self._format_case(corrected, requirements)

            # Handle delimiter formatting for multiple answers
            corrected = self._format_delimiter(corrected, requirements)

        return corrected.strip()

    def _remove_explanation_phrases(self, answer: str) -> str:
        """Remove common explanation phrases from answers."""
        # Patterns that indicate explanatory text before the answer
        prefixes_to_remove = [
            r"^the\s+answer\s+is[:\s]+",
            r"^the\s+final\s+answer\s+is[:\s]+",
            r"^the\s+result\s+is[:\s]+",
            r"^the\s+value\s+is[:\s]+",
            r"^it\s+is[:\s]+",
            r"^it's[:\s]+",
            r"^i\s+found\s+that\s+the\s+",
            r"^i\s+found\s+that\s+",
            r"^i\s+found\s+",
            r"^based\s+on\s+[^,]{1,50},\s*",
            r"^therefore,\s*the\s+answer\s+is\s+",
            r"^therefore,\s*",
            r"^thus,\s*",
            r"^so,\s*",
            r"^in\s+conclusion,\s*",
        ]

        result = answer.strip()

        # Keep applying patterns until no more matches
        changed = True
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        while changed and iteration < max_iterations:
            changed = False
            iteration += 1
            for pattern in prefixes_to_remove:
                new_result = re.sub(pattern, "", result, flags=re.IGNORECASE)
                if new_result != result:
                    result = new_result.strip()
                    changed = True
                    break  # Start over from first pattern

        # Remove trailing explanation
        suffixes_to_remove = [
            r"\s*\(.*?\)\s*$",  # Parenthetical notes at end
        ]
        for pattern in suffixes_to_remove:
            result = re.sub(pattern, "", result)

        # Strip trailing period and whitespace
        result = result.rstrip(". \t")

        return result

    def _format_number(self, answer: str, requirements: FormatRequirements) -> str:
        """Apply number formatting rules."""
        if requirements.number_format == NumberFormat.UNSPECIFIED:
            return answer

        # Try to extract number from answer
        number_match = re.search(r"[-+]?[\d,]+\.?\d*(?:[eE][-+]?\d+)?", answer)
        if not number_match:
            return answer

        number_str = number_match.group()
        # Remove existing commas to parse
        clean_number = number_str.replace(",", "")

        try:
            if "." in clean_number or "e" in clean_number.lower():
                value = float(clean_number)
            else:
                value = int(clean_number)
        except ValueError:
            return answer

        # Format based on requirements
        if requirements.number_format == NumberFormat.PLAIN:
            if isinstance(value, float):
                if requirements.decimal_places is not None:
                    formatted = f"{value:.{requirements.decimal_places}f}"
                else:
                    formatted = str(value)
            else:
                formatted = str(value)
        elif requirements.number_format == NumberFormat.COMMA_SEPARATED:
            if isinstance(value, float):
                formatted = f"{value:,.{requirements.decimal_places or 2}f}"
            else:
                formatted = f"{value:,}"
        elif requirements.number_format == NumberFormat.DECIMAL:
            places = requirements.decimal_places or 2
            formatted = f"{value:.{places}f}"
        elif requirements.number_format == NumberFormat.PERCENTAGE:
            formatted = f"{value}%"
        elif requirements.number_format == NumberFormat.SCIENTIFIC:
            formatted = f"{value:.2e}"
        else:
            formatted = str(value)

        # Replace the number in the answer
        return answer.replace(number_str, formatted)

    def _format_case(self, answer: str, requirements: FormatRequirements) -> str:
        """Apply case formatting rules."""
        if requirements.case_format == CaseFormat.LOWERCASE:
            return answer.lower()
        elif requirements.case_format == CaseFormat.UPPERCASE:
            return answer.upper()
        elif requirements.case_format == CaseFormat.TITLE_CASE:
            return answer.title()
        return answer

    def _format_delimiter(self, answer: str, requirements: FormatRequirements) -> str:
        """Normalize delimiter for multiple answers."""
        if not requirements.expected_multiple_answers or not requirements.delimiter:
            return answer

        # Try to detect current delimiter
        possible_delimiters = [", ", ",", "; ", ";", "\n", " and ", " or "]
        current_delimiter = None

        for delim in possible_delimiters:
            if delim in answer:
                current_delimiter = delim
                break

        if current_delimiter and current_delimiter != requirements.delimiter:
            parts = [p.strip() for p in answer.split(current_delimiter)]
            # Clean up "and" or "or" in last item
            if parts and " and " in parts[-1]:
                last_parts = parts[-1].split(" and ")
                parts = parts[:-1] + [p.strip() for p in last_parts]
            if parts and " or " in parts[-1]:
                last_parts = parts[-1].split(" or ")
                parts = parts[:-1] + [p.strip() for p in last_parts]

            return requirements.delimiter.join(parts)

        return answer


def create_format_validator() -> OutputFormatValidator:
    """Create an OutputFormatValidator instance.

    Returns:
        OutputFormatValidator instance.
    """
    return OutputFormatValidator()
