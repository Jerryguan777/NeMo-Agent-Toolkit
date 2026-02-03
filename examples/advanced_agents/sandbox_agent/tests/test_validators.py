# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for output format validators."""

import pytest

from nat_sandbox_agent.tools.validators import (
    OutputFormatValidator,
    FormatRequirements,
    NumberFormat,
    CaseFormat,
    create_format_validator,
)


class TestFormatRequirementsExtraction:
    """Tests for extracting format requirements from questions."""

    def setup_method(self):
        self.validator = OutputFormatValidator()

    def test_extract_plain_number_format(self):
        question = "What is the population without commas?"
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.number_format == NumberFormat.PLAIN

    def test_extract_comma_separated_number_format(self):
        question = "Give me the value in comma-separated format."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.number_format == NumberFormat.COMMA_SEPARATED

    def test_extract_decimal_places(self):
        question = "Calculate the result to 3 decimal places."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.number_format == NumberFormat.DECIMAL
        assert reqs.decimal_places == 3

    def test_extract_percentage_format(self):
        question = "Express the answer as a percentage."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.number_format == NumberFormat.PERCENTAGE

    def test_extract_no_units(self):
        question = "Give the distance without units."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.include_units is False

    def test_extract_with_units(self):
        question = "Give the distance in meters."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.include_units is True
        assert reqs.unit_type == "meters"

    def test_extract_comma_delimiter(self):
        question = "List all the names, comma-separated."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.delimiter == ","
        assert reqs.expected_multiple_answers is True

    def test_extract_semicolon_delimiter(self):
        question = "List items separated by semicolons."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.delimiter == ";"
        assert reqs.expected_multiple_answers is True

    def test_extract_lowercase_format(self):
        question = "Give the answer in lowercase."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.case_format == CaseFormat.LOWERCASE

    def test_extract_uppercase_format(self):
        question = "Give the answer in UPPERCASE."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.case_format == CaseFormat.UPPERCASE

    def test_extract_multiple_answers(self):
        question = "List all the countries that..."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.expected_multiple_answers is True

    def test_extract_date_format(self):
        question = "Give the date in YYYY-MM-DD format."
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.specific_format == "YYYY-MM-DD"

    def test_no_special_requirements(self):
        question = "What is the capital of France?"
        reqs = self.validator.extract_format_requirements(question)
        assert reqs.number_format == NumberFormat.UNSPECIFIED
        assert reqs.include_units is None
        assert reqs.delimiter is None
        assert reqs.case_format == CaseFormat.AS_IS


class TestAnswerValidationAndCorrection:
    """Tests for validating and correcting answers."""

    def setup_method(self):
        self.validator = OutputFormatValidator()

    def test_remove_answer_prefix(self):
        answer = "The answer is Paris"
        corrected = self.validator.validate_and_correct(answer)
        assert corrected == "Paris"

    def test_remove_result_prefix(self):
        answer = "The result is 42"
        corrected = self.validator.validate_and_correct(answer)
        assert corrected == "42"

    def test_remove_therefore_prefix(self):
        answer = "Therefore, the answer is London"
        corrected = self.validator.validate_and_correct(answer)
        assert corrected == "London"

    def test_format_number_plain(self):
        reqs = FormatRequirements(number_format=NumberFormat.PLAIN)
        answer = "100,000,000"
        corrected = self.validator.validate_and_correct(answer, reqs)
        assert corrected == "100000000"

    def test_format_number_comma_separated(self):
        reqs = FormatRequirements(number_format=NumberFormat.COMMA_SEPARATED)
        answer = "1000000"
        corrected = self.validator.validate_and_correct(answer, reqs)
        assert corrected == "1,000,000"

    def test_format_number_percentage(self):
        reqs = FormatRequirements(number_format=NumberFormat.PERCENTAGE)
        answer = "50"
        corrected = self.validator.validate_and_correct(answer, reqs)
        assert corrected == "50%"

    def test_format_case_lowercase(self):
        reqs = FormatRequirements(case_format=CaseFormat.LOWERCASE)
        answer = "PARIS"
        corrected = self.validator.validate_and_correct(answer, reqs)
        assert corrected == "paris"

    def test_format_case_uppercase(self):
        reqs = FormatRequirements(case_format=CaseFormat.UPPERCASE)
        answer = "paris"
        corrected = self.validator.validate_and_correct(answer, reqs)
        assert corrected == "PARIS"

    def test_format_case_title(self):
        reqs = FormatRequirements(case_format=CaseFormat.TITLE_CASE)
        answer = "hello world"
        corrected = self.validator.validate_and_correct(answer, reqs)
        assert corrected == "Hello World"

    def test_format_delimiter_change(self):
        reqs = FormatRequirements(
            expected_multiple_answers=True,
            delimiter=";"
        )
        answer = "apple, banana, cherry"
        corrected = self.validator.validate_and_correct(answer, reqs)
        assert corrected == "apple;banana;cherry"

    def test_format_from_question(self):
        question = "What is the population without commas?"
        answer = "The answer is 1,234,567"
        corrected = self.validator.validate_and_correct(answer, question=question)
        assert corrected == "1234567"

    def test_preserves_normal_answer(self):
        answer = "Paris"
        corrected = self.validator.validate_and_correct(answer)
        assert corrected == "Paris"


class TestCreateFormatValidator:
    """Tests for the validator factory function."""

    def test_creates_validator_instance(self):
        validator = create_format_validator()
        assert isinstance(validator, OutputFormatValidator)

    def test_validator_is_functional(self):
        validator = create_format_validator()
        reqs = validator.extract_format_requirements("without commas")
        assert reqs.number_format == NumberFormat.PLAIN
