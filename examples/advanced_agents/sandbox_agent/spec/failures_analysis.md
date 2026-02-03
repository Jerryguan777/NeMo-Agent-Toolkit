# Plan: Agent 失败案例分析工程化流水线

## 目标
建立稳定的失败案例分析工程流水线，实现：
1. **快速归因** - 将失败归到可行动的原因
2. **最小改动验证** - 用最小改动验证修复是否真的提升

---

## 一、数据源：Phoenix Observability

### Phoenix 已记录的完整信息

| 信息 | 是否包含 | 位置 |
|------|----------|------|
| 完整 System Prompt | ✅ | `metadata.chat_inputs` |
| 完整消息历史 | ✅ | `metadata.chat_inputs` (messages 列表) |
| LLM 输入/输出 | ✅ | `attributes.input.value`, `attributes.output.value` |
| Tool 调用参数 | ✅ | `metadata.tool_inputs` |
| Tool 执行结果 | ✅ | `metadata.tool_outputs` |
| Token 统计 | ✅ | `llm.token_count.*` |
| 错误信息 | ✅ | `span.status`, `events` |
| Trace/Span 关系 | ✅ | `context.trace_id`, `context.span_id` |

### 数据访问方式

```python
from phoenix.client import Client

px_client = Client(base_url="http://localhost:6006")

# 导出指定项目的所有 spans
df = px_client.spans.get_spans_dataframe(
    project_name="sandbox-agent-gaia-20samples-gpt52"
)

# 按 trace_id 分组获取完整轨迹
traces = df.groupby("context.trace_id")
```

### 优势：无需修改代码

- Phoenix 已经在评估时记录了完整数据
- 直接从 Phoenix API 导出即可分析
- 支持时间范围过滤和项目隔离

---

## 二、失败分类体系（9 类主因）

| 类别 | 描述 | 检测方式 |
|------|------|----------|
| **任务理解失败** | 读错约束、忽略输入一部分、目标偏差 | LLM 归因 |
| **计划/分解失败** | 没拆步骤、拆错顺序、缺关键子任务 | LLM 归因 |
| **工具选择失败** | 该用 A 用了 B；该用工具却硬猜 | 规则 + LLM |
| **工具调用失败** | 参数错、权限/网络/超时、输出解析错 | **规则检测** |
| **证据/检索失败** | 召回不到、引用错、看了却没用上 | 规则 + LLM |
| **推理/计算失败** | 中间计算错误、单位/边界条件错 | LLM 归因 |
| **状态/记忆失败** | 多轮上下文丢失、跨 step 变量覆盖 | 规则 + LLM |
| **策略/安全边界失败** | 不该做的做了、该拒绝的没拒绝 | 规则 + LLM |
| **输出格式失败** | schema 不符、JSON 不可 parse、缺字段 | **规则检测** |

---

## 三、Failure Packet 数据结构

```python
class FailurePacket(BaseModel):
    """可复盘证据包 - 每个失败 case 必须保存"""

    # 1. 输入
    task_id: str
    user_request: str  # 原始用户请求
    system_prompt: str  # 完整 system prompt
    config: dict  # 模型、temperature、tool 列表

    # 2. 轨迹
    spans: list[SpanSummary]  # 压缩后的 span 列表

    # 3. 状态快照
    state_diffs: list[StateDiff]  # 每步 state 变化

    # 4. 评测结果
    expected_output: str
    actual_output: str
    eval_result: EvalResult  # pass/fail + 指标 + evaluator 解释

    # 5. 可重放信息
    run_id: str
    prompt_version: str
    code_version: str  # git commit
    tool_schema_version: str
    random_seed: Optional[int]

class SpanSummary(BaseModel):
    """压缩后的 span 信息"""
    span_type: str  # "llm" | "tool" | "router" | "retriever"
    name: str
    status: str  # "OK" | "ERROR"
    duration_ms: float

    # LLM 特有
    model: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    output_summary: Optional[str]  # 截断到 500 字符

    # Tool 特有
    tool_name: Optional[str]
    tool_args: Optional[dict]
    tool_result_summary: Optional[str]  # 截断到 500 字符
    error_message: Optional[str]
```

