# 评估：将 Failure Analysis 贡献到 NAT Core

## 一、提案概述

**目标**：将 `sandbox_agent/analysis/` 模块贡献到 NAT core，提供 `nat analyze` 命令，帮助用户分析 `nat eval` 的失败案例。

**用户体验**：
```bash
# 运行评估
nat eval --config_file config.yaml

# 分析失败案例
nat analyze --workflow-output .tmp/workflow_output.json
```

---

## 二、NAT 现状分析

### 2.1 NAT CLI 架构

NAT 使用 Click + 入口点注册机制：

```
pyproject.toml [project.entry-points.'nat.cli']
├── eval = "nat.cli.commands.evaluate:eval_command"
├── start = "nat.cli.commands.start:start_command"
├── validate = "nat.cli.commands.validate:validate_command"
└── ... (其他命令)
```

**添加新命令非常简单**：创建命令文件 + 注册入口点。

### 2.2 NAT Eval 输出

`nat eval` 生成的文件：

| 文件 | 内容 |
|------|------|
| `workflow_output.json` | 完整执行轨迹（输入、输出、trajectory） |
| `accuracy_output.json` | 准确率评分 |
| `runtime_output.json` | 运行时间统计 |
| `llm_latency_output.json` | LLM 延迟统计 |
| `trajectory_output.json` | 轨迹评分 |

### 2.3 NAT 现有分析能力

| 能力 | 状态 |
|------|------|
| 评分（accuracy, trajectory） | ✅ 有 |
| 运行时统计（latency, tokens） | ✅ 有 |
| **失败原因分析** | ❌ **没有** |
| **改进建议生成** | ❌ **没有** |
| **失败分类统计** | ❌ **没有** |

**关键发现**：NAT 能告诉你"分数是多少"，但不能告诉你"为什么失败"和"如何改进"。

---

## 三、价值评估

### 3.1 用户痛点

| 痛点 | 当前解决方案 | 有 `nat analyze` 后 |
|------|-------------|-------------------|
| 评估失败后不知道为什么 | 手动查看 JSON，逐个分析 | 自动分类，快速定位 |
| 不知道优先修哪个问题 | 凭经验猜测 | ROI 排序，修复建议 |
| 失败模式难以统计 | 写脚本统计 | 内置分类，一键生成报告 |
| 工具错误 vs 推理错误混淆 | 难以区分 | 规则自动识别工具错误 |

### 3.2 目标用户

| 用户类型 | 使用场景 | 价值 |
|----------|----------|------|
| Agent 开发者 | 迭代改进 Agent | ⭐⭐⭐⭐⭐ 高 |
| 基准测试研究者 | 分析模型能力差异 | ⭐⭐⭐⭐ 高 |
| MLOps 工程师 | 监控生产 Agent | ⭐⭐⭐ 中 |

### 3.3 与 NAT 定位的契合度

| 维度 | 评估 |
|------|------|
| **与 eval 系统的关系** | ✅ 自然延伸，eval → analyze 是完整闭环 |
| **代码复用性** | ✅ 所有使用 nat eval 的 Agent 都可受益 |
| **依赖负担** | ✅ 轻量，仅需 pydantic（已是 NAT 依赖） |
| **维护成本** | ⭐⭐ 中等 - 需要维护失败分类规则 |

---

## 四、技术方案

### 4.1 模块结构

```
src/nat/
├── cli/commands/
│   └── analyze.py              # nat analyze 命令
└── analyze/                    # 分析模块（新增）
    ├── __init__.py
    ├── models.py               # FailurePacket, FailureCategory
    ├── exporter.py             # 从 workflow_output.json 提取失败
    ├── rule_classifier.py      # 规则分类器
    ├── llm_triage.py           # LLM 分类（可选）
    └── dashboard.py            # 报告生成
```

### 4.2 命令接口

```bash
# 基本用法
nat analyze --workflow-output .tmp/workflow_output.json

# 指定输出目录
nat analyze --workflow-output output.json --output ./reports/

# 启用 LLM 分类
nat analyze --workflow-output output.json --llm-triage --llm-model gpt-4o-mini

# 仅导出失败数据
nat analyze export --workflow-output output.json --output failures.jsonl

# 仅生成报告
nat analyze report --packets failures.jsonl --output ./reports/
```

### 4.3 失败分类体系

**规则可检测（7 类）**：
- `tool_timeout` - 工具超时
- `tool_rate_limit` - API 速率限制
- `tool_server_error` - 服务端错误
- `tool_parameter_error` - 参数错误
- `output_format` - 输出格式错误
- `retrieval_empty` - 检索空结果
- `context_overflow` - 上下文溢出

**需要 LLM 分类（7 类）**：
- `task_understanding` - 任务理解错误
- `planning_decomposition` - 规划分解错误
- `tool_selection` - 工具选择错误
- `evidence_utilization` - 证据利用不当
- `reasoning_calculation` - 推理计算错误
- `state_memory` - 状态记忆丢失
- `policy_safety` - 安全策略拒绝

---

## 五、实施工作量

### 5.1 代码迁移

| 文件 | 行数 | 修改需求 |
|------|------|----------|
| `models.py` | ~160 | 无需修改 |
| `workflow_exporter.py` | ~200 | 适配 NAT 数据模型 |
| `rule_classifier.py` | ~370 | 无需修改 |
| `llm_triage.py` | ~150 | 可选功能 |
| `dashboard.py` | ~300 | 无需修改 |
| `cli.py` → `analyze.py` | ~370 | 适配 NAT CLI 风格 |
| **总计** | ~1550 | 中等工作量 |

### 5.2 测试需求

