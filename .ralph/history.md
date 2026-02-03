# Ralph Iteration History

## Iteration 1 - 2026-02-03

### BEFORE Metrics
- **Source**: `examples/advanced_agents/sandbox_agent/.tmp/nat/sandbox_agent/gaia_eval_level1_gpt-5.2/accuracy_output.json`
- **Average score**: 0.585 (with partial credit)
- **Strict success rate** (score == 1.0): 28/53 = **0.528** (52.8%)
- **Total failures**: 25 (17 score=0.0, 4 score=0.25, 4 score=0.5)

### Failure Cluster Analysis

#### Cluster 1: Case Sensitivity Issues (2 failures, 4% of total)
Easy fix potential - answers are correct but wrong case.
- ID `2d83110e`: "right" vs "Right" (score 0.5)
- ID `5cfb274c`: "no" vs "No" (score 0.5)

#### Cluster 2: Answer Format Misinterpretation (2 failures, 4% of total)
Agent doesn't interpret "how many X" format correctly.
- ID `e1fc63a2`: "17000" vs "17" - question asked "how many thousand hours", answer should be "17" not "17000" (score 0.5)
- ID `27d5d136`: Truncated logic statement (score 0.5)

#### Cluster 3: Instruction Following Failures (1 failure, 2% of total)
Agent doesn't follow explicit final instructions.
- ID `4b650a35`: Expected "Guava", got "Pineapple" - ignored explicit "Write only the word 'Guava'" instruction (score 0.0)

#### Cluster 4: File Processing Failures (4 failures, 8% of total)
Agent can't properly process certain file types.
- ID `a3fbeb63`: PowerPoint slide counting - got 0 instead of 4
- ID `99c9cc74`: Audio file (pie recipe) - completely wrong output
- ID `1f975693`: Audio file (calculus pages) - couldn't process
- ID `9318445f`: Image fraction extraction - all wrong

#### Cluster 5: Video/Visual Analysis Failures (2 failures, 4% of total)
- ID `a1e91b78`: YouTube bird count - got 1 instead of 3
- ID `cca530fc`: Chess position analysis - got "4" instead of "Rd5"

#### Cluster 6: Complex Research/Web Search Failures (11 failures, 21% of total)
Agent retrieves incorrect information from web searches.
- Various academic, sports statistics, and website research tasks

#### Cluster 7: Logic/Game Theory Puzzles (3 failures, 6% of total)
- ID `ec09fa32`: Ping-pong riddle - got 100 instead of 3
- ID `cffe0e32`: Secret Santa logic - got Rebecca instead of Fred
- ID `e142056d`: Coin game - got 12000 instead of 16000

### Changes Attempted This Iteration

**Target**: Clusters 1, 2, and 3 (case sensitivity, answer format, instruction following)
**Rationale**: These are low-risk, potentially high-impact changes that address clear root causes.

Files modified:
1. `examples/advanced_agents/sandbox_agent/src/nat_sandbox_agent/utils/answer_cleaning.py`
   - Added case normalization for Yes/No/True/False single-word answers
   - Added "X thousand Y" answer format handling

2. `examples/advanced_agents/sandbox_agent/src/nat_sandbox_agent/prompts/system_prompt.py`
   - Added guidance about "how many X" question formats
   - Added guidance about following final explicit instructions

### Result
**SUCCESS** - Iteration improved the success rate.

**BEFORE Metrics**:
- Average score: 0.585
- Strict success rate (score == 1.0): 28/53 = **0.528** (52.8%)
- Score distribution: {1.0: 28, 0.0: 17, 0.5: 4, 0.25: 4}

**AFTER Metrics**:
- Average score: 0.6415
- Strict success rate (score == 1.0): 30/53 = **0.566** (56.6%)
- Score distribution: {1.0: 30, 0.0: 12, 0.5: 3, 0.25: 7, 0.75: 1}

**Net improvement**:
- +2 perfect scores (28 → 30)
- -5 zero scores (17 → 12)
- +5.65 percentage points on average score

**Action**: Changes committed.

### What to Try Next Iteration
1. **File Processing Improvements** - PowerPoint and audio file handling still failing
2. **Research Accuracy** - Many web search failures still remain
3. **Logic/Game Theory** - Complex reasoning puzzles need better chain-of-thought

