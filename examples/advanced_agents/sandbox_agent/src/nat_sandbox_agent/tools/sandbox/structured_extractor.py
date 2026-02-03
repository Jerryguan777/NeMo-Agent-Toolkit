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

"""Structured data extraction tools for tables, lists, and other structured content.

This module addresses the 38.8% evidence_extraction failure category by providing
specialized tools for accurate extraction of structured data from HTML, Markdown,
and other formats.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from nat_sandbox_agent.tools.sandbox.executor import SandboxToolExecutor


class TableExtractionInput(BaseModel):
    """Input schema for table extraction."""

    content: str = Field(
        description="HTML or Markdown content containing the table"
    )
    table_index: int = Field(
        default=0,
        description="Index of the table to extract (0-based). Use 0 for the first table."
    )
    headers: list[str] | None = Field(
        default=None,
        description="Specific column headers to extract. If None, extracts all columns."
    )
    row_filter: str | None = Field(
        default=None,
        description="Filter rows containing this text in any column."
    )


class ListExtractionInput(BaseModel):
    """Input schema for list extraction."""

    content: str = Field(
        description="HTML or Markdown content containing the list"
    )
    list_index: int = Field(
        default=0,
        description="Index of the list to extract (0-based)."
    )
    list_type: str = Field(
        default="any",
        description="Type of list: 'ordered', 'unordered', or 'any'."
    )
    include_nested: bool = Field(
        default=True,
        description="Whether to include nested list items."
    )


class DataVerificationInput(BaseModel):
    """Input schema for data verification."""

    extracted_value: str = Field(
        description="The extracted value to verify"
    )
    source_content: str = Field(
        description="The original source content"
    )
    context_hint: str | None = Field(
        default=None,
        description="Hint about what the value represents (e.g., 'population of Tokyo')"
    )


@dataclass
class ExtractionResult:
    """Result of a data extraction operation."""

    success: bool
    data: Any
    confidence: float
    source_location: str  # Description of where in source the data was found
    warnings: list[str]


class StructuredDataExtractor:
    """Specialized extractor for structured data from various formats.

    This class provides accurate extraction of:
    - Tables (HTML and Markdown)
    - Lists (ordered and unordered)
    - Key-value pairs
    - Nested structures

    It addresses the evidence_extraction failure category by:
    1. Precisely targeting specific elements
    2. Verifying extraction accuracy
    3. Providing confidence scores
    """

    def extract_table(
        self,
        content: str,
        table_index: int = 0,
        headers: list[str] | None = None,
        row_filter: str | None = None,
    ) -> str:
        """Extract a table from HTML or Markdown content.

        Args:
            content: HTML or Markdown content.
            table_index: Index of table to extract (0-based).
            headers: Specific columns to extract.
            row_filter: Filter rows containing this text.

        Returns:
            JSON string with extracted table data.
        """
        result = {
            "success": False,
            "table": [],
            "headers": [],
            "row_count": 0,
            "warnings": [],
        }

        try:
            # Try HTML table extraction first
            tables = self._extract_html_tables(content)

            if not tables:
                # Fall back to Markdown table extraction
                tables = self._extract_markdown_tables(content)

            if not tables:
                result["warnings"].append("No tables found in content")
                return json.dumps(result, ensure_ascii=False)

            if table_index >= len(tables):
                result["warnings"].append(
                    f"Table index {table_index} out of range. Found {len(tables)} tables."
                )
                table_index = 0

            table = tables[table_index]
            extracted_headers = table.get("headers", [])
            rows = table.get("rows", [])

            # Filter columns if headers specified
            if headers:
                col_indices = []
                for h in headers:
                    for i, eh in enumerate(extracted_headers):
                        if h.lower() in eh.lower():
                            col_indices.append(i)
                            break

                if col_indices:
                    extracted_headers = [extracted_headers[i] for i in col_indices if i < len(extracted_headers)]
                    rows = [
                        [row[i] for i in col_indices if i < len(row)]
                        for row in rows
                    ]

            # Filter rows if filter specified
            if row_filter:
                filtered_rows = []
                for row in rows:
                    if any(row_filter.lower() in str(cell).lower() for cell in row):
                        filtered_rows.append(row)
                rows = filtered_rows

            result["success"] = True
            result["headers"] = extracted_headers
            result["table"] = rows
            result["row_count"] = len(rows)
            result["total_tables_found"] = len(tables)

        except Exception as e:
            result["warnings"].append(f"Extraction error: {str(e)}")

        return json.dumps(result, ensure_ascii=False, indent=2)

    def _extract_html_tables(self, content: str) -> list[dict[str, Any]]:
        """Extract tables from HTML content."""
        tables = []

        # Find all table elements
        table_pattern = re.compile(r'<table[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
        table_matches = table_pattern.findall(content)

        for table_html in table_matches:
            table_data: dict[str, Any] = {"headers": [], "rows": []}

            # Extract headers from thead or first tr with th elements
            header_pattern = re.compile(r'<th[^>]*>(.*?)</th>', re.DOTALL | re.IGNORECASE)
            headers = header_pattern.findall(table_html)

            if headers:
                table_data["headers"] = [self._clean_html(h) for h in headers]

            # Extract rows
            row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
            rows = row_pattern.findall(table_html)

            for row in rows:
                # Skip header row if already extracted
                if '<th' in row.lower():
                    continue

                cell_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE)
                cells = cell_pattern.findall(row)

                if cells:
                    table_data["rows"].append([self._clean_html(c) for c in cells])

            if table_data["headers"] or table_data["rows"]:
                # If no headers but have rows, use first row as headers
                if not table_data["headers"] and table_data["rows"]:
                    table_data["headers"] = table_data["rows"][0]
                    table_data["rows"] = table_data["rows"][1:]

                tables.append(table_data)

        return tables

    def _extract_markdown_tables(self, content: str) -> list[dict[str, Any]]:
        """Extract tables from Markdown content."""
        tables = []

        # Split by lines and find table blocks
        lines = content.split('\n')
        current_table: dict[str, Any] | None = None

        for i, line in enumerate(lines):
            line = line.strip()

            # Check if line looks like a table row
            if '|' in line and line.startswith('|') and line.endswith('|'):
                cells = [c.strip() for c in line.split('|')[1:-1]]

                # Check if this is a separator row (---|---|---)
                if all(re.match(r'^:?-+:?$', c) for c in cells if c):
                    continue

                if current_table is None:
                    # Start new table, first row is headers
                    current_table = {"headers": cells, "rows": []}
                else:
                    current_table["rows"].append(cells)

            elif current_table is not None:
                # End of table block
                tables.append(current_table)
                current_table = None

        # Don't forget last table
        if current_table is not None:
            tables.append(current_table)

        return tables

    def _clean_html(self, html: str) -> str:
        """Remove HTML tags and clean text."""
        # Remove tags
        text = re.sub(r'<[^>]+>', '', html)
        # Decode common entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        # Clean whitespace
        text = ' '.join(text.split())
        return text.strip()

    def extract_list(
        self,
        content: str,
        list_index: int = 0,
        list_type: str = "any",
        include_nested: bool = True,
    ) -> str:
        """Extract a list from HTML or Markdown content.

        Args:
            content: HTML or Markdown content.
            list_index: Index of list to extract (0-based).
            list_type: Type of list ('ordered', 'unordered', 'any').
            include_nested: Whether to include nested items.

        Returns:
            JSON string with extracted list items.
        """
        result = {
            "success": False,
            "items": [],
            "list_type": "",
            "warnings": [],
        }

        try:
            lists = []

            # Extract HTML lists
            if list_type in ("any", "unordered"):
                ul_pattern = re.compile(r'<ul[^>]*>(.*?)</ul>', re.DOTALL | re.IGNORECASE)
                for ul_content in ul_pattern.findall(content):
                    items = self._extract_list_items(ul_content, include_nested)
                    if items:
                        lists.append({"type": "unordered", "items": items})

            if list_type in ("any", "ordered"):
                ol_pattern = re.compile(r'<ol[^>]*>(.*?)</ol>', re.DOTALL | re.IGNORECASE)
                for ol_content in ol_pattern.findall(content):
                    items = self._extract_list_items(ol_content, include_nested)
                    if items:
                        lists.append({"type": "ordered", "items": items})

            # Extract Markdown lists
            md_lists = self._extract_markdown_lists(content, list_type)
            lists.extend(md_lists)

            if not lists:
                result["warnings"].append("No lists found in content")
                return json.dumps(result, ensure_ascii=False)

            if list_index >= len(lists):
                result["warnings"].append(
                    f"List index {list_index} out of range. Found {len(lists)} lists."
                )
                list_index = 0

            selected_list = lists[list_index]
            result["success"] = True
            result["items"] = selected_list["items"]
            result["list_type"] = selected_list["type"]
            result["total_lists_found"] = len(lists)

        except Exception as e:
            result["warnings"].append(f"Extraction error: {str(e)}")

        return json.dumps(result, ensure_ascii=False, indent=2)

    def _extract_list_items(self, html: str, include_nested: bool) -> list[str]:
        """Extract items from HTML list content."""
        items = []

        if include_nested:
            # Extract all li elements
            li_pattern = re.compile(r'<li[^>]*>(.*?)</li>', re.DOTALL | re.IGNORECASE)
        else:
            # Only extract direct children (more complex regex to exclude nested)
            li_pattern = re.compile(r'<li[^>]*>([^<]*(?:<(?!ul|ol|li)[^>]*>[^<]*)*)</li>', re.DOTALL | re.IGNORECASE)

        for li_content in li_pattern.findall(html):
            clean = self._clean_html(li_content)
            if clean:
                items.append(clean)

        return items

    def _extract_markdown_lists(self, content: str, list_type: str) -> list[dict[str, Any]]:
        """Extract lists from Markdown content."""
        lists = []
        lines = content.split('\n')

        current_list: dict[str, Any] | None = None
        current_type = ""

        for line in lines:
            stripped = line.lstrip()

            # Check for unordered list item
            unordered_match = re.match(r'^[-*+]\s+(.+)$', stripped)
            # Check for ordered list item
            ordered_match = re.match(r'^\d+\.\s+(.+)$', stripped)

            if unordered_match and list_type in ("any", "unordered"):
                if current_type != "unordered" and current_list is not None:
                    lists.append(current_list)
                    current_list = None

                if current_list is None:
                    current_list = {"type": "unordered", "items": []}
                    current_type = "unordered"

                current_list["items"].append(unordered_match.group(1).strip())

            elif ordered_match and list_type in ("any", "ordered"):
                if current_type != "ordered" and current_list is not None:
                    lists.append(current_list)
                    current_list = None

                if current_list is None:
                    current_list = {"type": "ordered", "items": []}
                    current_type = "ordered"

                current_list["items"].append(ordered_match.group(1).strip())

            elif not stripped and current_list is not None:
                # Empty line ends current list
                lists.append(current_list)
                current_list = None
                current_type = ""

        if current_list is not None:
            lists.append(current_list)

        return lists

    def verify_extraction(
        self,
        extracted_value: str,
        source_content: str,
        context_hint: str | None = None,
    ) -> str:
        """Verify that an extracted value matches the source content.

        Args:
            extracted_value: The value that was extracted.
            source_content: The original source content.
            context_hint: Optional hint about what the value represents.

        Returns:
            JSON string with verification result.
        """
        result = {
            "verified": False,
            "confidence": 0.0,
            "found_in_source": False,
            "exact_match": False,
            "similar_values": [],
            "warnings": [],
        }

        try:
            # Normalize values for comparison
            normalized_value = self._normalize_value(extracted_value)
            normalized_source = source_content.lower()

            # Check for exact presence in source
            if normalized_value in normalized_source:
                result["found_in_source"] = True
                result["exact_match"] = True
                result["confidence"] = 1.0

            # Check for numeric equivalence
            if not result["exact_match"]:
                extracted_num = self._extract_number(extracted_value)
                if extracted_num is not None:
                    # Find all numbers in source
                    source_numbers = self._find_all_numbers(source_content)
                    for num, context in source_numbers:
                        if abs(num - extracted_num) < 0.001 * abs(extracted_num + 0.001):
                            result["found_in_source"] = True
                            result["confidence"] = 0.9
                            result["similar_values"].append({
                                "value": str(num),
                                "context": context[:100],
                            })
                            break

            # If context hint provided, check for related content
            if context_hint and not result["found_in_source"]:
                hint_words = context_hint.lower().split()
                hint_found = sum(1 for w in hint_words if w in normalized_source)
                if hint_found >= len(hint_words) * 0.5:
                    result["confidence"] = max(result["confidence"], 0.5)
                    result["warnings"].append(
                        "Context hint found in source but extracted value not directly verified"
                    )

            result["verified"] = result["confidence"] >= 0.7

        except Exception as e:
            result["warnings"].append(f"Verification error: {str(e)}")

        return json.dumps(result, ensure_ascii=False, indent=2)

    def _normalize_value(self, value: str) -> str:
        """Normalize a value for comparison."""
        # Remove commas from numbers
        normalized = re.sub(r'(\d),(\d)', r'\1\2', value)
        # Convert to lowercase
        normalized = normalized.lower().strip()
        return normalized

    def _extract_number(self, text: str) -> float | None:
        """Extract a number from text."""
        # Remove commas
        cleaned = text.replace(',', '')
        # Try to find a number
        match = re.search(r'[-+]?[\d.]+(?:[eE][-+]?\d+)?', cleaned)
        if match:
            try:
                return float(match.group())
            except ValueError:
                return None
        return None

    def _find_all_numbers(self, text: str) -> list[tuple[float, str]]:
        """Find all numbers in text with their context."""
        results = []
        # Pattern to match numbers with surrounding context
        pattern = re.compile(r'(.{0,30})([-+]?[\d,]+\.?\d*(?:[eE][-+]?\d+)?)(.{0,30})')

        for match in pattern.finditer(text):
            num_str = match.group(2).replace(',', '')
            try:
                num = float(num_str)
                context = f"{match.group(1)}{match.group(2)}{match.group(3)}"
                results.append((num, context))
            except ValueError:
                continue

        return results


def create_structured_extractor_tools(
    executor: SandboxToolExecutor,
) -> list[StructuredTool]:
    """Create structured data extraction tools.

    Args:
        executor: The sandbox tool executor (for consistency with other tools).

    Returns:
        List of structured extraction tools.
    """
    extractor = StructuredDataExtractor()

    def extract_table_fn(
        content: str,
        table_index: int = 0,
        headers: list[str] | None = None,
        row_filter: str | None = None,
    ) -> str:
        """Extract a table from HTML or Markdown content."""
        return extractor.extract_table(content, table_index, headers, row_filter)

    def extract_list_fn(
        content: str,
        list_index: int = 0,
        list_type: str = "any",
        include_nested: bool = True,
    ) -> str:
        """Extract a list from HTML or Markdown content."""
        return extractor.extract_list(content, list_index, list_type, include_nested)

    def verify_extraction_fn(
        extracted_value: str,
        source_content: str,
        context_hint: str | None = None,
    ) -> str:
        """Verify that an extracted value exists in the source."""
        return extractor.verify_extraction(extracted_value, source_content, context_hint)

    return [
        StructuredTool.from_function(
            func=extract_table_fn,
            name="extract_table",
            description=(
                "Extract a table from HTML or Markdown content. "
                "Use this when you need to accurately extract tabular data. "
                "Returns JSON with headers and rows. "
                "You can filter specific columns by providing 'headers' parameter, "
                "or filter rows containing specific text with 'row_filter'."
            ),
            args_schema=TableExtractionInput,
        ),
        StructuredTool.from_function(
            func=extract_list_fn,
            name="extract_list",
            description=(
                "Extract a list from HTML or Markdown content. "
                "Use this when you need to accurately extract list items. "
                "Returns JSON with list items. "
                "Supports ordered, unordered, or any list type."
            ),
            args_schema=ListExtractionInput,
        ),
        StructuredTool.from_function(
            func=verify_extraction_fn,
            name="verify_extraction",
            description=(
                "Verify that an extracted value is correct by checking against the source. "
                "Use this to double-check that you extracted the right data. "
                "Returns confidence score and verification status."
            ),
            args_schema=DataVerificationInput,
        ),
    ]