需要新增测试：
- `test_exporter.py` - 工作流导出测试
- `test_rule_classifier.py` - 规则分类测试
- `test_dashboard.py` - 报告生成测试
- `test_analyze_command.py` - CLI 集成测试

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| NVIDIA 团队不认同 | 中 | 高 | 先作为 example 验证价值 |
| 分类规则不够通用 | 中 | 中 | 提供可扩展的规则接口 |
| LLM 分类成本高 | 低 | 低 | 默认关闭，按需启用 |
| 与现有 eval 系统冲突 | 低 | 中 | analyze 是独立命令，不修改 eval |

---

## 七、结论与建议

### 7.1 价值判断

| 维度 | 评分 | 说明 |
|------|------|------|
| **用户价值** | ⭐⭐⭐⭐⭐ | 填补 NAT 的明显空白 |
| **技术契合度** | ⭐⭐⭐⭐ | 与 eval 系统自然集成 |
| **实施难度** | ⭐⭐⭐ | 中等，需要适配和测试 |
| **维护负担** | ⭐⭐⭐ | 中等，规则需要持续维护 |

**综合评估**：**值得贡献**

### 7.2 建议策略

1. **先在 Examples Repo 验证**
   - 将 sandbox_agent 放入 NeMo-Agent-Toolkit-Examples
   - 收集用户反馈，验证 analysis 模块的实用性

2. **根据反馈决定 Upstream**
   - 如果用户反馈积极，再提议将 analysis 模块上游到 NAT core
   - 这样有数据支撑，更容易获得 NVIDIA 团队认可

3. **备选方案：作为独立 Plugin**
   ```bash
   pip install nat-analyze
   nat analyze --workflow-output output.json
   ```
   利用 NAT 的插件机制，不需要进入 core 也能提供 `nat analyze` 命令

### 7.3 与 NVIDIA 团队沟通建议

在之前的 PR 回复基础上，可以追加：

> Additionally, I'd like to propose contributing the **failure analysis module** to NAT core. Currently, `nat eval` tells users "what the score is" but not "why tasks failed" or "how to improve."
>
> The analysis module provides:
> - Automatic failure classification (14 categories)
> - ROI-prioritized fix recommendations
> - HTML/JSON reports for quick insights
>
> This would complete the evaluation workflow: `nat eval` → `nat analyze` → iterate.
>
> Would you be interested in having this as a `nat analyze` command? I can refactor it to fit NAT's architecture.

---

---

## 八、详细设计方案

### 8.1 设计目标

1. **无缝集成** - 与 NAT eval 系统自然衔接
2. **可扩展** - 用户可自定义分类规则
3. **轻量级** - 最小依赖，可选 LLM 分类
4. **两种实现方式** - 支持 CLI 命令和 Evaluator 两种使用方式

### 8.2 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        nat analyze 架构                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  方式 1: CLI 命令 (事后分析)                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  nat eval ─────► workflow_output.json ─────► nat analyze  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  方式 2: Evaluator (实时分析)                                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  nat eval ─────► FailureAnalysisEvaluator ─────► 结果     │   │
│  │              (与其他 evaluator 并行运行)                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  核心模块:                                                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │ Exporter   │──│ Classifier │──│  Triage    │──│Dashboard │  │
│  │(提取失败)   │  │(规则分类)   │  │(LLM分类)   │  │(生成报告) │  │
│  └────────────┘  └────────────┘  └────────────┘  └──────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 8.3 核心数据模型

#### 与 NAT 模型对齐

```python
from nat.data_models.intermediate_step import IntermediateStep, IntermediateStepType
from nat.eval.evaluator.evaluator_model import EvalInputItem, EvalOutputItem

class FailureCategory(str, Enum):
    """失败分类 - 与 IntermediateStepType 对齐"""

    # 工具类失败 (从 TOOL_END 检测)
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_RATE_LIMIT = "tool_rate_limit"
    TOOL_SERVER_ERROR = "tool_server_error"
    TOOL_PARAMETER_ERROR = "tool_parameter_error"

    # 输出类失败 (从 output_obj 检测)
    OUTPUT_FORMAT = "output_format"
    OUTPUT_EMPTY = "output_empty"

    # 上下文类失败 (从 usage_info 检测)
    CONTEXT_OVERFLOW = "context_overflow"

    # 检索类失败 (从 metadata 检测)
    RETRIEVAL_EMPTY = "retrieval_empty"

    # 需要 LLM 分析的语义类失败
    REASONING_ERROR = "reasoning_error"
    TASK_MISUNDERSTANDING = "task_misunderstanding"
    TOOL_SELECTION_ERROR = "tool_selection_error"

    UNKNOWN = "unknown"


class FailureAnalysisItem(EvalOutputItem):
    """扩展 EvalOutputItem，添加失败分析字段"""

    id: Any
    score: float  # 0.0 = 失败, 1.0 = 通过
    reasoning: str  # 失败原因描述

    # 失败分析特有字段
    failure_category: FailureCategory | None = None
    classification_source: str = "rule"  # "rule" | "llm"
    confidence: float = 1.0

    # 根因追踪
    key_step_uuids: list[str] = []  # 关键 IntermediateStep 的 UUID
    root_cause_evidence: str = ""

    # 改进建议
    fix_suggestions: list[str] = []
```

### 8.4 关键设计决策

#### 决策 1: 如何识别失败案例？

**方案**: 从 `workflow_output.json` 中筛选 `score < 1.0` 的案例

```python
def extract_failures(workflow_output: list[dict], eval_output: dict) -> list[FailurePacket]:
    """结合 workflow_output 和 evaluator 输出提取失败"""
    failures = []

    # 从 accuracy_output.json 获取分数
    scores = {item["id"]: item["score"] for item in eval_output["eval_output_items"]}

    for item in workflow_output:
        task_id = item.get("task_id")
        if scores.get(task_id, 0) < 1.0:  # 失败
            failures.append(create_failure_packet(item, scores[task_id]))

    return failures
```

#### 决策 2: 如何从 IntermediateStep 提取信息？

