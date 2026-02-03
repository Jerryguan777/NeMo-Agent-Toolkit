# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for calculation verification tools."""

import json
import pytest

from nat_sandbox_agent.tools.sandbox.calculation_verifier import (
    CalculationVerifier,
)


class TestCalculationVerification:
    """Tests for basic calculation verification."""

    def setup_method(self):
        self.verifier = CalculationVerifier()

    def test_simple_arithmetic(self):
        result = json.loads(self.verifier.verify_calculation("2 + 3"))
        assert result["success"] is True
        assert result["calculated_value"] == 5

    def test_multiplication(self):
        result = json.loads(self.verifier.verify_calculation("4 * 5"))
        assert result["success"] is True
        assert result["calculated_value"] == 20

    def test_division(self):
        result = json.loads(self.verifier.verify_calculation("10 / 2"))
        assert result["success"] is True
        assert result["calculated_value"] == 5.0

    def test_power_notation(self):
        result = json.loads(self.verifier.verify_calculation("2^3"))
        assert result["success"] is True
        assert result["calculated_value"] == 8

    def test_sqrt_function(self):
        result = json.loads(self.verifier.verify_calculation("sqrt(16)"))
        assert result["success"] is True
        assert result["calculated_value"] == 4.0

    def test_trigonometric_function(self):
        result = json.loads(self.verifier.verify_calculation("sin(0)"))
        assert result["success"] is True
        assert abs(result["calculated_value"]) < 0.0001

    def test_pi_constant(self):
        result = json.loads(self.verifier.verify_calculation("pi"))
        assert result["success"] is True
        assert abs(result["calculated_value"] - 3.14159) < 0.001

    def test_complex_expression(self):
        result = json.loads(self.verifier.verify_calculation("(2 + 3) * 4 / 2"))
        assert result["success"] is True
        assert result["calculated_value"] == 10.0

    def test_verify_correct_result(self):
        result = json.loads(self.verifier.verify_calculation("2 + 2", expected_result=4))
        assert result["success"] is True
        assert result["verified"] is True

    def test_verify_incorrect_result(self):
        result = json.loads(self.verifier.verify_calculation("2 + 2", expected_result=5))
        assert result["success"] is True
        assert result["verified"] is False

    def test_precision_in_verification(self):
        result = json.loads(
            self.verifier.verify_calculation("1/3", expected_result=0.333333, precision=5)
        )
        assert result["verified"] is True

    def test_dangerous_expression_blocked(self):
        result = json.loads(self.verifier.verify_calculation("import os"))
        assert result["success"] is False
        assert any("unsafe" in w.lower() for w in result["warnings"])


