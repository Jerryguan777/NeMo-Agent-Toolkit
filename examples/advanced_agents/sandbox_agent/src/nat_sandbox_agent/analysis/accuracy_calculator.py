"""
Accuracy Calculator for Failure Analysis

Compares Plan A and Plan B results against ground truth annotations.
"""

import json
from pathlib import Path
from dataclasses import dataclass


# =============================================================================
# Ground Truth Annotations (from manual analysis of workflow traces)
# =============================================================================

# Updated ground truth based on detailed analysis of each case's workflow trace
GROUND_TRUTH = {
    "e1fc63a2": "output_format",           # 17 vs 17000 - unit conversion error
    "8e867cd7": "evidence_extraction",     # Wrong album count from Wikipedia
    "ec09fa32": "reasoning_error",         # Game theory misunderstanding
    "46719c30": "evidence_extraction",     # Found wrong first paper
    "4b6bb5f7": "tool_limitation",         # PDF download not supported
    "27d5d136": "output_format",           # Truncated/incomplete answer
    "cca530fc": "missing_dependency",      # chess/sklearn not available
    "6f37996b": "reasoning_error",         # Math logic error in counter-examples
    "9318445f": "iteration_limit",         # Explicit "reached maximum steps"
    "cabe07ed": "evidence_extraction",     # Found wrong veterinarian name
    "99c9cc74": "missing_dependency",      # ffmpeg not installed
    "d0633230": "evidence_extraction",     # Wrong predictor from changelog
    "0383a3ee": "output_format",           # "Penguin" instead of "Rockhopper penguin"
    "e142056d": "reasoning_error",         # Game theory calculation error
    "50ad0280": "output_format",           # Uppercase instead of sentence case
    "dc22a632": "evidence_utilization",    # Only extracted "500" not full title
    "1f975693": "missing_dependency",      # ffmpeg not installed
    "50ec8903": "reasoning_error",         # Rubik's cube logic error
    "dc28cf18": "reasoning_error",         # Family counting error
    "72e110e7": "evidence_utilization",    # Access denied, guessed wrong
    "42576abe": "task_understanding",      # Fictional language rules misapplied
    "b415aba4": "output_format",           # "diamond layer" instead of "diamond"
    "935e2cff": "evidence_extraction",     # Wrong policy acronym meaning
    "4b650a35": "task_understanding",      # Followed wrong instruction
    "c714ab3a": "api_content_filter",      # API rejected prompt
    "7673d772": "evidence_extraction",     # Wrong deleted word from amendment
    "c365c1c7": "evidence_extraction",     # Quincy vs Braintree error
    "23dd907f": "evidence_extraction",     # Wrong stanza number
    "a0c07678": "evidence_extraction",     # Wrong pitcher name
}


# =============================================================================
# Related Category Mappings (for fuzzy matching)
# =============================================================================

# Categories that are semantically related (order matters: first is primary)
RELATED_GROUPS = [
    # Task understanding / interpretation errors
    {
        "task_understanding",
        "misinterpretation_error",
        "instruction_parsing_error",
        "contextual_understanding",
    },

    # Output/format errors
    {
        "output_format",
        "constraint_violation",
        "data_entry_error",
    },

    # Code generation / execution errors
    {
        "code_generation",
        "code_quality",
        "algorithmic_error",
        "execution_context",
    },

    # Reasoning / calculation errors
    {
        "reasoning_calculation",
        "reasoning_error",
        "counting_error",
        "data_interpretation_error",
        "data interpretation error",
    },

    # Evidence utilization errors
    {
        "evidence_utilization",
        "evidence_extraction",
        "information_extraction_error",
        "data_extraction_failure",
        "suboptimal_strategy",
        "search_strategy",
    },

    # Tool/environment limitations
    {
        "tool_limitation",
        "environment_limitations",
        "environment_limitation",
        "audio_processing_failure",
    },

    # Missing dependencies
    {
        "missing_dependency",
        "dependency_missing",
        "tool_server_error",  # Often caused by missing deps
    },

    # Data processing errors
    {
        "data_processing_error",
    },

    # Planning errors
    {
        "planning_decomposition",
    },

    # Iteration limits
    {
        "iteration_limit",
    },

    # API content filter
    {
        "api_content_filter",
        "content_policy_violation",
    },
]


def normalize_category(cat: str) -> str:
    """Normalize category name for comparison."""
    return cat.lower().strip().replace(" ", "_").replace("-", "_")


def find_related_group(category: str) -> set:
    """Find the related group for a category."""
    normalized = normalize_category(category)
    for group in RELATED_GROUPS:
        normalized_group = {normalize_category(c) for c in group}
        if normalized in normalized_group:
            return normalized_group
    return {normalized}


def is_exact_match(predicted: str, ground_truth: str) -> bool:
    """Check if prediction exactly matches ground truth."""
    return normalize_category(predicted) == normalize_category(ground_truth)