**方案**: 使用 NAT 的 `IntermediateStepAdapter`

```python
from nat.eval.intermediate_step_adapter import IntermediateStepAdapter
from nat.data_models.intermediate_step import IntermediateStepType

class FailureExporter:
    def __init__(self):
        self.adapter = IntermediateStepAdapter()

    def extract_spans(self, trajectory: list[IntermediateStep]) -> list[SpanSummary]:
        """从执行轨迹提取关键 span 信息"""
        spans = []

        for step in trajectory:
            payload = step.payload

            if payload.event_type == IntermediateStepType.TOOL_END:
                spans.append(SpanSummary(
                    span_id=payload.UUID,
                    span_type="tool",
                    name=payload.name,
                    status="ERROR" if self._is_tool_error(payload) else "OK",
                    duration_ms=self._calc_duration(payload),
                    tool_name=payload.name,
                    tool_args=payload.data.input if payload.data else None,
                    tool_result=payload.data.output if payload.data else None,
                    error_message=self._extract_error(payload),
                ))

            elif payload.event_type == IntermediateStepType.LLM_END:
                usage = payload.usage_info
                spans.append(SpanSummary(
                    span_id=payload.UUID,
                    span_type="llm",
                    name=payload.name,
                    status="OK",
                    duration_ms=self._calc_duration(payload),
                    model=payload.name,
                    prompt_tokens=usage.token_usage.prompt_tokens if usage else None,
                    completion_tokens=usage.token_usage.completion_tokens if usage else None,
                ))

        return spans
```

#### 决策 3: 规则分类器如何检测失败类型？

**方案**: 基于 payload 内容的正则匹配

```python
class RuleBasedClassifier:
    """规则分类器 - 从 IntermediateStep 检测确定性失败"""

    TOOL_ERROR_PATTERNS = {
        FailureCategory.TOOL_TIMEOUT: [r"timeout", r"timed?\s*out"],
        FailureCategory.TOOL_RATE_LIMIT: [r"rate\s*limit", r"429", r"too\s*many\s*requests"],
        FailureCategory.TOOL_SERVER_ERROR: [r"\b5\d{2}\b", r"internal\s*server\s*error"],
    }

    def classify(self, packet: FailurePacket) -> FailureCategory | None:
        # 1. 检查工具错误
        for span in packet.spans:
            if span.span_type == "tool" and span.error_message:
                for category, patterns in self.TOOL_ERROR_PATTERNS.items():
                    if any(re.search(p, span.error_message, re.I) for p in patterns):
                        return category

        # 2. 检查上下文溢出
        total_tokens = sum(s.prompt_tokens or 0 for s in packet.spans if s.span_type == "llm")
        if total_tokens > 120000:  # 95% of 128k
            return FailureCategory.CONTEXT_OVERFLOW

        # 3. 检查输出格式
        if not packet.actual_output.strip():
            return FailureCategory.OUTPUT_EMPTY

        return None  # 需要 LLM 分类
```

#### 决策 4: 作为 Evaluator 还是独立 CLI？

**方案**: 两者都支持

```python
# 方式 1: 作为 Evaluator (实时，与 eval 集成)
class FailureAnalysisEvaluator(BaseEvaluator):
    """作为 evaluator 运行，与其他评估器并行"""

    async def evaluate_item(self, item: EvalInputItem) -> FailureAnalysisItem:
        # 直接访问 item.trajectory (list[IntermediateStep])
        packet = self.exporter.create_packet(item)
        category = self.classifier.classify(packet)
        return FailureAnalysisItem(
            id=item.id,
            score=1.0 if category is None else 0.0,
            reasoning=f"Failure category: {category}",
            failure_category=category,
            ...
        )

# 方式 2: 作为 CLI (事后，独立运行)
@click.command()
@click.option("--workflow-output", required=True)
def analyze_command(workflow_output: Path):
    """事后分析 workflow_output.json"""
    packets = exporter.load_from_file(workflow_output)
    classified = classifier.classify_batch(packets)
    dashboard.generate_report(classified)
```

### 8.5 配置设计

```yaml
# 作为 Evaluator 使用
evaluators:
  failure_analysis:
    _type: failure_analysis
    llm_triage_enabled: false  # 是否启用 LLM 分类
    llm_name: eval_llm  # LLM 分类使用的模型
    context_token_limit: 128000  # 上下文溢出阈值
    custom_rules: []  # 自定义规则

# 作为 CLI 使用
# nat analyze --workflow-output output.json --config analyze_config.yaml
```

### 8.6 模块结构

```
src/nat/analyze/                    # 核心分析模块
├── __init__.py
├── models.py                       # FailureCategory, FailurePacket, SpanSummary
├── exporter.py                     # 从 workflow_output 提取失败
├── classifier/
│   ├── __init__.py
│   ├── base.py                     # BaseClassifier ABC
│   ├── rule_classifier.py          # 规则分类器
│   └── llm_classifier.py           # LLM 分类器 (可选)
├── dashboard.py                    # 报告生成
└── evaluator.py                    # FailureAnalysisEvaluator

src/nat/cli/commands/
└── analyze.py                      # nat analyze CLI 命令
```

### 8.7 依赖管理

```toml
# pyproject.toml
[project]
dependencies = [
    # 核心依赖 (已在 NAT 中)
    "pydantic>=2.0",
    "click>=8.0",
]

[project.optional-dependencies]
analyze-llm = [
    # LLM 分类可选依赖
    "openai>=1.0",
]
```

### 8.8 输出格式

```
output_dir/
├── workflow_output.json            # (已有) 执行轨迹
├── accuracy_output.json            # (已有) 准确率
├── failure_analysis_output.json    # (新增) 失败分析结果
│   {
│     "average_score": 0.45,
│     "total_failures": 29,
│     "rule_classified": 18,
│     "llm_classified": 0,
│     "category_distribution": {...},
│     "eval_output_items": [...]
│   }
├── failure_packets.jsonl           # (新增) 详细失败数据
└── failure_report.html             # (新增) 可视化报告
```

