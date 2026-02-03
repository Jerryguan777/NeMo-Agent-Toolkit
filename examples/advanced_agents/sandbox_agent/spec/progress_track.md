# Sandbox Agent 开发进度追踪

本文档记录 Sandbox Agent 项目的每日开发进展。

---

## [1/22/2026] 

### 今日工作
- 根据计划移除所有 v2 相关代码，恢复为纯 v1 实现
- 重新运行 GAIA Level 1/2/3 评估
- 详细分析 v1 架构实现细节

### v2 代码移除

**删除的文件:**
- `src/nat_sandbox_agent/agent/` 目录 (planner.py, verifier.py, reflector.py)
- `src/nat_sandbox_agent/register_v2.py`
- `src/nat_sandbox_agent/tools/core_tools.py`
- `src/nat_sandbox_agent/prompts/gaia_prompt.py`
- `src/nat_sandbox_agent/configs/config_gaia_v2.yaml`
- `tests/test_agent.py`, `tests/test_tools.py`, `tests/test_workflow.py`
- `spec/design_draft_v2.md`

**修改的文件:**
- `src/nat_sandbox_agent/__init__.py` - 移除 register_v2 导入
- `src/nat_sandbox_agent/prompts/__init__.py` - 移除 gaia_prompt 导入
- `src/nat_sandbox_agent/tools/__init__.py` - 移除 core_tools 导入
- `tests/test_prompts.py` - 保留 v1 测试

### GAIA 评估结果 (v1)

| 级别 | 样本数 | 准确率 | 平均运行时间(秒) | LLM延迟(秒) | LLM调用次数 |
|------|--------|--------|------------------|-------------|-------------|
| **Level 1** | 53 | **33.96%** | 34.19 | 3.07 | 7.51 |
| **Level 2** | 86 | **10.76%** | 38.53 | 3.47 | 8.76 |
| **Level 3** | 26 | **7.69%** | 44.08 | 7.87 | 8.15 |

---

### v1 架构详细分析

#### 一、Agent 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Sandbox Agent Workflow                    │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐    ┌──────────┐    ┌─────────────────────────┐ │
│  │  START  │───▶│  Agent   │───▶│ should_continue?        │ │
│  └─────────┘    │  Node    │    │ ├─ has tool_calls → tools│ │
│                 │(LLM+思考)│    │ └─ no tool_calls → END   │ │
│                 └──────────┘    └─────────────────────────┘ │
│                       ▲                     │               │
│                       │                     ▼               │
│                       │              ┌──────────┐           │
│                       └──────────────│  Tools   │           │
│                                      │  Node    │           │
│                                      └──────────┘           │
├─────────────────────────────────────────────────────────────┤
│                    Docker/Daytona Sandbox                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  /workspace                                           │   │
│  │  ├── input/    (用户上传文件)                         │   │
│  │  ├── output/   (生成的输出文件)                       │   │
│  │  ├── temp/     (临时文件)                             │   │
│  │  └── downloads/ (下载文件)                            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**核心组件 (register.py):**

| 组件 | 描述 |
|------|------|
| **AgentState** | TypedDict状态，包含`messages`, `iteration_count`, `sandbox_id` |
| **agent_node** | LLM推理节点，调用绑定工具的LLM |
| **should_continue** | 条件边，判断是否有tool_calls |
| **ToolNode** | LangGraph预置工具执行节点 |

**执行流程:**
```
User Input → HumanMessage → Agent(LLM) → Tool Calls?
                              ↓ Yes           ↓ No
                         ToolNode执行     返回最终答案
                              ↓
                         Tool Results
                              ↓
                         Agent(继续推理)
```

#### 二、工具列表 (12个工具)

| 工具名称 | 输入参数 | 功能描述 |
|----------|----------|----------|
| **shell** | `command`, `working_dir` | 在沙箱中执行bash命令 |
| **python** | `code` | 执行Python代码 |
| **read_file** | `path` | 读取文件内容 |
| **write_file** | `path`, `content` | 写入文件 |
| **list_files** | `path` | 列出目录内容 |
| **delete_file** | `path` | 删除文件/目录 |
| **web_search** | `query`, `num_results` | 使用Tavily API搜索网络 |
| **browser_navigate** | `url` | 打开URL并截图 |
| **browser_extract** | `url`, `selector` | 提取网页文本内容 |
| **download_file** | `url`, `save_path` | 下载文件到沙箱 |
| **youtube_transcript** | `url`, `language` | 获取YouTube视频字幕 |
| **generate_document** | `format`, `content`, `filename`, `title` | 生成文档(md/pdf/docx/pptx/html) |

#### 三、System Prompt 结构

```markdown
You are a powerful AI assistant with access to an isolated sandbox environment...

## Your Capabilities
### Code Execution
- shell: 执行bash命令
- python: 执行Python代码

### File Operations
- read_file, write_file, list_files, delete_file, download_file

### Web Operations
- web_search, browser_navigate, browser_extract, youtube_transcript

### Document Generation
- generate_document (md/pdf/docx/pptx/html)

## Sandbox Environment
- /workspace/input  - 用户上传文件
- /workspace/output - 生成输出文件
- /workspace/temp   - 临时文件

## CRITICAL RULES
1. **NEVER guess** - 必须使用工具
2. **NEVER assume facts** - 必须搜索验证
3. **Check /workspace/input** - 附件文件位置
4. **Answer format** - 只返回最终答案，不要解释

## Problem-Solving Strategy
- 分解复杂任务
- 使用适当工具
- 优雅处理错误
- 验证答案
```

