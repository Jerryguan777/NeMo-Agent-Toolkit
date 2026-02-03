# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for structured data extraction tools."""

import json
import pytest

from nat_sandbox_agent.tools.sandbox.structured_extractor import (
    StructuredDataExtractor,
)


class TestTableExtraction:
    """Tests for table extraction functionality."""

    def setup_method(self):
        self.extractor = StructuredDataExtractor()

    def test_extract_html_table(self):
        html = """
        <table>
            <tr><th>Name</th><th>Age</th></tr>
            <tr><td>Alice</td><td>30</td></tr>
            <tr><td>Bob</td><td>25</td></tr>
        </table>
        """
        result = json.loads(self.extractor.extract_table(html))

        assert result["success"] is True
        assert result["headers"] == ["Name", "Age"]
        assert result["row_count"] == 2
        assert result["table"][0] == ["Alice", "30"]
        assert result["table"][1] == ["Bob", "25"]

    def test_extract_markdown_table(self):
        markdown = """
| City | Population |
|------|------------|
| Tokyo | 14000000 |
| Delhi | 11000000 |
"""
        result = json.loads(self.extractor.extract_table(markdown))

        assert result["success"] is True
        assert result["headers"] == ["City", "Population"]
        assert result["row_count"] == 2

    def test_extract_table_with_filter(self):
        html = """
        <table>
            <tr><th>Country</th><th>Capital</th></tr>
            <tr><td>France</td><td>Paris</td></tr>
            <tr><td>Germany</td><td>Berlin</td></tr>
            <tr><td>Italy</td><td>Rome</td></tr>
        </table>
        """
        result = json.loads(self.extractor.extract_table(html, row_filter="Germany"))

        assert result["success"] is True
        assert result["row_count"] == 1
        assert result["table"][0] == ["Germany", "Berlin"]

    def test_extract_specific_columns(self):
        html = """
        <table>
            <tr><th>Name</th><th>Age</th><th>City</th></tr>
            <tr><td>Alice</td><td>30</td><td>NYC</td></tr>
        </table>
        """
        result = json.loads(self.extractor.extract_table(html, headers=["Name", "City"]))

        assert result["success"] is True
        assert result["headers"] == ["Name", "City"]
        # Note: column filtering may include only matched columns

    def test_no_tables_found(self):
        html = "<p>No tables here</p>"
        result = json.loads(self.extractor.extract_table(html))

        assert result["success"] is False
        assert "No tables found" in result["warnings"][0]

    def test_table_index_out_of_range(self):
        html = """
        <table><tr><th>A</th></tr></table>
        """
        result = json.loads(self.extractor.extract_table(html, table_index=5))

        assert "out of range" in result["warnings"][0]


class TestListExtraction:
    """Tests for list extraction functionality."""

    def setup_method(self):
        self.extractor = StructuredDataExtractor()

    def test_extract_html_unordered_list(self):
        html = """
        <ul>
            <li>Apple</li>
            <li>Banana</li>
            <li>Cherry</li>
        </ul>
        """
        result = json.loads(self.extractor.extract_list(html))

        assert result["success"] is True
        assert result["list_type"] == "unordered"
        assert result["items"] == ["Apple", "Banana", "Cherry"]

    def test_extract_html_ordered_list(self):
        html = """
        <ol>
            <li>First</li>
            <li>Second</li>
            <li>Third</li>
        </ol>
        """
        result = json.loads(self.extractor.extract_list(html, list_type="ordered"))

        assert result["success"] is True
        assert result["list_type"] == "ordered"
        assert result["items"] == ["First", "Second", "Third"]

    def test_extract_markdown_unordered_list(self):
        markdown = """
- Item 1
- Item 2
- Item 3
"""
        result = json.loads(self.extractor.extract_list(markdown))

        assert result["success"] is True
        assert result["list_type"] == "unordered"
        assert len(result["items"]) == 3

    def test_extract_markdown_ordered_list(self):
        markdown = """
1. First item
2. Second item
3. Third item
"""
        result = json.loads(self.extractor.extract_list(markdown, list_type="ordered"))

        assert result["success"] is True
        assert result["list_type"] == "ordered"
        assert len(result["items"]) == 3

    def test_no_lists_found(self):
        content = "<p>No lists here</p>"
        result = json.loads(self.extractor.extract_list(content))

        assert result["success"] is False
        assert "No lists found" in result["warnings"][0]


class TestDataVerification:
    """Tests for data verification functionality."""

    def setup_method(self):
        self.extractor = StructuredDataExtractor()

    def test_verify_exact_match(self):
        extracted = "Paris"
        source = "The capital of France is Paris."
        result = json.loads(self.extractor.verify_extraction(extracted, source))

        assert result["verified"] is True
        assert result["found_in_source"] is True
        assert result["exact_match"] is True
        assert result["confidence"] == 1.0

    def test_verify_number_match(self):
        extracted = "1,000,000"
        source = "The population is approximately 1000000 people."
        result = json.loads(self.extractor.verify_extraction(extracted, source))

        assert result["found_in_source"] is True
        assert result["confidence"] >= 0.9

    def test_verify_not_found(self):
        extracted = "Tokyo"
        source = "The capital of France is Paris."
        result = json.loads(self.extractor.verify_extraction(extracted, source))

        assert result["verified"] is False
        assert result["found_in_source"] is False

    def test_verify_with_context_hint(self):
        extracted = "14 million"
        source = "Tokyo has a population of approximately 14,000,000 people."
        result = json.loads(
            self.extractor.verify_extraction(
                extracted, source, context_hint="population of Tokyo"
            )
        )

        assert result["confidence"] > 0


class TestHTMLCleaning:
    """Tests for HTML cleaning functionality."""

    def setup_method(self):
        self.extractor = StructuredDataExtractor()

    def test_clean_html_tags(self):
        html = "<b>Bold</b> and <i>italic</i>"
        cleaned = self.extractor._clean_html(html)
        assert cleaned == "Bold and italic"

    def test_clean_html_entities(self):
        html = "Tom &amp; Jerry"
        cleaned = self.extractor._clean_html(html)
        assert cleaned == "Tom & Jerry"

    def test_clean_whitespace(self):
        html = "  Multiple   spaces  "
        cleaned = self.extractor._clean_html(html)
        assert cleaned == "Multiple spaces"