---

## 九、实施路径

### 阶段 1: MVP (2 周)

- [ ] 迁移 models.py, exporter.py, rule_classifier.py
- [ ] 适配 NAT IntermediateStep 模型
- [ ] 实现 `nat analyze` CLI 命令
- [ ] 基本测试

### 阶段 2: Evaluator 集成 (1 周)

- [ ] 实现 FailureAnalysisEvaluator
- [ ] 添加 evaluator 配置支持
- [ ] 集成测试

### 阶段 3: 增强功能 (1 周)

- [ ] LLM 分类器
- [ ] 自定义规则接口
- [ ] HTML 报告美化
- [ ] 文档

---

## 九、通用性分析：NAT Examples 覆盖情况

### 9.1 NAT 现有 Examples 概览

NAT 有 **56+ 个示例**，主要类型：

| 类型 | 数量 | 代表示例 |
|------|------|----------|
| ReAct Agent | 18 | simple_calculator, simple_web_query |
| RAG Agent | 5 | simple_rag, haystack_deep_research |
| Tool Calling | 4 | tool_calling |
| Multi-Agent | 3 | mixture_of_agents, nat_autogen_demo |
| Security/Safety | 2 | email_phishing_analyzer, retail_agent |
| SWE/Code | 2 | swe_bench, sandbox_agent |
| 其他 | 22 | MCP, A2A, Finetuning, Observability |

### 9.2 当前 14 类失败分类覆盖分析

#### ✅ 可覆盖的失败类型 (7 类规则检测)

| 分类 | 适用 Examples | 覆盖率 |
|------|---------------|--------|
| `tool_timeout` | 所有使用外部 API 的 agent | 90%+ |
| `tool_rate_limit` | web_search, Tavily, SerperDev 相关 | 60% |
| `tool_server_error` | 所有有工具调用的 agent | 90%+ |
| `tool_parameter_error` | 所有工具调用 | 90%+ |
| `output_format` | 所有 agent（输出解析） | 100% |
| `retrieval_empty` | RAG 类 (simple_rag, haystack_*) | 15% |
| `context_overflow` | 长对话/大文档处理 | 30% |

#### ⚠️ 部分覆盖 (7 类 LLM 分析)

| 分类 | 适用场景 | 局限性 |
|------|----------|--------|
| `task_understanding` | 所有 agent | 通用，但检测依赖 LLM |
| `tool_selection` | 多工具 agent | 需要 LLM 分析 |
| `reasoning_error` | 计算/逻辑类 | 需要 LLM 分析 |
| `planning_decomposition` | ReWOO, 复杂任务 | 需要 LLM 分析 |
| `evidence_utilization` | RAG 类 | 需要 LLM 分析 |
| `state_memory` | 多轮对话 | 需要 LLM 分析 |
| `policy_safety` | safety 相关 | 需要 LLM 分析 |

### 9.3 无法覆盖的失败类型

| 失败类型 | 涉及 Examples | 原因 |
|----------|---------------|------|
| **认证失败** | simple_auth, *_mcp, *_a2a | 当前无 `auth_failure` 分类 |
| **框架兼容性** | multi_frameworks, agno_*, semantic_kernel | 跨框架错误难以通用化 |
| **容器/资源** | sandbox_agent, swe_bench | 需要 `resource_exhaustion` 分类 |
| **网络连接** | 所有远程调用 | 需要 `network_error` 分类 |
| **配置错误** | config_inheritance | 需要 `config_error` 分类 |
| **安全检测** | retail_agent, email_phishing | 需要领域特定分类 |

### 9.4 覆盖率评估

```
                    当前 14 类覆盖率
┌─────────────────────────────────────────────┐
│ ████████████████████░░░░░░░░░  65%          │
│ 可覆盖          部分覆盖    无法覆盖         │
└─────────────────────────────────────────────┘

按 Example 类型:
- ReAct/Tool Agent:     ████████████████████ 85%  ✅ 高
- RAG Agent:            ████████████████░░░░ 80%  ✅ 高
- Multi-Agent:          ████████████░░░░░░░░ 60%  ⚠️ 中
- MCP/A2A:              ████████░░░░░░░░░░░░ 40%  ⚠️ 低
- Security/Safety:      ██████░░░░░░░░░░░░░░ 30%  ❌ 低
- Finetuning:           ████░░░░░░░░░░░░░░░░ 20%  ❌ 低
```

### 9.5 建议新增的失败分类

为提高通用性，建议新增 **5 类**：

| 新分类 | 检测方式 | 覆盖场景 |
|--------|----------|----------|
| `auth_failure` | Rule | OAuth, JWT, API Key 错误 |
| `network_error` | Rule | 连接超时、DNS 失败、SSL 错误 |
| `resource_exhaustion` | Rule | 内存、CPU、磁盘配额 |
| `config_error` | Rule | 配置缺失、格式错误 |
| `recursion_limit` | Rule | Agent 迭代次数超限 |

新增后覆盖率：**65% → 80%+**

---

## 十、可扩展性设计

### 10.1 扩展机制概览

提供两种扩展方式，满足不同用户需求：

| 方式 | 适用场景 | 复杂度 | 能力 |
|------|----------|--------|------|
| **YAML 配置** | 简单模式匹配扩展 | 低 | 添加模式、修改描述 |
| **Python Registry** | 复杂自定义逻辑 | 中 | 完全自定义匹配逻辑 |

