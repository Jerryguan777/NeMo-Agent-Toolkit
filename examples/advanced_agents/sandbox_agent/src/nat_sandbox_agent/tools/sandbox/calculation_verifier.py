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

"""Calculation verification tools to address reasoning_error failures.

This module provides tools to independently verify mathematical calculations
and trace reasoning chains, addressing the 28.6% reasoning_error failure category.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from nat_sandbox_agent.tools.sandbox.executor import SandboxToolExecutor


class CalculationInput(BaseModel):
    """Input schema for calculation verification."""

    expression: str = Field(
        description="Mathematical expression to evaluate (e.g., '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)')"
    )
    expected_result: float | str | None = Field(
        default=None,
        description="Expected result to verify against (optional)"
    )
    precision: int = Field(
        default=6,
        description="Number of decimal places for comparison"
    )


class FormulaInput(BaseModel):
    """Input schema for formula verification."""

    formula_name: str = Field(
        description="Name of the formula (e.g., 'michaelis_menten', 'quadratic', 'compound_interest')"
    )
    variables: dict[str, float] = Field(
        description="Dictionary of variable values (e.g., {'Vmax': 100, 'Km': 10, 'S': 50})"
    )
    expected_result: float | None = Field(
        default=None,
        description="Expected result to verify against (optional)"
    )


class ReasoningTraceInput(BaseModel):
    """Input schema for reasoning trace."""

    steps: list[str] = Field(
        description="List of reasoning steps as strings"
    )
    check_consistency: bool = Field(
        default=True,
        description="Whether to check for logical consistency between steps"
    )


@dataclass
class VerificationResult:
    """Result of a verification operation."""

    verified: bool
    calculated_value: Any
    expected_value: Any | None
    difference: float | None
    within_tolerance: bool
    details: str


class CalculationVerifier:
    """Verifies mathematical and logical calculations.

    This class provides:
    - Expression evaluation using safe Python eval
    - Formula verification with common scientific formulas
    - Reasoning chain tracing and consistency checking

    It addresses the reasoning_error failure category by providing
    independent verification of calculations.
    """

    # Common formulas that can be verified
    KNOWN_FORMULAS = {
        "michaelis_menten": {
            "description": "Michaelis-Menten enzyme kinetics: v = (Vmax * S) / (Km + S)",
            "variables": ["Vmax", "Km", "S"],
            "formula": lambda v: (v["Vmax"] * v["S"]) / (v["Km"] + v["S"]),
        },
        "quadratic_positive": {
            "description": "Quadratic formula positive root: (-b + sqrt(b^2 - 4ac)) / (2a)",
            "variables": ["a", "b", "c"],
            "formula": lambda v: (-v["b"] + (v["b"]**2 - 4*v["a"]*v["c"])**0.5) / (2*v["a"]),
        },
        "quadratic_negative": {
            "description": "Quadratic formula negative root: (-b - sqrt(b^2 - 4ac)) / (2a)",
            "variables": ["a", "b", "c"],
            "formula": lambda v: (-v["b"] - (v["b"]**2 - 4*v["a"]*v["c"])**0.5) / (2*v["a"]),
        },
        "compound_interest": {
            "description": "Compound interest: A = P * (1 + r/n)^(n*t)",
            "variables": ["P", "r", "n", "t"],
            "formula": lambda v: v["P"] * (1 + v["r"]/v["n"]) ** (v["n"]*v["t"]),
        },
        "simple_interest": {
            "description": "Simple interest: A = P * (1 + r*t)",
            "variables": ["P", "r", "t"],
            "formula": lambda v: v["P"] * (1 + v["r"]*v["t"]),
        },
        "pythagorean": {
            "description": "Pythagorean theorem: c = sqrt(a^2 + b^2)",
            "variables": ["a", "b"],
            "formula": lambda v: (v["a"]**2 + v["b"]**2)**0.5,
        },
        "distance": {
            "description": "Distance formula: d = sqrt((x2-x1)^2 + (y2-y1)^2)",
            "variables": ["x1", "y1", "x2", "y2"],
            "formula": lambda v: ((v["x2"]-v["x1"])**2 + (v["y2"]-v["y1"])**2)**0.5,
        },
        "percentage_change": {
            "description": "Percentage change: ((new - old) / old) * 100",
            "variables": ["old", "new"],
            "formula": lambda v: ((v["new"] - v["old"]) / v["old"]) * 100,
        },
        "bmi": {
            "description": "Body Mass Index: weight(kg) / height(m)^2",
            "variables": ["weight", "height"],
            "formula": lambda v: v["weight"] / (v["height"]**2),
        },
        "celsius_to_fahrenheit": {
            "description": "Celsius to Fahrenheit: F = C * 9/5 + 32",
            "variables": ["C"],
            "formula": lambda v: v["C"] * 9/5 + 32,
        },
        "fahrenheit_to_celsius": {
            "description": "Fahrenheit to Celsius: C = (F - 32) * 5/9",
            "variables": ["F"],
            "formula": lambda v: (v["F"] - 32) * 5/9,
        },
    }

    def verify_calculation(
        self,
        expression: str,
        expected_result: float | str | None = None,
        precision: int = 6,
    ) -> str:
        """Verify a mathematical calculation.

        Args:
            expression: Mathematical expression to evaluate.
            expected_result: Expected result to compare against.
            precision: Decimal places for comparison.

        Returns:
            JSON string with verification result.
        """
        result = {
            "success": False,
            "expression": expression,
            "calculated_value": None,
            "expected_value": expected_result,
            "verified": False,
            "difference": None,
            "details": "",
            "warnings": [],
        }

        try:
            # Prepare safe evaluation environment
            import math
            safe_env = {
                # Math functions
                "sqrt": math.sqrt,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "log": math.log,
                "log10": math.log10,
                "log2": math.log2,
                "exp": math.exp,
                "pow": pow,
                "abs": abs,
                "round": round,
                "floor": math.floor,
                "ceil": math.ceil,
                # Constants
                "pi": math.pi,
                "e": math.e,
                # Safe builtins
                "sum": sum,
                "min": min,
                "max": max,
                "len": len,
            }

            # Sanitize expression
            sanitized = self._sanitize_expression(expression)

            # Evaluate
            calculated = eval(sanitized, {"__builtins__": {}}, safe_env)
            result["calculated_value"] = calculated
            result["success"] = True

            # Compare with expected if provided
            if expected_result is not None:
                try:
                    expected_num = float(expected_result) if isinstance(expected_result, str) else expected_result
                    diff = abs(calculated - expected_num)
                    result["difference"] = round(diff, precision)

                    # Check if within tolerance
                    tolerance = 10 ** (-precision)
                    result["verified"] = diff < tolerance or (expected_num != 0 and diff / abs(expected_num) < tolerance)

                    if result["verified"]:
                        result["details"] = f"Calculation verified: {calculated} matches expected {expected_num}"
                    else:
                        result["details"] = f"Mismatch: calculated {calculated}, expected {expected_num}, difference {diff}"

                except (ValueError, TypeError) as e:
                    result["warnings"].append(f"Could not compare with expected value: {e}")
            else:
                result["details"] = f"Calculation successful: {expression} = {calculated}"

        except Exception as e:
            result["details"] = f"Evaluation error: {str(e)}"
            result["warnings"].append(str(e))

        return json.dumps(result, ensure_ascii=False, indent=2)

    def _sanitize_expression(self, expression: str) -> str:
        """Sanitize expression for safe evaluation."""
        # Remove potentially dangerous patterns
        dangerous = ["import", "exec", "eval", "__", "open", "file", "os.", "sys."]
        sanitized = expression
        for d in dangerous:
            if d in sanitized.lower():
                raise ValueError(f"Potentially unsafe pattern detected: {d}")

        # Replace common mathematical notation
        sanitized = sanitized.replace("^", "**")  # Power notation
        sanitized = sanitized.replace("×", "*")
        sanitized = sanitized.replace("÷", "/")

        return sanitized

    def verify_formula(
        self,
        formula_name: str,
        variables: dict[str, float],
        expected_result: float | None = None,
    ) -> str:
        """Verify a calculation using a known formula.

        Args:
            formula_name: Name of the formula to use.
            variables: Dictionary of variable values.
            expected_result: Expected result to compare against.

        Returns:
            JSON string with verification result.
        """
        result = {
            "success": False,
            "formula_name": formula_name,
            "variables": variables,
            "calculated_value": None,
            "expected_value": expected_result,
            "verified": False,
            "formula_description": "",
            "required_variables": [],
            "available_formulas": list(self.KNOWN_FORMULAS.keys()),
            "warnings": [],
        }

        if formula_name not in self.KNOWN_FORMULAS:
            result["warnings"].append(f"Unknown formula: {formula_name}")
            return json.dumps(result, ensure_ascii=False, indent=2)

        formula_info = self.KNOWN_FORMULAS[formula_name]
        result["formula_description"] = formula_info["description"]
        result["required_variables"] = formula_info["variables"]

        # Check for missing variables
        missing = [v for v in formula_info["variables"] if v not in variables]
        if missing:
            result["warnings"].append(f"Missing variables: {missing}")
            return json.dumps(result, ensure_ascii=False, indent=2)

        try:
            calculated = formula_info["formula"](variables)
            result["calculated_value"] = calculated
            result["success"] = True

            if expected_result is not None:
                diff = abs(calculated - expected_result)
                result["difference"] = diff
                # Use relative tolerance: 0.01% of expected value, minimum 1e-6
                tolerance = max(1e-6, abs(expected_result) * 1e-4)
                result["verified"] = diff < tolerance

                if result["verified"]:
                    result["details"] = f"Formula verified: {calculated} matches expected {expected_result}"
                else:
                    result["details"] = f"Mismatch: calculated {calculated}, expected {expected_result}"
            else:
                result["details"] = f"Calculation successful using {formula_name}"

        except Exception as e:
            result["warnings"].append(f"Calculation error: {str(e)}")

        return json.dumps(result, ensure_ascii=False, indent=2)

    def trace_reasoning(
        self,
        steps: list[str],
        check_consistency: bool = True,
    ) -> str:
        """Trace and analyze a reasoning chain.

        Args:
            steps: List of reasoning steps.
            check_consistency: Whether to check for consistency.

        Returns:
            JSON string with reasoning trace analysis.
        """
        result = {
            "success": True,
            "step_count": len(steps),
            "steps_analysis": [],
            "potential_issues": [],
            "consistency_check": None,
            "summary": "",
        }

        # Analyze each step
        for i, step in enumerate(steps):
            step_analysis = {
                "index": i,
                "step": step[:200],  # Truncate for readability
                "contains_numbers": bool(re.search(r'\d+', step)),
                "contains_conclusion_markers": any(
                    marker in step.lower()
                    for marker in ["therefore", "thus", "so", "hence", "because", "since"]
                ),
                "contains_uncertainty": any(
                    marker in step.lower()
                    for marker in ["maybe", "might", "possibly", "perhaps", "could be", "uncertain"]
                ),
            }

            # Extract any numbers mentioned
            numbers = re.findall(r'[-+]?[\d,]+\.?\d*', step)
            step_analysis["numbers_mentioned"] = numbers[:5]  # Limit to first 5

            result["steps_analysis"].append(step_analysis)

        # Check for potential issues
        issues = []

        # Check for sudden changes in numbers (potential calculation errors)
        all_numbers = []
        for analysis in result["steps_analysis"]:
            all_numbers.extend(analysis.get("numbers_mentioned", []))

        # Check for uncertainty in conclusions
        for analysis in result["steps_analysis"]:
            if analysis["contains_conclusion_markers"] and analysis["contains_uncertainty"]:
                issues.append({
                    "type": "uncertain_conclusion",
                    "step_index": analysis["index"],
                    "description": "Conclusion step contains uncertainty markers"
                })

        # Check for missing intermediate steps
        if len(steps) < 3 and any(a["contains_numbers"] for a in result["steps_analysis"]):
            issues.append({
                "type": "potentially_missing_steps",
                "description": "Complex calculation with few steps - consider adding intermediate steps"
            })

        result["potential_issues"] = issues

        # Consistency check
        if check_consistency and len(steps) >= 2:
            result["consistency_check"] = {
                "checked": True,
                "issues_found": len(issues),
                "recommendation": (
                    "Review flagged steps" if issues
                    else "Reasoning chain appears consistent"
                )
            }

        # Summary
        if issues:
            result["summary"] = f"Found {len(issues)} potential issues in reasoning chain"
        else:
            result["summary"] = f"Reasoning chain with {len(steps)} steps appears sound"

        return json.dumps(result, ensure_ascii=False, indent=2)


def create_calculation_verifier_tools(
    executor: SandboxToolExecutor,
) -> list[StructuredTool]:
    """Create calculation verification tools.

    Args:
        executor: The sandbox tool executor (for consistency with other tools).

    Returns:
        List of calculation verification tools.
    """
    verifier = CalculationVerifier()

    def verify_calculation_fn(
        expression: str,
        expected_result: float | str | None = None,
        precision: int = 6,
    ) -> str:
        """Verify a mathematical calculation."""
        return verifier.verify_calculation(expression, expected_result, precision)

    def verify_formula_fn(
        formula_name: str,
        variables: dict[str, float],
        expected_result: float | None = None,
    ) -> str:
        """Verify a calculation using a known formula."""
        return verifier.verify_formula(formula_name, variables, expected_result)

    def trace_reasoning_fn(
        steps: list[str],
        check_consistency: bool = True,
    ) -> str:
        """Trace and analyze a reasoning chain."""
        return verifier.trace_reasoning(steps, check_consistency)

    return [
        StructuredTool.from_function(
            func=verify_calculation_fn,
            name="verify_calculation",
            description=(
                "Verify a mathematical calculation by independently evaluating it. "
                "Use this to double-check your math. "
                "Supports common math functions (sqrt, sin, cos, log, etc.) and constants (pi, e). "
                "Optionally provide an expected result to verify against."
            ),
            args_schema=CalculationInput,
        ),
        StructuredTool.from_function(
            func=verify_formula_fn,
            name="verify_formula",
            description=(
                "Verify a calculation using a known scientific/mathematical formula. "
                "Available formulas: michaelis_menten, quadratic_positive, quadratic_negative, "
                "compound_interest, simple_interest, pythagorean, distance, percentage_change, "
                "bmi, celsius_to_fahrenheit, fahrenheit_to_celsius. "
                "Provide variable values as a dictionary."
            ),
            args_schema=FormulaInput,
        ),
        StructuredTool.from_function(
            func=trace_reasoning_fn,
            name="trace_reasoning",
            description=(
                "Trace and analyze a multi-step reasoning chain. "
                "Use this to check for logical consistency in your reasoning. "
                "Identifies potential issues like uncertain conclusions or missing steps."
            ),
            args_schema=ReasoningTraceInput,
        ),
    ]