---

## 四、二段式归因流程

### 第一段：确定性归因（规则/程序）

优先检测"非智能问题"，直接从 span 属性判定：

```python
class RuleBasedClassifier:
    def classify(self, packet: FailurePacket) -> Optional[FailureCategory]:
        # 1. Tool 调用错误
        for span in packet.spans:
            if span.span_type == "tool" and span.status == "ERROR":
                if "timeout" in span.error_message.lower():
                    return FailureCategory.TOOL_TIMEOUT
                if "rate limit" in span.error_message.lower():
                    return FailureCategory.TOOL_RATE_LIMIT
                if "500" in span.error_message:
                    return FailureCategory.TOOL_SERVER_ERROR

        # 2. Schema 不匹配
        if "parse" in packet.eval_result.reason.lower():
            return FailureCategory.OUTPUT_FORMAT

        # 3. 检索为空
        for span in packet.spans:
            if span.span_type == "retriever" and span.docs_returned == 0:
                return FailureCategory.RETRIEVAL_EMPTY

        # 4. Context 超限
        total_tokens = sum(s.prompt_tokens + s.completion_tokens
                          for s in packet.spans if s.span_type == "llm")
        if total_tokens > 120000:  # 接近限制
            return FailureCategory.CONTEXT_OVERFLOW

        return None  # 需要 LLM 归因
```

### 第二段：语义归因（LLM as Triage）

对规则无法判定的 case，使用 LLM 分析：

```python
LLM_TRIAGE_PROMPT = """
你是一个 Agent 失败分析专家。请分析以下失败案例并给出：

1. **主因标签**（只选一个）：
   - 任务理解失败
   - 计划/分解失败
   - 工具选择失败
   - 证据利用失败
   - 推理/计算失败
   - 状态/记忆失败

2. **关键证据定位**：指出哪几个 span 是拐点

3. **修复建议**：
   - 改 prompt/policy?
   - 加 verifier?
   - 改 tool 调用策略?
   - 其他?

## 失败案例

任务: {task}
期望输出: {expected}
实际输出: {actual}
评估原因: {eval_reason}

## 执行轨迹

{spans_json}
"""
```

---

## 五、ROI 优先级排序

### 失败看板维度

```python
class FailureDashboard:
    def calculate_priority(self, category: FailureCategory) -> float:
        """
        优先级 = 频次 × 影响度 × 可修复性 × 可验证性
        """
        stats = self.get_category_stats(category)

        frequency = stats.count / self.total_failures  # 0-1
        impact = self.IMPACT_WEIGHTS[category]  # 1-5
        fixability = 1 / self.EFFORT_WEIGHTS[category]  # 1/1, 1/2, 1/3
        verifiability = 1.0 if stats.has_test_cases else 0.5

        return frequency * impact * fixability * verifiability
```

### 优先级排序规则

1. **高优先**：高影响 + 高频 + 易修（工具超时、格式错误）
2. **中优先**：高影响 + 中频（工具选择、证据利用）
3. **低优先**：低影响 + 高频（格式化细节）

---

## 六、常见修复模板

| 失败类型 | 修复模板 | 实施难度 |
|----------|----------|----------|
| **工具调用失败** | 添加 retry + fallback + timeout | Low |
| **输出格式失败** | 强制 JSON schema + repair loop | Low |
| **计划不足** | Plan-Execute 分离 + verify step | Medium |
| **工具选择错误** | 改进 tool description + few-shot | Low |
| **推理错误** | 加 self-check / 轻量 verifier | Medium |
| **证据利用失败** | 强制 claim → evidence 绑定 | Medium |
| **Context 超限** | 添加摘要中间件 | Medium |

---

## 七、实施步骤

所有代码统一放在 `src/nat_sandbox_agent/analysis/` 下，作为包的一部分可被复用。

### 文件结构