class TestFormulaVerification:
    """Tests for known formula verification."""

    def setup_method(self):
        self.verifier = CalculationVerifier()

    def test_michaelis_menten(self):
        # v = (Vmax * S) / (Km + S)
        # With Vmax=100, Km=10, S=50: v = (100 * 50) / (10 + 50) = 5000/60 = 83.33...
        result = json.loads(
            self.verifier.verify_formula(
                "michaelis_menten",
                {"Vmax": 100, "Km": 10, "S": 50}
            )
        )
        assert result["success"] is True
        assert abs(result["calculated_value"] - 83.333) < 0.01

    def test_michaelis_menten_with_expected(self):
        # v = (100 * 50) / (10 + 50) = 5000/60 = 83.3333...
        result = json.loads(
            self.verifier.verify_formula(
                "michaelis_menten",
                {"Vmax": 100, "Km": 10, "S": 50},
                expected_result=83.33333333  # More precise expected value
            )
        )
        assert result["verified"] is True

    def test_quadratic_formula_positive(self):
        # x^2 - 5x + 6 = 0: roots are 2 and 3
        # (-b + sqrt(b^2 - 4ac)) / 2a = (5 + sqrt(25-24)) / 2 = (5 + 1) / 2 = 3
        result = json.loads(
            self.verifier.verify_formula(
                "quadratic_positive",
                {"a": 1, "b": -5, "c": 6}
            )
        )
        assert result["success"] is True
        assert abs(result["calculated_value"] - 3) < 0.001

    def test_compound_interest(self):
        # A = P * (1 + r/n)^(n*t)
        # P=1000, r=0.05, n=12, t=1: A = 1000 * (1 + 0.05/12)^12 ≈ 1051.16
        result = json.loads(
            self.verifier.verify_formula(
                "compound_interest",
                {"P": 1000, "r": 0.05, "n": 12, "t": 1}
            )
        )
        assert result["success"] is True
        assert abs(result["calculated_value"] - 1051.16) < 0.1

    def test_pythagorean(self):
        # c = sqrt(3^2 + 4^2) = sqrt(9 + 16) = sqrt(25) = 5
        result = json.loads(
            self.verifier.verify_formula(
                "pythagorean",
                {"a": 3, "b": 4}
            )
        )
        assert result["success"] is True
        assert result["calculated_value"] == 5.0

    def test_percentage_change(self):
        # ((new - old) / old) * 100 = ((150 - 100) / 100) * 100 = 50%
        result = json.loads(
            self.verifier.verify_formula(
                "percentage_change",
                {"old": 100, "new": 150}
            )
        )
        assert result["success"] is True
        assert result["calculated_value"] == 50.0

    def test_celsius_to_fahrenheit(self):
        # F = C * 9/5 + 32 = 0 * 9/5 + 32 = 32
        result = json.loads(
            self.verifier.verify_formula(
                "celsius_to_fahrenheit",
                {"C": 0}
            )
        )
        assert result["success"] is True
        assert result["calculated_value"] == 32.0

    def test_fahrenheit_to_celsius(self):
        # C = (F - 32) * 5/9 = (212 - 32) * 5/9 = 100
        result = json.loads(
            self.verifier.verify_formula(
                "fahrenheit_to_celsius",
                {"F": 212}
            )
        )
        assert result["success"] is True
        assert result["calculated_value"] == 100.0

    def test_unknown_formula(self):
        result = json.loads(
            self.verifier.verify_formula(
                "unknown_formula",
                {"x": 1}
            )
        )
        assert result["success"] is False
        assert "Unknown formula" in result["warnings"][0]

    def test_missing_variables(self):
        result = json.loads(
            self.verifier.verify_formula(
                "michaelis_menten",
                {"Vmax": 100}  # Missing Km and S
            )
        )
        assert result["success"] is False
        assert "Missing variables" in result["warnings"][0]

    def test_available_formulas_listed(self):
        result = json.loads(
            self.verifier.verify_formula("unknown", {})
        )
        assert "available_formulas" in result
        assert "michaelis_menten" in result["available_formulas"]
        assert "quadratic_positive" in result["available_formulas"]


class TestReasoningTrace:
    """Tests for reasoning chain tracing."""

    def setup_method(self):
        self.verifier = CalculationVerifier()

    def test_trace_simple_chain(self):
        steps = [
            "The question asks for the sum of 2 and 3.",
            "2 + 3 = 5",
            "Therefore, the answer is 5."
        ]
        result = json.loads(self.verifier.trace_reasoning(steps))

        assert result["success"] is True
        assert result["step_count"] == 3

    def test_detects_numbers_in_steps(self):
        steps = [
            "First, we calculate 100 / 4.",
            "This gives us 25.",
        ]
        result = json.loads(self.verifier.trace_reasoning(steps))

        assert result["steps_analysis"][0]["contains_numbers"] is True
        assert result["steps_analysis"][1]["contains_numbers"] is True

    def test_detects_conclusion_markers(self):
        steps = [
            "We have the values.",
            "Therefore, the result is 42."
        ]
        result = json.loads(self.verifier.trace_reasoning(steps))

        assert result["steps_analysis"][1]["contains_conclusion_markers"] is True

    def test_detects_uncertainty(self):
        steps = [
            "The value might be around 100.",
            "Maybe the answer is 95."
        ]
        result = json.loads(self.verifier.trace_reasoning(steps))

        assert result["steps_analysis"][0]["contains_uncertainty"] is True
        assert result["steps_analysis"][1]["contains_uncertainty"] is True

    def test_flags_uncertain_conclusions(self):
        steps = [
            "We calculated the value.",
            "Therefore, the answer might be 42."  # Uncertain conclusion
        ]
        result = json.loads(self.verifier.trace_reasoning(steps))

        # Should flag this as an issue
        assert any(
            issue["type"] == "uncertain_conclusion"
            for issue in result["potential_issues"]
        )

    def test_consistency_check_included(self):
        steps = ["Step 1", "Step 2"]
        result = json.loads(self.verifier.trace_reasoning(steps, check_consistency=True))

        assert result["consistency_check"] is not None
        assert result["consistency_check"]["checked"] is True

    def test_summary_generated(self):
        steps = ["Step 1", "Step 2", "Step 3"]
        result = json.loads(self.verifier.trace_reasoning(steps))

        assert "summary" in result
        assert "3 steps" in result["summary"]
