# [Feature] Add Sandbox Agent - General-Purpose Agent with Isolated Code Execution

## Summary

Propose adding **Sandbox Agent** to NAT as an advanced agent example. This agent executes tasks within secure, isolated Docker containers or Daytona cloud sandboxes, enabling safe code execution, web browsing, and file manipulation.

## Motivation

Current NAT examples lack a general-purpose agent capable of:
- **Safe code execution** - Running arbitrary Python/shell code without host system risk
- **GAIA benchmark evaluation** - A reference implementation for evaluating agent capabilities
- **Multi-modal tool usage** - Combining code execution, web browsing, file I/O, and search

Sandbox Agent addresses these gaps and provides a foundation for building secure, capable AI agents.

## Key Features

### 1. Dual Sandbox Support
- **Docker** - Local isolated containers with configurable resources
- **Daytona** - Cloud-based sandboxes for scalable execution

### 2. Comprehensive Tool Suite (7 tools)

| Tool | Location | Description |
|------|----------|-------------|
| `shell` | Sandbox | Execute bash commands |
| `python` | Sandbox | Execute Python code with pre-installed data science libraries |
| `file_read` | Sandbox | Read file contents |
| `file_write` | Sandbox | Write files |
| `web_browse` | Sandbox | Browse URLs with Playwright (headless Chromium) |
| `web_search` | Host | Tavily AI search API |
| `youtube_transcript` | Host | Extract YouTube video transcripts |

### 3. GAIA Benchmark Integration
- Pre-configured for [GAIA benchmark](https://huggingface.co/datasets/gaia-benchmark/GAIA) evaluation
- Supports all 3 difficulty levels (165 tasks total)
- Parameterized configuration with environment variables

### 4. Production-Ready Architecture
- LangGraph-based ReAct loop
- Modular tool system with clean separation
- Configurable iteration limits and output truncation
- Proper error handling and sandbox cleanup

## Benchmark Results

### GAIA Validation Set (January 2026)

**GPT-5.2:**

| Level | Tasks | Accuracy |
|-------|-------|----------|
| Level 1 | 53 | 55.66% |
| Level 2 | 86 | 51.16% |
| Level 3 | 26 | 36.54% |

**NIM LLaMA-3.3-70B:**

| Level | Tasks | Accuracy |
|-------|-------|----------|
| Level 1 | 53 | 23.11% |
| Level 2 | 86 | 20.64% |
| Level 3 | 26 | 15.38% |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Sandbox Agent Workflow                     │
├──────────────────────────────────────────────────────────────┤
│  User Request                                                 │
│       ↓                                                       │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  LangGraph ReAct Loop                    │ │
│  │  ┌──────────┐    ┌───────────┐    ┌─────────────────┐  │ │
│  │  │  Agent   │───▶│   Tool    │───▶│    Sandbox      │  │ │
│  │  │  Node    │◀───│   Node    │◀───│    Executor     │  │ │
│  │  └──────────┘    └───────────┘    └─────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                          ↓                                    │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Docker Container (Isolated)                 │ │
│  │  /workspace/  │  Shell  │  Python  │  Browser  │  Files │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## Project Structure

```
examples/advanced_agents/sandbox_agent/
├── README.md                     # Comprehensive documentation
├── Dockerfile                    # Sandbox image (pandas, playwright, etc.)
├── pyproject.toml               # Dependencies
├── configs/
│   ├── config.yaml              # Basic configuration
│   ├── config_daytona.yaml      # Daytona cloud configuration
│   └── config_gaia.yaml         # GAIA evaluation configuration
├── src/nat_sandbox_agent/
│   ├── register.py              # NAT workflow registration
│   ├── sandbox/                 # Sandbox implementations
│   │   ├── base.py              # Abstract base class
│   │   ├── docker_sandbox.py    # Docker implementation
│   │   ├── daytona_sandbox.py   # Daytona implementation
│   │   └── factory.py           # Factory pattern
│   ├── tools/                   # Modular tool system
│   │   ├── sandbox/             # shell, python, file_*, web_browse
│   │   └── host/                # web_search, youtube_transcript
│   ├── prompts/                 # System prompts
│   └── utils/                   # Answer cleaning utilities
└── tests/                       # 159 unit tests (145 pass, 14 skip integration)
```

## Testing

- **159 unit tests** covering all modules
- **14 Docker integration tests** (skipped without Docker)
- **Comprehensive mock testing** for external dependencies
- Test coverage: 37% (core modules >90%)

```bash
# Run tests
pytest tests/ -v

# Skip Docker integration tests
pytest tests/ -v -m "not integration"

# With coverage
pytest tests/ --cov=nat_sandbox_agent
```

## Dependencies

### Required
- `docker` (Python SDK)
- `langchain-core`, `langgraph`
- `tavily-python` (web search)
- `youtube-transcript-api`
- `playwright` (web browsing)

### Optional
- `daytona-sdk` (cloud sandboxes)

## Configuration Example

```yaml
llms:
  agent_llm:
    _type: nim
    model_name: meta/llama-3.3-70b-instruct
    temperature: 0.0

workflow:
  _type: sandbox_agent
  llm_name: agent_llm
  max_iterations: 20
  sandbox_config:
    type: docker
    image: "nat-sandbox:latest"
    memory_limit: "1g"
    cpu_limit: 2.0
    network_enabled: true
```

## Checklist

- [x] Comprehensive README with usage instructions
- [x] Unit tests with good coverage
- [x] Docker integration tests
- [x] GAIA benchmark evaluation support
- [x] Multiple LLM support (NIM, OpenAI)
- [x] Configurable sandbox resources
- [x] Clean code structure following NAT patterns
- [x] Apache 2.0 license headers

## Related Work

- Similar to [OpenHands](https://github.com/All-Hands-AI/OpenHands) but integrated with NAT
- Inspired by [SWE-bench](https://www.swebench.com/) evaluation patterns in NAT

## Questions for Reviewers

1. Should Daytona cloud support be included in initial contribution or added later?
2. Should the `analysis/` module (failure analysis tools) be included?
3. Any preferences on tool naming conventions?

---

**Author:** @Jerryguan777
**Target:** `examples/advanced_agents/sandbox_agent/`
**Branch:** `feat/sandbox-agent`