def is_related_match(predicted: str, ground_truth: str) -> bool:
    """Check if prediction is in the same related group as ground truth."""
    pred_group = find_related_group(predicted)
    gt_group = find_related_group(ground_truth)
    return bool(pred_group & gt_group)


@dataclass
class AccuracyResult:
    """Result of accuracy calculation."""
    total_cases: int
    exact_matches: int
    related_matches: int
    exact_accuracy: float
    related_accuracy: float
    details: list[dict]


def calculate_accuracy(results: list[dict], ground_truth: dict = GROUND_TRUTH) -> AccuracyResult:
    """Calculate accuracy against ground truth."""
    details = []
    exact_matches = 0
    related_matches = 0

    for result in results:
        task_id = result["task_id"]
        task_id_short = task_id[:8]
        predicted = result["category"]

        gt = ground_truth.get(task_id_short)
        if gt is None:
            continue

        exact = is_exact_match(predicted, gt)
        related = is_related_match(predicted, gt)

        if exact:
            exact_matches += 1
        if related:
            related_matches += 1

        details.append({
            "task_id": task_id_short,
            "predicted": predicted,
            "ground_truth": gt,
            "exact_match": exact,
            "related_match": related,
        })

    total = len(details)
    return AccuracyResult(
        total_cases=total,
        exact_matches=exact_matches,
        related_matches=related_matches,
        exact_accuracy=exact_matches / total if total > 0 else 0,
        related_accuracy=related_matches / total if total > 0 else 0,
        details=details,
    )


def run_accuracy_comparison(
    plan_a_path: Path,
    plan_b_path: Path,
    output_path: Path | None = None,
) -> dict:
    """Run accuracy comparison for Plan A and Plan B."""

    with open(plan_a_path) as f:
        plan_a_results = json.load(f)

    with open(plan_b_path) as f:
        plan_b_results = json.load(f)

    acc_a = calculate_accuracy(plan_a_results)
    acc_b = calculate_accuracy(plan_b_results)

    # Print results
    print("=" * 70)
    print("ACCURACY COMPARISON RESULTS")
    print("=" * 70)

    print(f"\n{'Metric':<25} {'Plan A':>15} {'Plan B':>15}")
    print("-" * 55)
    print(f"{'Total Cases':<25} {acc_a.total_cases:>15} {acc_b.total_cases:>15}")
    print(f"{'Exact Matches':<25} {acc_a.exact_matches:>15} {acc_b.exact_matches:>15}")
    print(f"{'Related Matches':<25} {acc_a.related_matches:>15} {acc_b.related_matches:>15}")
    print(f"{'Exact Accuracy':<25} {acc_a.exact_accuracy:>14.1%} {acc_b.exact_accuracy:>14.1%}")
    print(f"{'Related Accuracy':<25} {acc_a.related_accuracy:>14.1%} {acc_b.related_accuracy:>14.1%}")

    # Print detailed comparison
    print("\n" + "=" * 70)
    print("DETAILED COMPARISON")
    print("=" * 70)
    print(f"\n{'Task ID':<10} {'Ground Truth':<22} {'Plan A':<22} {'Plan B':<22}")
    print("-" * 76)

    for i in range(len(acc_a.details)):
        da = acc_a.details[i]
        db = acc_b.details[i]

        gt = da["ground_truth"]
        pa = da["predicted"]
        pb = db["predicted"]

        # Mark matches
        pa_mark = "✓" if da["exact_match"] else ("~" if da["related_match"] else "✗")
        pb_mark = "✓" if db["exact_match"] else ("~" if db["related_match"] else "✗")

        print(f"{da['task_id']:<10} {gt:<22} {pa_mark} {pa:<20} {pb_mark} {pb:<20}")

    print("\nLegend: ✓ = exact match, ~ = related match, ✗ = no match")

    # Build output
    output = {
        "plan_a": {
            "total_cases": acc_a.total_cases,
            "exact_matches": acc_a.exact_matches,
            "related_matches": acc_a.related_matches,
            "exact_accuracy": acc_a.exact_accuracy,
            "related_accuracy": acc_a.related_accuracy,
            "details": acc_a.details,
        },
        "plan_b": {
            "total_cases": acc_b.total_cases,
            "exact_matches": acc_b.exact_matches,
            "related_matches": acc_b.related_matches,
            "exact_accuracy": acc_b.exact_accuracy,
            "related_accuracy": acc_b.related_accuracy,
            "details": acc_b.details,
        },
        "ground_truth": GROUND_TRUTH,
        "related_groups": [list(g) for g in RELATED_GROUPS],
    }

    if output_path:
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {output_path}")

    return output


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Calculate accuracy of failure analysis")
    parser.add_argument("--plan-a", required=True, help="Path to Plan A results JSON")
    parser.add_argument("--plan-b", required=True, help="Path to Plan B results JSON")
    parser.add_argument("--output", help="Path to save accuracy results JSON")

    args = parser.parse_args()

    run_accuracy_comparison(
        Path(args.plan_a),
        Path(args.plan_b),
        Path(args.output) if args.output else None,
    )


if __name__ == "__main__":
    main()