```
src/nat_sandbox_agent/analysis/
├── __init__.py
├── models.py              # FailurePacket, SpanSummary 等数据结构
├── phoenix_exporter.py    # Phoenix 数据导出
├── rule_classifier.py     # 规则分类器
├── llm_triage.py          # LLM 归因
├── dashboard.py           # 失败看板 + HTML 报告
└── cli.py                 # CLI 入口
```

### Phase 1: 数据模型和 Phoenix 数据导出

**新建文件**:
- `models.py` - FailurePacket, SpanSummary 等数据结构
- `phoenix_exporter.py` - 从 Phoenix 导出 trace 数据

**功能**:
```python
# 1. 连接 Phoenix
px_client = Client(base_url="http://localhost:6006")

# 2. 导出 spans
df = px_client.spans.get_spans_dataframe(project_name="...")

# 3. 按 trace_id 重组为 Failure Packet
# 4. 关联 workflow_output.json 中的 expected/actual
# 5. 输出 failure_packets.jsonl
```

### Phase 2: 实现规则分类器

**新建文件**:
- `rule_classifier.py`

**功能**: 从 Failure Packet 中检测工具错误、格式错误、Context 超限

### Phase 3: 实现 LLM 归因

**新建文件**:
- `llm_triage.py`

**功能**: 对规则无法判定的 case 进行语义归因

### Phase 4: 失败看板和报告

**新建文件**:
- `dashboard.py` - 生成 HTML 报告 + ROI 排序
- `cli.py` - CLI 入口，支持命令行调用

---

## 八、验证方法

1. **Phoenix 数据验证**: 确认 Phoenix 中有完整的 trace 数据
   ```bash
   # 访问 Phoenix UI
   open http://localhost:6006
   # 查看项目 sandbox-agent-gaia-20samples-gpt52
   ```

2. **数据导出验证**:
   ```bash
   python -m nat_sandbox_agent.analysis.cli export \
     --project sandbox-agent-gaia-20samples-gpt52 \
     --output .tmp/failure_packets.jsonl
   ```

3. **端到端验证**:
   ```bash
   # 运行失败分析
   python -m nat_sandbox_agent.analysis.cli analyze \
     --packets .tmp/failure_packets.jsonl \
     --eval-output .tmp/nat/sandbox_agent/gaia_eval_20samples_gpt52/

   # 查看报告
   open .tmp/nat/sandbox_agent/gaia_eval_20samples_gpt52/failure_report.html
   ```

---

## 九、关键文件

| 文件 | 用途 |
|------|------|
| `src/nat_sandbox_agent/analysis/models.py` | FailurePacket, SpanSummary 等数据结构 |
| `src/nat_sandbox_agent/analysis/phoenix_exporter.py` | 从 Phoenix 导出 trace → Failure Packet |
| `src/nat_sandbox_agent/analysis/rule_classifier.py` | 规则分类器 |
| `src/nat_sandbox_agent/analysis/llm_triage.py` | LLM 归因 |
| `src/nat_sandbox_agent/analysis/dashboard.py` | 失败看板 + HTML 报告 |
| `src/nat_sandbox_agent/analysis/cli.py` | CLI 入口 |

---

## 十、数据流

```
Phoenix (已有数据)
    ↓
nat_sandbox_agent.analysis.phoenix_exporter
    导出 spans → 重组为 Failure Packet
    ↓
failure_packets.jsonl
    ↓
┌───────────────────────────────────┐
│ nat_sandbox_agent.analysis.rule_classifier
│ 第一段：规则分类器               │
│ - Tool 错误 (timeout/500/rate)   │
│ - 格式错误 (JSON parse fail)     │
│ - Context 超限                    │
└───────────────────────────────────┘
    ↓ 无法判定的 case
┌───────────────────────────────────┐
│ nat_sandbox_agent.analysis.llm_triage
│ 第二段：LLM 归因                 │
│ - 任务理解/计划/工具选择失败     │
│ - 推理/证据利用/状态失败         │
└───────────────────────────────────┘
    ↓
nat_sandbox_agent.analysis.dashboard
    ↓
failure_report.html
    - 失败类别分布
    - ROI 优先级排序
    - 修复建议
```
