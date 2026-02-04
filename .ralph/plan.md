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

---

## Iteration 3 - 2026-02-03

### Failure Analysis Summary
Current rate: 32/53 = 0.604 (60.4%)
Total failures: 21 (9 score=0.0, 7 score=0.25, 3 score=0.5, 2 score=0.75)

**Key Failure Patterns Identified:**

1. **Answer Format/Extraction Issues** (5 failures, 24%):
   - `4b6bb5f7` (0.75): Extracted scene heading instead of just setting ("INT. THE CASTLE - DAY" vs "THE CASTLE")
   - `27d5d136` (0.5): Logic statement truncated - "(¬A → B) ↔" missing right side
   - `42576abe` (0.5): Case mismatch on "mato" in Tizin language translation
   - `5cfb274c` (0.5): Appears correct "No" but scored 0.5, likely whitespace/format issue
   - `dc22a632` (0.75): Book title close but not exact match on capitalization

2. **File Processing Failures** (3 failures, 14%):
   - `99c9cc74` (0.0): Audio file completely misidentified (pie recipe)
   - `1f975693` (0.0): Audio file couldn't process (calculus pages)
   - `a3fbeb63` (0.0): PowerPoint slide count wrong (0 vs 4)

3. **Logic/Game Theory Puzzles** (3 failures, 14%):
   - `ec09fa32` (0.0): Ping-pong riddle still wrong (100 vs 3) - simulation bug
   - `e142056d` (0.25): Coin game improved but still wrong (12000 vs 16000)
   - `50ec8903` (0.25): Rubik's cube spatial reasoning error

4. **Complex Research/Retrieval** (6 failures, 29%):
   - Various web searches returning incorrect information
   - Academic/sports statistics/database queries

5. **Image/Visual Analysis** (2 failures, 10%):
   - Chess position, fraction extraction failures

### Selected Changes for This Iteration

**Target**: Answer format issues (Cluster 1) - highest fix potential with minimal risk

1. **Improve Answer Extraction Precision** (targets `4b6bb5f7`, `27d5d136`)
   - Add guidance about extracting *exactly* what's requested, no more, no less
   - Emphasize reading questions carefully for: "exactly as it appears", "complete statement", etc.
   - Expected impact: +2 correct (0.75→1.0, 0.5→1.0)

2. **Add Case Sensitivity Handling for Generated Text** (targets `42576abe`)
   - Add answer cleaning for preserving case when reconstructing from grammar rules
   - Expected impact: +1 correct (0.5→1.0)

3. **Add Code Verification Guidance for Simulation Puzzles** (targets `ec09fa32`, `e142056d`)
   - Add specific prompt guidance: before running simulations, verify the code logic matches the problem rules exactly
   - Add suggestion to trace through a few manual examples before running full simulation
   - Expected impact: +1-2 correct (targeting the persistent ping-pong failure)

### Acceptance Criteria
- Success rate should improve from 0.604 to at least 0.642 (+2-3 correct answers)
- No regressions on currently passing tests

### Safety Notes
- NOT changing: GAIA dataset, evaluation harness, config scoring logic
- NOT changing: Core tool implementations
- Changes are minimal and targeted to system prompt and answer cleaning only

