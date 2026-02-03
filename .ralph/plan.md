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