```
┌─────────────────────────────────────────────────────────────┐
│                    扩展机制架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户扩展方式:                                               │
│  ┌─────────────┐         ┌─────────────┐                   │
│  │ YAML 配置   │         │ Python 代码  │                   │
│  │ (简单扩展)  │         │ (高级扩展)   │                   │
│  └──────┬──────┘         └──────┬──────┘                   │
│         │                       │                          │
│         ▼                       ▼                          │
│  ┌─────────────────────────────────────────────┐           │
│  │              RuleRegistry                    │           │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────────┐   │           │
│  │  │ 内置规则 │ │YAML规则 │ │ 用户代码规则 │   │           │
│  │  └─────────┘ └─────────┘ └─────────────┘   │           │
│  └─────────────────────────────────────────────┘           │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────────────────────────────────┐           │
│  │           RuleBasedClassifier                │           │
│  └─────────────────────────────────────────────┘           │
│                                                             │
│  LLM 分类扩展:                                              │
│  ┌─────────────┐         ┌─────────────┐                   │
│  │ YAML 配置   │         │ 自定义 Prompt │                  │
│  │ (新增分类)  │         │ (完全自定义)  │                  │
│  └──────┬──────┘         └──────┬──────┘                   │
│         │                       │                          │
│         ▼                       ▼                          │
│  ┌─────────────────────────────────────────────┐           │
│  │              LLMTriage                       │           │
│  │  (动态构建 prompt，包含内置+自定义分类)        │           │
│  └─────────────────────────────────────────────┘           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 10.2 Rule-based 扩展

#### 10.2.1 ClassificationRule 基类

```python
# nat/analyze/classifier/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar
import re

@dataclass
class RuleResult:
    """规则匹配结果"""
    matched: bool
    category: str
    evidence: str = ""
    key_span_ids: list[str] = field(default_factory=list)
    fix_suggestions: list[str] = field(default_factory=list)


class ClassificationRule(ABC):
    """分类规则基类 - 所有规则必须继承此类"""

    # 子类必须定义
    name: ClassVar[str]  # 规则名称，如 "tool_timeout"
    category: ClassVar[str]  # 对应的失败分类
    priority: ClassVar[int] = 100  # 优先级，数字越小越先执行
    description: ClassVar[str] = ""  # 规则描述

    @abstractmethod
    def match(self, packet: "FailurePacket") -> RuleResult:
        """
        判断是否匹配此规则。

        Args:
            packet: 失败数据包

        Returns:
            RuleResult，matched=True 表示匹配
        """
        pass


class PatternRule(ClassificationRule):
    """基于正则模式的规则 - 简化常见场景"""

    patterns: ClassVar[list[str]] = []  # 正则模式列表
    check_fields: ClassVar[list[str]] = ["error_message", "tool_result_summary"]
    fix_suggestions: ClassVar[list[str]] = []

    def __init__(self):
        self._compiled_re = re.compile(
            "|".join(f"({p})" for p in self.patterns),
            re.IGNORECASE
        )

    def match(self, packet: "FailurePacket") -> RuleResult:
        for span in packet.spans:
            if span.span_type != "tool":
                continue

            # 检查指定字段
            for field_name in self.check_fields:
                text = getattr(span, field_name, "") or ""
                if self._compiled_re.search(text):
                    return RuleResult(
                        matched=True,
                        category=self.category,
                        evidence=f"Tool '{span.tool_name}' matched pattern. Text: {text[:200]}",
                        key_span_ids=[span.span_id],
                        fix_suggestions=self.fix_suggestions,
                    )

        return RuleResult(matched=False, category=self.category)
```

#### 10.2.2 RuleRegistry 注册表

```python
# nat/analyze/classifier/registry.py

import importlib.util
import logging
from pathlib import Path
from typing import Type

import yaml

logger = logging.getLogger(__name__)