**Prompt 关键特点:**
1. 强调**必须使用工具**，禁止猜测
2. 明确**答案格式要求**（只返回答案，不要解释）
3. 提供**问题解决策略**
4. 说明**沙箱目录结构**

#### 四、关键配置参数

```yaml
workflow:
  _type: sandbox_agent
  llm_name: agent_llm           # LLM引用
  max_iterations: 50            # 最大迭代次数
  max_observation_tokens: 20000 # 工具输出截断长度

  sandbox_config:
    type: docker                # docker 或 daytona
    image: "nat-sandbox:latest"
    memory_limit: "4g"
    cpu_limit: 4.0
    network_enabled: true       # 允许网络访问
    volumes:                    # 挂载卷
      "/host/path": "/workspace/input"
```

#### 五、Context/重试/截断机制分析

| 机制 | 是否实现 | 详情 |
|------|----------|------|
| **Context 累积** | ✅ | 使用 LangGraph `add_messages`，所有消息不断累积 |
| **Tool 结果截断** | ✅ | 默认 50,000 字符，防止输出过长 |
| **LLM 调用重试** | ✅ | NAT RetryMixin: 5次重试，针对 429/500/502/503/504 |
| **Tool 调用重试** | ❌ | 无，依赖 LLM 重新规划 |
| **Context 压缩** | ❌ | 无，可能导致 context overflow |

**Tool 结果截断实现:**
```python
# tools/executor.py
class SandboxToolExecutor:
    def __init__(self, sandbox, max_output_chars=50000):
        self.max_output_chars = max_output_chars

    def _truncate_output(self, text: str) -> str:
        if len(text) > self.max_output_chars:
            return text[:self.max_output_chars] + f"\n... (truncated, {len(text)} total chars)"
        return text
```

**LLM 重试机制 (NAT 框架):**
```python
# nat/data_models/retry_mixin.py
class RetryMixin(BaseModel):
    do_auto_retry: bool = True          # 默认启用
    num_retries: int = 5                # 重试5次
    retry_on_status_codes: list = [429, 500, 502, 503, 504]
    retry_on_errors: list = ["Too Many Requests"]
```

**Context 累积问题:**
- 使用 `add_messages` 注解，每次迭代追加消息
- 没有压缩机制，随迭代增长
- 可能超过 LLM context window (评估中出现过: "223378 tokens > 131072 limit")
- 仅靠 `max_iterations` 间接限制

#### 六、v1 设计特点与局限

**优点:**
- 简单的 ReAct 循环架构
- 丰富的工具集（12个工具）
- 隔离的沙箱环境
- NAT 框架内置 LLM 重试

**局限:**
- 没有规划阶段（Plan）
- 没有验证阶段（Verify）
- 没有反思阶段（Reflect）
- 没有 Context 压缩机制
- Tool 执行无重试
- 依赖 LLM 自己决定何时停止

---

### GPT 5.2 评估结果

将 Agent LLM 从 Llama 3.3 70B 更换为 GPT 5.2 后重新运行评估。

#### Level 2 完整评估 (86 samples)

| 指标 | 结果 |
|------|------|
| **准确率** | **25.58%** (22/86) |
| **平均运行时间** | 45.2秒 |
| **平均 LLM 调用次数** | 12.3 |

**对比 Llama 3.3 70B:**
- GPT 5.2: 25.58% vs Llama 3.3 70B: 10.76%
- **提升: +14.82 个百分点 (2.4倍)**

#### 20 样本评估 (10 Level 2 + 10 Level 3)

随机选取 10 个 Level 2 和 10 个 Level 3 样本进行评估。

| 级别 | 样本数 | 正确数 | 准确率 |
|------|--------|--------|--------|
| **Level 2** | 10 | 4 | **40.0%** |
| **Level 3** | 10 | 1 | **10.0%** |
| **总计** | 20 | 5 | **25.0%** |

**性能指标:**
- 平均运行时间: 49.12 秒/样本
- 平均 LLM 调用次数: 18.65 次/样本

**遇到的问题:**
1. **Tavily API 配额耗尽** - 部分样本无法执行网络搜索
2. **OpenAI 内容策略错误** - 3 个样本触发 400 错误 (content policy violation)
3. **OpenAI API 速率限制** - 评估阶段遇到 429 错误

**配置文件:**
- Level 2 完整评估: `config_gaia_level2_gpt52.yaml`
- 20 样本评估: `config_gaia_20samples_gpt52.yaml`

**Observability:**
- Phoenix tracing 已启用
- 项目名: `sandbox-agent-gaia-20samples-gpt52`
- Endpoint: `http://localhost:6006/v1/traces`

---

<!-- 后续进度追加在此处 -->
<!-- 格式示例:
## [MM/DD/YYYY] 简要标题

### 今日工作
- 工作项 1
- 工作项 2

### 遇到的问题
- 问题描述

### 明日计划
- 计划项 1
-->
