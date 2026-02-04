# Ralph Improvement Plan

## Iteration 1 - 2026-02-03

### Selected Changes

1. **Fix Case Sensitivity in Answer Cleaning** (targets Cluster 1)
   - Normalize single-word Yes/No/True/False answers to Title Case
   - Normalize single-word directional answers (Left/Right/Up/Down)
   - Expected impact: +2 correct (score 0.5 -> 1.0)

2. **Add "X thousand/million" Format Guidance** (targets Cluster 2)
   - Add system prompt guidance explaining that "how many thousand X" means the answer should be the coefficient, not the full number
   - Expected impact: +1 correct (score 0.5 -> 1.0)

3. **Add Instruction Priority Guidance** (targets Cluster 3)
   - Add system prompt guidance about following the final explicit instruction when multiple instructions are present
   - Expected impact: +1 correct (score 0.0 -> 1.0)

### Acceptance Criteria
- Success rate should improve from 0.528 to at least 0.57 (+2-4 correct answers)
- No regressions on currently passing tests

### Safety Notes
- NOT changing: GAIA dataset, evaluation harness, config scoring logic
- NOT changing: Tool implementations or sandbox behavior
- Changes are minimal and targeted to prompt and post-processing only

---

## Iteration 2 - 2026-02-03

### Failure Analysis Summary
Current rate: 30/53 = 0.566 (56.6%)

**Key Failure Patterns Identified:**
1. **Answer format issues** (3 failures): Truncated answers, numbers not converted to words, extracting too much
2. **Logic/game theory puzzle errors** (4 failures): Reasoning mistakes in probability puzzles
3. **Complex research failures** (8 failures): Wrong information from web searches
4. **File processing failures** (4 failures): Audio/Excel/PowerPoint files not processed

### Selected Changes for This Iteration

1. **Add Number-to-Words Format Guidance** (targets `dc22a632`)
   - Add explicit guidance about converting numbers to words when question asks for "plain text" numbers
   - Example: "500" → "Five Hundred"
   - Expected impact: +1 correct

2. **Add Answer Completeness Guidance** (targets `27d5d136`, `4b6bb5f7`)
   - Emphasize providing complete answers exactly as specified
   - Add guidance about extracting exactly what's asked (not more, not less)
   - Expected impact: +2 correct

3. **Improve Logic Puzzle Chain-of-Thought Guidance** (targets `ec09fa32`, `e142056d`)
   - Add specific guidance for game theory/probability puzzles
   - Emphasize verifying algorithm correctness before running simulations
   - Expected impact: +1-2 correct

### Acceptance Criteria
- Success rate should improve from 0.566 to at least 0.60 (+2-3 correct answers)
- No regressions on currently passing tests

### Safety Notes
- NOT changing: GAIA dataset, evaluation harness, config scoring logic
- NOT changing: Tool implementations or sandbox behavior
- Changes are minimal and targeted to system prompt only