class RuleRegistry:
    """规则注册表 - 管理所有分类规则"""

    _rules: list[Type[ClassificationRule]] = []
    _initialized: bool = False

    @classmethod
    def register(cls, rule_class: Type[ClassificationRule]):
        """装饰器：注册规则类"""
        cls._rules.append(rule_class)
        cls._rules.sort(key=lambda r: r.priority)
        logger.debug(f"Registered rule: {rule_class.name} (priority={rule_class.priority})")
        return rule_class

    @classmethod
    def load_builtin_rules(cls):
        """加载内置规则"""
        if cls._initialized:
            return
        # 导入内置规则模块，触发 @register 装饰器
        from nat.analyze.classifier import rules  # noqa
        cls._initialized = True

    @classmethod
    def load_from_yaml(cls, config_path: Path):
        """从 YAML 配置加载规则"""
        with open(config_path) as f:
            config = yaml.safe_load(f)

        for rule_def in config.get("custom_rules", []):
            rule_class = cls._create_rule_from_yaml(rule_def)
            cls._rules.append(rule_class)

        cls._rules.sort(key=lambda r: r.priority)

    @classmethod
    def load_from_python(cls, module_path: Path):
        """从 Python 文件加载规则"""
        spec = importlib.util.spec_from_file_location("custom_rules", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # 规则通过 @register 装饰器自动注册

    @classmethod
    def _create_rule_from_yaml(cls, rule_def: dict) -> Type[ClassificationRule]:
        """从 YAML 定义创建规则类"""
        class YAMLRule(PatternRule):
            name = rule_def["name"]
            category = rule_def["category"]
            priority = rule_def.get("priority", 100)
            patterns = rule_def.get("patterns", [])
            fix_suggestions = rule_def.get("fix_suggestions", [])
            description = rule_def.get("description", "")

        return YAMLRule

    @classmethod
    def get_rules(cls) -> list[Type[ClassificationRule]]:
        """获取所有已注册规则"""
        cls.load_builtin_rules()
        return cls._rules

    @classmethod
    def clear(cls):
        """清空注册表（用于测试）"""
        cls._rules = []
        cls._initialized = False
```

#### 10.2.3 内置规则示例

```python
# nat/analyze/classifier/rules/tool_errors.py

from nat.analyze.classifier.base import PatternRule, ClassificationRule, RuleResult
from nat.analyze.classifier.registry import RuleRegistry


@RuleRegistry.register
class ToolTimeoutRule(PatternRule):
    """工具超时规则"""
    name = "tool_timeout"
    category = "tool_timeout"
    priority = 10
    description = "Detects tool execution timeouts"

    patterns = [
        r"timeout",
        r"timed?\s*out",
        r"deadline\s*exceeded",
        r"request\s*took\s*too\s*long",
    ]
    fix_suggestions = [
        "Increase timeout limit for this tool",
        "Add retry logic with exponential backoff",
        "Consider using a more reliable alternative service",
    ]


@RuleRegistry.register
class ToolRateLimitRule(PatternRule):
    """API 速率限制规则"""
    name = "tool_rate_limit"
    category = "tool_rate_limit"
    priority = 10

    patterns = [
        r"rate\s*limit",
        r"too\s*many\s*requests",
        r"quota\s*exceeded",
        r"429",
    ]
    fix_suggestions = [
        "Add rate limiting and request queuing",
        "Implement exponential backoff with jitter",
        "Consider upgrading API quota or using fallback service",
    ]


@RuleRegistry.register
class ContextOverflowRule(ClassificationRule):
    """上下文溢出规则 - 需要自定义逻辑"""
    name = "context_overflow"
    category = "context_overflow"
    priority = 50

    def __init__(self, token_limit: int = 128000):
        self.token_limit = token_limit

    def match(self, packet: "FailurePacket") -> RuleResult:
        total_tokens = sum(
            (span.prompt_tokens or 0) + (span.completion_tokens or 0)
            for span in packet.spans
            if span.span_type == "llm"
        )

        if total_tokens > self.token_limit * 0.95:
            return RuleResult(
                matched=True,
                category=self.category,
                evidence=f"Total tokens ({total_tokens}) exceeded 95% of limit ({self.token_limit})",
                fix_suggestions=[
                    "Add context summarization middleware",
                    "Implement sliding window for conversation history",
                ],
            )

        return RuleResult(matched=False, category=self.category)
```

#### 10.2.4 YAML 配置格式

```yaml
# analyze_config.yaml

# ============ Rule-based 扩展 ============

custom_rules:
  # 简单模式匹配规则
  - name: openai_api_error
    category: tool_server_error
    priority: 15
    description: "OpenAI API specific errors"
    patterns:
      - "openai.*error"
      - "api\.openai\.com.*failed"
      - "insufficient_quota"
    fix_suggestions:
      - "Check OpenAI API key validity"
      - "Verify account has sufficient credits"

  # 认证失败规则
  - name: auth_failure
    category: auth_failure
    priority: 20
    patterns:
      - "401"
      - "unauthorized"
      - "authentication failed"
      - "invalid.*api.*key"
      - "token.*expired"
    fix_suggestions:
      - "Check API key configuration"
      - "Refresh authentication token"

  # 企业内部错误
  - name: internal_service_error
    category: tool_server_error
    priority: 25
    patterns:
      - "internal-service-\\d+"
      - "corp\\.example\\.com.*error"
    fix_suggestions:
      - "Contact internal service team"
      - "Check service health dashboard"

# 禁用某些内置规则
disabled_rules:
  - tool_parameter_error  # 暂时禁用
```

---

### 10.3 LLM-based 扩展

#### 10.3.1 LLM 分类配置

```yaml
# analyze_config.yaml (续)

# ============ LLM-based 扩展 ============

llm_triage:
  # 基础配置
  model: gpt-4o-mini
  temperature: 0.1
  max_tokens: 1000

  # 自定义分类（追加到内置分类后）
  custom_categories:
    - id: domain_knowledge
      description: "Agent lacks specific domain expertise needed for the task"
      examples:
        - "Agent doesn't understand medical terminology"
        - "Agent misinterprets legal or financial concepts"
      fix_suggestions:
        - "Add domain-specific knowledge to the prompt"
        - "Use a domain-specialized model or RAG"

    - id: multi_step_coordination
      description: "Agent failed to coordinate results across multiple steps"
      examples:
        - "Agent completed step 1 but didn't use its result in step 2"
        - "Agent lost intermediate results between tool calls"
      fix_suggestions:
        - "Improve state management in agent loop"
        - "Add explicit result passing between steps"

    - id: hallucination
      description: "Agent generated false information not supported by evidence"
      examples:
        - "Agent invented facts not present in retrieved documents"
        - "Agent claimed to have done something it didn't do"
      fix_suggestions:
        - "Add fact-checking step before final output"
        - "Require citations for all claims"

  # 完全自定义 prompt（可选，覆盖默认 prompt）
  # custom_prompt_file: my_triage_prompt.txt
```

#### 10.3.2 LLMTriage 实现

```python
# nat/analyze/llm_triage.py

from pathlib import Path
from typing import Any

import yaml

# 内置 LLM 分类
BUILTIN_LLM_CATEGORIES = [
    {
        "id": "task_understanding",
        "description": "Agent misunderstood the task requirements, constraints, or goals",
    },
    {
        "id": "planning_decomposition",
        "description": "Agent failed to break down the task properly, wrong order, missing steps",
    },
    {
        "id": "tool_selection",
        "description": "Agent chose the wrong tool or tried to guess instead of using available tools",
    },
    {
        "id": "evidence_utilization",
        "description": "Agent found relevant information but failed to use it correctly",
    },
    {
        "id": "reasoning_calculation",
        "description": "Agent made logical errors, calculation mistakes, or wrong inferences",
    },
    {
        "id": "state_memory",
        "description": "Agent lost track of context across steps or overwrote important state",
    },
    {
        "id": "policy_safety",
        "description": "Agent refused due to safety policy or generated harmful content",
    },
]


class LLMTriage:
    """LLM-based 失败分类，支持扩展"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        config: dict[str, Any] | None = None,
        config_path: Path | None = None,
    ):
        self.model = model
        self.config = config or {}

        if config_path:
            self._load_config(config_path)

        self.custom_categories = self.config.get("custom_categories", [])
        self.custom_prompt_file = self.config.get("custom_prompt_file")

    def _load_config(self, path: Path):
        """加载配置文件"""
        with open(path) as f:
            full_config = yaml.safe_load(f)
            self.config = full_config.get("llm_triage", {})

    def _build_categories_text(self) -> str:
        """构建分类描述文本"""
        all_categories = BUILTIN_LLM_CATEGORIES + self.custom_categories

        lines = []
        for i, cat in enumerate(all_categories, 1):
            desc = cat["description"]
            examples = cat.get("examples", [])

            line = f'{i}. **{cat["id"]}** - {desc}'
            if examples:
                line += f'\n   Examples: {"; ".join(examples)}'
            lines.append(line)

        return "\n".join(lines)

    def _build_prompt(self, packet: "FailurePacket") -> str:
        """构建 LLM prompt"""
        # 如果用户提供了自定义 prompt，使用它
        if self.custom_prompt_file:
            with open(self.custom_prompt_file) as f:
                template = f.read()
        else:
            template = self._get_default_template()

        categories_text = self._build_categories_text()

        return template.format(
            categories=categories_text,
            user_request=packet.user_request,
            expected_output=packet.expected_output,
            actual_output=packet.actual_output,
            eval_reason=packet.eval_result.reason,
            spans_json=self._format_spans_json(packet),
        )

    def _get_default_template(self) -> str:
        return """You are an expert at analyzing AI agent failures.

## Failure Categories (choose exactly ONE):

{categories}

## Task Information

**User Request:** {user_request}
**Expected Output:** {expected_output}
**Actual Output:** {actual_output}
**Evaluation Reason:** {eval_reason}

## Execution Trace

{spans_json}

## Your Analysis

Respond with JSON:
{{"category": "...", "confidence": 0.0-1.0, "evidence": "...", "fix_suggestions": [...]}}
"""

    def get_all_categories(self) -> list[str]:
        """获取所有分类 ID（内置+自定义）"""
        all_cats = BUILTIN_LLM_CATEGORIES + self.custom_categories
        return [cat["id"] for cat in all_cats]
```

---

### 10.4 CLI 接口

```bash
# 基本用法（使用内置规则）
nat analyze --workflow-output output.json

# 使用 YAML 配置（Rule + LLM 扩展）
nat analyze --workflow-output output.json --config analyze_config.yaml

# 加载 Python 自定义规则
nat analyze --workflow-output output.json --rules my_rules.py

# 同时使用配置和 Python 规则
nat analyze --workflow-output output.json --config config.yaml --rules my_rules.py

# 启用 LLM 分类
nat analyze --workflow-output output.json --llm-triage

# LLM 分类 + 自定义配置
nat analyze --workflow-output output.json --llm-triage --config config.yaml

# 列出所有可用规则
nat analyze --list-rules

# 列出所有分类
nat analyze --list-categories
```

---

### 10.5 FailureCategory 动态扩展

```python
# nat/analyze/models.py

from enum import Enum
from typing import ClassVar


class FailureCategory(str, Enum):
    """失败分类枚举 - 支持运行时扩展"""

    # === 内置分类 ===
    # Rule-based (12 类)
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_RATE_LIMIT = "tool_rate_limit"
    TOOL_SERVER_ERROR = "tool_server_error"
    TOOL_PARAMETER_ERROR = "tool_parameter_error"
    OUTPUT_FORMAT = "output_format"
    OUTPUT_EMPTY = "output_empty"
    CONTEXT_OVERFLOW = "context_overflow"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    RECURSION_LIMIT = "recursion_limit"
    NETWORK_ERROR = "network_error"
    AUTH_FAILURE = "auth_failure"
    RETRIEVAL_EMPTY = "retrieval_empty"

    # LLM-based (7 类)
    TASK_UNDERSTANDING = "task_understanding"
    PLANNING_DECOMPOSITION = "planning_decomposition"
    TOOL_SELECTION = "tool_selection"
    EVIDENCE_UTILIZATION = "evidence_utilization"
    REASONING_ERROR = "reasoning_error"
    STATE_MEMORY = "state_memory"
    POLICY_SAFETY = "policy_safety"

    # 未知
    UNKNOWN = "unknown"

    # 自定义分类存储
    _custom_categories: ClassVar[dict[str, str]] = {}

    @classmethod
    def register_custom(cls, category_id: str, description: str = ""):
        """注册自定义分类"""
        cls._custom_categories[category_id] = description

    @classmethod
    def get(cls, value: str) -> "FailureCategory":
        """获取分类，支持自定义分类"""
        try:
            return cls(value)
        except ValueError:
            if value in cls._custom_categories:
                return value  # 返回字符串形式的自定义分类
            return cls.UNKNOWN

    @classmethod
    def all_categories(cls) -> list[str]:
        """获取所有分类（内置+自定义）"""
        builtin = [c.value for c in cls]
        custom = list(cls._custom_categories.keys())
        return builtin + custom
```

---

### 10.6 实现工作量

| 模块 | 新增代码 | 说明 |
|------|----------|------|
| `classifier/base.py` | ~80 行 | ClassificationRule, PatternRule, RuleResult |
| `classifier/registry.py` | ~100 行 | RuleRegistry |
| `classifier/rules/*.py` | ~200 行 | 内置规则重构 |
| `llm_triage.py` | ~100 行 | LLM 扩展支持 |
| `models.py` | ~30 行 | FailureCategory 扩展 |
| `cli/analyze.py` | ~50 行 | CLI 参数支持 |
| **总计** | **~560 行** | |

---

### 10.7 用户使用示例

#### 示例 1: 企业内部 API 错误

```yaml
# my_config.yaml
custom_rules:
  - name: internal_api_error
    category: tool_server_error
    patterns:
      - "internal-api-\\d{3}"
      - "corp-service-unavailable"
    fix_suggestions:
      - "Check internal service status page"
      - "Contact platform team"
```

```bash
nat analyze --workflow-output output.json --config my_config.yaml
```

#### 示例 2: 医疗领域 LLM 分类

```yaml
# medical_config.yaml
llm_triage:
  custom_categories:
    - id: medical_terminology
      description: "Agent misunderstood medical terms or clinical concepts"
      examples:
        - "Confused drug names"
        - "Misinterpreted diagnosis codes"
```

#### 示例 3: 复杂自定义逻辑

```python
# my_rules.py
from nat.analyze.classifier import ClassificationRule, RuleRegistry, RuleResult

@RuleRegistry.register
class CascadingFailureRule(ClassificationRule):
    """检测级联失败 - 多个工具连续失败"""
    name = "cascading_failure"
    category = "tool_server_error"
    priority = 5  # 高优先级

    def match(self, packet):
        error_count = sum(
            1 for span in packet.spans
            if span.span_type == "tool" and span.status == "ERROR"
        )

        if error_count >= 3:
            return RuleResult(
                matched=True,
                category=self.category,
                evidence=f"Cascading failure: {error_count} tools failed consecutively",
                fix_suggestions=["Implement circuit breaker pattern"],
            )

        return RuleResult(matched=False, category=self.category)
```

```bash
nat analyze --workflow-output output.json --rules my_rules.py
```

---

## 十一、Core vs Plugin 决策

### 11.1 两种实现方式对比

| 维度 | Core 集成 | Plugin 方式 |
|------|-----------|-------------|
| **安装** | `pip install nat` 自动包含 | `pip install nat-analyze` 额外安装 |
| **可见性** | `nat --help` 默认显示 | 需要用户知道并安装 |
| **维护** | NVIDIA 团队负责 | 可以独立维护和发布 |
| **审批** | 需要 NVIDIA 接受 PR | 无需审批 |
| **版本** | 与 NAT 同步 | 独立版本，可快速迭代 |
| **依赖** | 增加 NAT 核心大小 | 按需安装 |

### 11.2 技术实现差异

```
# Core 方式
src/nat/
├── analyze/           # 分析模块
└── cli/commands/
    └── analyze.py     # nat analyze 命令

pyproject.toml:
[project.entry-points.'nat.cli']
analyze = "nat.cli.commands.analyze:analyze_command"

# Plugin 方式
nat-analyze/
├── src/nat_analyze/
│   ├── analyze/       # 分析模块
│   └── cli.py         # 命令实现
└── pyproject.toml

pyproject.toml:
[project.entry-points.'nat.cli']
analyze = "nat_analyze.cli:analyze_command"
```

**技术本质相同**：都通过 `nat.cli` 入口点注册命令，用户体验一致。

### 11.3 建议策略：Plugin First

**推荐路径**：

```
阶段 1: 作为 Plugin 发布 (立即)
├── 发布 `nat-analyze` 到 PyPI
├── 用户可通过 `pip install nat-analyze` 安装
├── 快速迭代，收集反馈
└── 验证价值

阶段 2: 根据反馈决定 (3-6 个月后)
├── 如果反馈积极 → 提议合并到 NAT core
├── 有下载量、issue、用户反馈作为数据支撑
└── 更容易获得 NVIDIA 团队认可
```

**理由**：
1. **降低审批风险** - 无需等待 NVIDIA 认可
2. **快速验证** - 可立即发布，收集真实用户反馈
3. **保留灵活性** - 证明价值后仍可进入 core
4. **符合 reviewer 建议** - "先验证价值，再决定上游"

### 11.4 Plugin 包结构

```
nat-analyze/
├── README.md
├── pyproject.toml
├── src/nat_analyze/
│   ├── __init__.py
│   ├── models.py
│   ├── exporter.py
│   ├── classifier/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   └── rules/
│   │       ├── __init__.py
│   │       └── tool_errors.py
│   ├── llm_triage.py
│   ├── dashboard.py
│   └── cli.py
└── tests/
```

```toml
# pyproject.toml
[project]
name = "nat-analyze"
version = "0.1.0"
description = "Failure analysis tool for NeMo Agent Toolkit"
dependencies = [
    "pydantic>=2.0",
    "click>=8.0",
    "jinja2>=3.0",  # HTML report
]

[project.optional-dependencies]
llm = ["openai>=1.0"]

[project.entry-points.'nat.cli']
analyze = "nat_analyze.cli:analyze_command"
```

---

## 十二、最终决策与下一步行动

### 12.1 决策总结

| 决策项 | 选择 | 理由 |
|--------|------|------|
| **实现方式** | CLI only (事后分析) | 简单、实用、无侵入 |
| **部署方式** | Plugin first | 快速验证、降低审批风险 |
| **初始分类** | 19 类 (12 rule + 7 LLM) | 覆盖 80%+ NAT examples |
| **扩展机制** | Registry + YAML | 兼顾简单和高级用户 |

### 12.2 下一步行动

1. [ ] 等待 NVIDIA 对 sandbox PR 的反馈
2. [ ] 在 PR 回复中提及 failure analysis 作为 Plugin 的计划
3. [ ] 创建 `nat-analyze` 独立仓库/包
4. [ ] 从 sandbox_agent/analysis/ 迁移代码
5. [ ] 添加 RuleRegistry 扩展机制
6. [ ] 发布到 PyPI
7. [ ] 收集用户反馈，评估是否进入 NAT core
