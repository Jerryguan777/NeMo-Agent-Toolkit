# Sandbox Agent 设计文档 v1

## 一、项目背景与定位

### 1.1 项目目标

在 NeMo-Agent-Toolkit (NAT) 的 `examples/advanced_agents/` 目录下创建一个 **sandbox_agent** 示例项目，用于展示 NAT 框架的以下能力：

- **沙盒安全能力**：在隔离环境中执行代码、命令和文件操作
- **工具集成能力**：集成多种工具类型（文件、网络、代码、浏览器）
- **通用 Agent 构建模式**：作为通用助手的参考实现
- **生产级应用能力**：安全、错误处理、资源管理
- **可扩展性**：易于添加新工具，展示 NAT 的可扩展架构

### 1.2 参考项目

本项目参考 OpenManus 的功能设计，但完全基于 NAT 框架实现，充分利用 NAT 提供的：
- Workflow 注册机制
- Agent 注册机制
- Tool 注册机制
- Evaluation 系统
- Observability 集成
- FastAPI 前端

### 1.3 评估方式

- 使用 GAIA 测试集上的 selected tasks 进行评估
- 未来扩展支持 Scale AI 的 RLI 测试集

---

## 二、核心能力

Sandbox Agent 具备六大核心能力，**所有操作均在隔离的沙盒环境中执行**：

| 能力 | 说明 | 实现方式 |
|------|------|---------|
| **Shell 命令执行** | 在沙盒中运行任意 Shell 命令 | `sandbox.run_command()` |
| **Python 代码执行** | 运行 Python 脚本，支持数据处理和可视化 | `sandbox.run_python()` |
| **文件操作** | 读取、写入、列表、删除、上传、下载文件 | `sandbox.read_file()` 等 |
| **浏览器操作** | 页面导航、点击、输入、截图、内容提取 | 在沙盒中运行 Playwright |
| **网络搜索** | 集成搜索引擎，汇总搜索结果 | 在沙盒中调用 duckduckgo-search |
| **文档生成** | 生成 PDF、Word、PPT、Markdown 等格式文档 | 在沙盒中调用 python-pptx 等 |

---

## 三、架构设计

### 3.1 Session 与 Sandbox 的关系

采用 **1 Session = 1 Sandbox** 的设计原则：

```
┌─────────────────────────────────────────────────────────────────┐
│                        NAT Sandbox Agent                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User A ─┬─ Session A1 ──► Sandbox A1 (Docker Container)       │
│          └─ Session A2 ──► Sandbox A2 (Docker Container)       │
│                                                                 │
│  User B ─┬─ Session B1 ──► Sandbox B1 (Docker Container)       │
│          └─ Session B2 ──► Sandbox B2 (Docker Container)       │
│                                                                 │
│  每个 Sandbox 完全隔离：独立文件系统、网络、进程空间             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**设计要点**：
- 每个用户会话创建一个独立的 Docker 容器或 Daytona 沙盒
- 该会话中的所有工具共享同一个沙盒实例和文件系统
- 会话结束时释放沙盒资源
- 多用户、多会话之间完全隔离

### 3.2 工具与 Sandbox 的绑定

工具不独立注册到 NAT，而是在 Workflow 级别通过**闭包绑定**到 Sandbox 实例：

```
Workflow 启动
    ↓
创建 Sandbox 实例
    ↓
创建工具集（闭包绑定 Sandbox）
    ↓
构建 LangGraph Agent
    ↓
处理用户请求（所有工具共享 Sandbox 状态）
    ↓
Workflow 结束，释放 Sandbox
```

**原因**：
- 确保所有工具共享同一个 Sandbox 实例
- 工具之间可以共享文件系统状态
- 简化生命周期管理

### 3.3 所有工具在 Sandbox 中运行

为了安全隔离和状态一致性，**所有工具都在 Sandbox 中执行**：

```
┌─────────────────────────────────────────────────────────────────┐
│                    Sandbox (Docker/Daytona)                     │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                 /workspace (共享文件系统)                   │ │
│  │  ├── input/       # 用户上传                              │ │
│  │  ├── output/      # 生成结果                              │ │
│  │  ├── temp/        # 临时文件                              │ │
│  │  └── downloads/   # 浏览器下载                            │ │
│  └───────────────────────────────────────────────────────────┘ │
│       ▲         ▲         ▲         ▲         ▲               │
│       │         │         │         │         │               │
│  ┌────┴───┐ ┌───┴───┐ ┌───┴───┐ ┌───┴────┐ ┌──┴─────┐        │
│  │ Shell  │ │Python │ │ File  │ │Browser │ │WebSearch│        │
│  │        │ │       │ │       │ │(Playwright)│(HTTP) │        │
│  └────────┘ └───────┘ └───────┘ └────────┘ └────────┘        │
│                                                                 │
│  预装: Python, Chromium, Playwright, duckduckgo-search, etc.   │
│  网络: 已启用 (network_enabled=True)                           │
└─────────────────────────────────────────────────────────────────┘
```

**优势**：
- 安全隔离：浏览器/网络请求都在容器内，不影响主机
- 状态共享：浏览器下载的文件可以被 Python/Shell 直接访问
- 一致性：所有工具看到的是同一个文件系统
- 清理简单：Session 结束销毁容器，所有状态清除
- 资源控制：统一的 CPU/内存限制

---

## 四、统一的 Sandbox 接口

### 4.1 接口设计（ABC）

设计统一的 `BaseSandbox` 抽象基类，支持 Docker 和 Daytona 两种实现：

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict

class SandboxState(Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    ARCHIVED = "archived"
    ERROR = "error"

@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.exit_code == 0

@dataclass
class SandboxInfo:
    id: str
    state: SandboxState
    created_at: float
    vnc_url: Optional[str] = None
    web_url: Optional[str] = None
    memory_limit: Optional[str] = None
    cpu_limit: Optional[float] = None


class BaseSandbox(ABC):
    """Sandbox 抽象基类"""

    # ============ 生命周期 ============

    @abstractmethod
    async def start(self) -> SandboxInfo:
        """启动 Sandbox"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止 Sandbox（可恢复）"""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """销毁 Sandbox（不可恢复）"""
        pass

    @abstractmethod
    async def get_state(self) -> SandboxState:
        """获取当前状态"""
        pass

    @abstractmethod
    async def get_info(self) -> SandboxInfo:
        """获取详细信息"""
        pass

    # ============ 命令执行 ============

    @abstractmethod
    async def run_command(
        self,
        command: str,
        working_dir: str = "/workspace",
        timeout: float = 120,
        env: Optional[Dict[str, str]] = None
    ) -> CommandResult:
        """执行 Shell 命令"""
        pass

    @abstractmethod
    async def run_python(
        self,
        code: str,
        timeout: float = 60
    ) -> CommandResult:
        """执行 Python 代码"""
        pass

    # ============ 文件操作 ============

    @abstractmethod
    async def read_file(self, path: str) -> str:
        """读取文件内容"""
        pass

    @abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        """写入文件"""
        pass

    @abstractmethod
    async def list_files(self, path: str = "/workspace") -> list[str]:
        """列出目录内容"""
        pass

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """检查文件是否存在"""
        pass

    @abstractmethod
    async def delete_file(self, path: str) -> None:
        """删除文件"""
        pass

    # ============ 文件传输 ============

    @abstractmethod
    async def upload_bytes(self, data: bytes, sandbox_path: str) -> None:
        """上传字节数据到 Sandbox"""
        pass

    @abstractmethod
    async def download_bytes(self, sandbox_path: str) -> bytes:
        """从 Sandbox 下载字节数据"""
        pass

    # ============ 浏览器支持（可选覆盖）============

    async def get_browser_vnc_url(self) -> Optional[str]:
        """获取浏览器 VNC URL，默认返回 None"""
        return None

    async def get_browser_web_url(self) -> Optional[str]:
        """获取 Web 预览 URL，默认返回 None"""
        return None

    # ============ 上下文管理 ============

    async def __aenter__(self) -> "BaseSandbox":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()
```

### 4.2 Docker 实现

```python
class DockerSandbox(BaseSandbox):
    """Docker 本地沙盒实现"""

    def __init__(
        self,
        image: str = "python:3.12-slim",
        memory_limit: str = "512m",
        cpu_limit: float = 1.0,
        network_enabled: bool = True,
        work_dir: str = "/workspace"
    ):
        # 初始化 Docker 客户端和配置
        ...

    async def start(self) -> SandboxInfo:
        # 创建并启动 Docker 容器
        ...

    async def run_command(self, command: str, ...) -> CommandResult:
        # 通过 docker exec 执行命令
        ...

    # 实现其他抽象方法...
```

### 4.3 Daytona 实现

```python
class DaytonaSandbox(BaseSandbox):
    """Daytona 云端沙盒实现"""

    def __init__(
        self,
        api_key: str,
        server_url: str,
        target: str = "us",
        image: str = "daytonaio/workspace:latest",
        cpu: int = 2,
        memory: int = 4,  # GB
        disk: int = 10,   # GB
    ):
        # 初始化 Daytona 客户端
        ...

    async def start(self) -> SandboxInfo:
        # 创建 Daytona Sandbox
        ...

    async def get_browser_vnc_url(self) -> Optional[str]:
        # 返回 VNC 预览 URL
        info = await self.get_info()
        return info.vnc_url

    # 实现其他抽象方法...
```

### 4.4 工厂函数

```python
from enum import Enum
from typing import Union
from pydantic import BaseModel, Field

class SandboxType(str, Enum):
    DOCKER = "docker"
    DAYTONA = "daytona"

class DockerSandboxConfig(BaseModel):
    type: Literal["docker"] = "docker"
    image: str = "python:3.12-slim"
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    network_enabled: bool = True
    work_dir: str = "/workspace"

class DaytonaSandboxConfig(BaseModel):
    type: Literal["daytona"] = "daytona"
    api_key: str
    server_url: str
    target: str = "us"
    image: str = "daytonaio/workspace:latest"
    cpu: int = 2
    memory: int = 4
    disk: int = 10

SandboxConfig = Union[DockerSandboxConfig, DaytonaSandboxConfig]

def create_sandbox(config: SandboxConfig) -> BaseSandbox:
    """根据配置创建 Sandbox 实例"""
    if config.type == "docker":
        return DockerSandbox(...)
    elif config.type == "daytona":
        return DaytonaSandbox(...)
    else:
        raise ValueError(f"Unknown sandbox type: {config.type}")
```

### 4.5 启动时间对比

| 场景 | Docker Sandbox | Daytona Sandbox |
|------|---------------|-----------------|
| 冷启动（需拉取镜像） | 30秒 - 几分钟 | 10-30秒（云端预热） |
| 温启动（镜像已存在） | 1-5秒 | 5-15秒（API 调用） |
| 热启动（容器已存在但停止） | < 1秒 | 5-10秒 |
| 已运行状态 | 即时 | 即时 |

**Overhead 分析**：抽象层 overhead 可忽略不计（< 1ms），主要耗时在 Docker API / Daytona API 调用。

---

## 五、NAT 框架集成

### 5.1 Workflow 注册

使用 NAT 的 `@register_function` 装饰器注册 Workflow：

```python
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig
from nat.data_models.function_ref import LLMRef
from nat.llm.wrapper import LLMFrameworkEnum

class SandboxAgentWorkflowConfig(FunctionBaseConfig, name="sandbox_agent"):
    """Sandbox Agent 工作流配置"""

    llm_name: LLMRef = Field(description="主 LLM 引用")
    max_iterations: int = Field(default=20, description="最大迭代次数")
    sandbox_config: SandboxConfig = Field(description="沙盒配置")

@register_function(
    config_type=SandboxAgentWorkflowConfig,
    framework_wrappers=[LLMFrameworkEnum.LANGCHAIN]
)
async def sandbox_agent_workflow(config: SandboxAgentWorkflowConfig, builder):

    # 1. 从 builder context 获取 session 信息
    session_id = builder.context.get("session_id", str(uuid.uuid4()))

    # 2. 创建该 session 专属的 sandbox
    sandbox = create_sandbox(config.sandbox_config)
    await sandbox.start()

    try:
        # 3. 创建绑定到这个 sandbox 的工具
        tools = create_sandbox_tools(sandbox)

        # 4. 获取 LLM
        llm = await builder.get_llm(config.llm_name, wrapper_type=LLMFrameworkEnum.LANGCHAIN)

        # 5. 构建 LangGraph Agent
        agent_graph = build_agent_graph(llm, tools, config)

        # 6. 定义响应函数
        async def _response_fn(message: str) -> str:
            result = await agent_graph.ainvoke({"messages": [HumanMessage(content=message)]})
            return result["messages"][-1].content

        yield _response_fn

    finally:
        # 7. 释放 Sandbox
        await sandbox.cleanup()
```

### 5.2 工具创建（闭包绑定）

```python
def create_sandbox_tools(sandbox: BaseSandbox) -> list:
    """创建绑定到特定 sandbox 的工具集"""

    executor = SandboxToolExecutor(sandbox)

    return [
        StructuredTool.from_function(
            coroutine=executor.execute_shell,
            name="shell",
            description="在沙盒中执行 Shell 命令"
        ),
        StructuredTool.from_function(
            coroutine=executor.execute_python,
            name="python",
            description="在沙盒中执行 Python 代码"
        ),
        StructuredTool.from_function(
            coroutine=executor.web_search,
            name="web_search",
            description="执行网络搜索"
        ),
        StructuredTool.from_function(
            coroutine=executor.browser_navigate,
            name="browser",
            description="控制浏览器"
        ),
        StructuredTool.from_function(
            coroutine=executor.read_file,
            name="read_file",
            description="读取文件"
        ),
        StructuredTool.from_function(
            coroutine=executor.write_file,
            name="write_file",
            description="写入文件"
        ),
        StructuredTool.from_function(
            coroutine=executor.generate_document,
            name="document",
            description="生成文档"
        ),
    ]
```

### 5.3 Agent Graph 构建

使用 LangGraph StateGraph 实现 ReAct 模式：

```python
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

def build_agent_graph(llm, tools, config):
    """构建 Agent 执行图"""

    llm_with_tools = llm.bind_tools(tools)

    class AgentState(TypedDict):
        messages: Annotated[list, add_messages]
        iteration_count: int

    async def agent_node(state: AgentState):
        # LLM 推理，决定工具调用
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response], "iteration_count": state["iteration_count"] + 1}

    def should_continue(state: AgentState):
        # 检查是否继续执行
        if state["iteration_count"] >= config.max_iterations:
            return END
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    # 构建图
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()
```

### 5.4 YAML 配置示例

```yaml
# configs/sandbox_agent.yaml

llms:
  agent_llm:
    _type: nim
    model_name: meta/llama-3.3-70b-instruct
    temperature: 0.0
    max_tokens: 4096

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

### 5.5 入口点配置

```toml
# pyproject.toml

[project.entry-points.'nat.components']
nat_sandbox_agent = "nat_sandbox_agent.register"
```

---

## 六、工具执行层

### 6.1 SandboxToolExecutor

```python
class SandboxToolExecutor:
    """所有工具的统一执行层，绑定到特定 Sandbox 实例"""

    def __init__(self, sandbox: BaseSandbox):
        self.sandbox = sandbox

    # ============ Shell 命令 ============

    async def execute_shell(self, command: str, working_dir: str = "/workspace") -> dict:
        result = await self.sandbox.run_command(command, working_dir=working_dir)
        return {
            "status": "success" if result.success else "error",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code
        }

    # ============ Python 代码 ============

    async def execute_python(self, code: str) -> dict:
        result = await self.sandbox.run_python(code)
        return {
            "status": "success" if result.success else "error",
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    # ============ Web Search（在 Sandbox 中执行）============

    async def web_search(self, query: str, num_results: int = 5) -> dict:
        code = f'''
import json
from duckduckgo_search import DDGS

results = []
with DDGS() as ddgs:
    for r in ddgs.text("{query}", max_results={num_results}):
        results.append({{
            "title": r["title"],
            "url": r["href"],
            "snippet": r["body"]
        }})

print(json.dumps(results, ensure_ascii=False))
'''
        result = await self.sandbox.run_python(code, timeout=30)

        if result.success:
            import json
            return {"status": "success", "results": json.loads(result.stdout)}
        return {"status": "error", "error": result.stderr}

    # ============ Browser（在 Sandbox 中执行）============

    async def browser_navigate(self, url: str) -> dict:
        code = f'''
import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("{url}")
        await page.screenshot(path="/workspace/temp/screenshot.png")
        title = await page.title()
        result = {{"url": page.url, "title": title}}
        await browser.close()
        print(json.dumps(result))

asyncio.run(main())
'''
        result = await self.sandbox.run_python(code, timeout=60)

        if result.success:
            import json
            data = json.loads(result.stdout)
            screenshot = await self.sandbox.download_bytes("/workspace/temp/screenshot.png")
            import base64
            data["screenshot_base64"] = base64.b64encode(screenshot).decode()
            return {"status": "success", **data}
        return {"status": "error", "error": result.stderr}

    # ============ 文件操作 ============

    async def read_file(self, path: str) -> dict:
        try:
            content = await self.sandbox.read_file(path)
            return {"status": "success", "content": content}
        except FileNotFoundError:
            return {"status": "error", "error": f"File not found: {path}"}

    async def write_file(self, path: str, content: str) -> dict:
        await self.sandbox.write_file(path, content)
        return {"status": "success", "path": path}

    # ============ 文档生成 ============

    async def generate_document(self, format: str, content: str, filename: str) -> dict:
        output_path = f"/workspace/output/{filename}.{format}"

        if format == "md":
            await self.sandbox.write_file(output_path, content)
        elif format == "pdf":
            code = f'''
# 使用 reportlab 或 pandoc 生成 PDF
...
'''
            await self.sandbox.run_python(code)
        # 其他格式类似处理

        return {"status": "success", "output_path": output_path}
```

---

## 七、Sandbox 镜像

### 7.1 Dockerfile

```dockerfile
# Dockerfile for nat-sandbox
FROM python:3.12-slim

# 系统依赖
RUN apt-get update && apt-get install -y \
    # 浏览器
    chromium chromium-driver \
    # 字体
    fonts-noto-cjk \
    # 工具
    curl wget git jq \
    # 文档生成
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# Python 包
RUN pip install --no-cache-dir \
    # 浏览器自动化
    playwright \
    # 网络搜索
    duckduckgo-search \
    # 网络请求
    requests httpx beautifulsoup4 \
    # 数据处理
    pandas numpy matplotlib seaborn \
    # 文档生成
    python-pptx python-docx reportlab markdown \
    # Excel
    openpyxl xlrd

# 安装 Playwright 浏览器
RUN playwright install chromium

# 工作目录
WORKDIR /workspace
RUN mkdir -p input output temp downloads

# 非 root 用户
RUN useradd -m sandbox && chown -R sandbox:sandbox /workspace
USER sandbox
```

### 7.2 构建命令

```bash
docker build -t nat-sandbox:latest .
```

---

## 八、评估系统集成

### 8.1 GAIA 评估配置

```yaml
# configs/sandbox_agent_gaia.yaml

llms:
  agent_llm:
    _type: nim
    model_name: meta/llama-3.3-70b-instruct
  eval_llm:
    _type: nim
    model_name: meta/llama-3.3-70b-instruct

workflow:
  _type: sandbox_agent
  llm_name: agent_llm
  max_iterations: 30
  sandbox_config:
    type: docker
    image: "nat-sandbox:latest"
    memory_limit: "2g"
    network_enabled: true

eval:
  general:
    output_dir: .tmp/nat/sandbox_agent/gaia_eval/
    dataset:
      _type: json
      file_path: src/nat_sandbox_agent/data/gaia_selected_tasks.json

  evaluators:
    accuracy:
      _type: ragas
      metric: AnswerAccuracy
      llm_name: eval_llm

    trajectory:
      _type: trajectory
      llm_name: eval_llm

    runtime:
      _type: avg_workflow_runtime
```

### 8.2 运行评估

```bash
nat eval configs/sandbox_agent_gaia.yaml
```

---

## 九、可观测性集成

### 9.1 配置示例

```yaml
# 在配置文件中添加
observability:
  phoenix:
    _type: phoenix
    project_name: sandbox_agent
    endpoint: http://localhost:6006
    collect_input_output: true
    collect_tool_calls: true
```

### 9.2 支持的后端

- **Phoenix** - 推荐用于开发调试
- **Langfuse** - 推荐用于生产环境
- **Weave** - 可选

---

## 十、前端设计

### 10.1 设计决策

**采用 NAT 内置 UI**，而非自定义前端界面。

| 方案 | 说明 |
|------|------|
| ~~自定义 HTML/CSS/JS~~ | 需要额外开发三栏布局、WebSocket 处理等 |
| **NAT 内置 UI (nat-ui)** ✅ | 复用 NAT 现有组件，减少重复开发 |

**理由**：
- NAT 的 `external/nat-ui/` 已提供完整的聊天界面
- 支持 WebSocket 流式响应、Markdown 渲染、代码高亮
- 只需扩展 REST API 即可满足沙盒特有功能

### 10.2 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      NAT FastAPI Server                      │
├─────────────────────────────────────────────────────────────┤
│  NAT 内置端点              │  Sandbox 扩展端点              │
│  ├── POST /generate       │  ├── GET  /sandbox/status      │
│  ├── POST /chat           │  ├── GET  /sandbox/files       │
│  ├── WS   /websocket      │  ├── GET  /sandbox/files/content│
│  └── ...                  │  ├── POST /sandbox/files/upload │
│                           │  ├── GET  /sandbox/files/download│
│                           │  ├── GET  /sandbox/screenshot   │
│                           │  ├── GET  /sandbox/sessions     │
│                           │  └── DELETE /sandbox/cleanup    │
└─────────────────────────────────────────────────────────────┘
                              ↑
                    ┌─────────┴─────────┐
                    │   NAT UI (nat-ui)  │
                    │   聊天界面 + API调用 │
                    └───────────────────┘
```

### 10.3 Sandbox 扩展路由

扩展 NAT FastAPI 前端，添加沙盒专用 REST API：

```python
def create_sandbox_router(manager: SandboxManager) -> APIRouter:
    """创建沙盒专用路由"""
    router = APIRouter(prefix="/sandbox", tags=["sandbox"])

    @router.get("/status", response_model=SandboxStatusResponse)
    async def get_sandbox_status(session_id: str):
        """获取沙盒状态"""
        ...

    @router.get("/files", response_model=FileListResponse)
    async def list_files(session_id: str, path: str = "/workspace"):
        """列出目录内容"""
        ...

    @router.get("/files/content", response_model=FileContentResponse)
    async def get_file_content(session_id: str, path: str):
        """读取文件内容"""
        ...

    @router.post("/files/upload")
    async def upload_file(session_id: str, path: str, file: UploadFile):
        """上传文件到沙盒"""
        ...

    @router.get("/files/download")
    async def download_file(session_id: str, path: str):
        """从沙盒下载文件"""
        ...

    @router.get("/screenshot")
    async def get_screenshot(session_id: str):
        """获取浏览器截图"""
        ...

    @router.get("/sessions", response_model=SessionListResponse)
    async def list_sessions(user_id: Optional[str] = None):
        """列出活跃会话"""
        ...

    @router.delete("/cleanup")
    async def cleanup_sandbox(session_id: str):
        """清理沙盒实例"""
        ...

    return router
```

### 10.4 响应模型

```python
class SandboxStatusResponse(BaseModel):
    session_id: str
    state: str
    created_at: float
    memory_limit: Optional[str] = None
    cpu_limit: Optional[float] = None

class FileListResponse(BaseModel):
    path: str
    files: list[str]
    details: Optional[str] = None

class FileContentResponse(BaseModel):
    path: str
    content: str
    size: int

class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]
    total: int
    capacity: int
```

### 10.5 前端配置

```yaml
front_end:
  _type: fastapi
  host: 0.0.0.0
  port: 8000
  cors:
    allow_origins:
      - "http://localhost:3000"  # NAT UI 开发服务器
```

### 10.6 WebSocket 通信

**使用 NAT 内置的 WebSocket 处理**，无需自定义实现。

NAT 的 WebSocket 端点 (`/websocket`) 已支持：
- 流式响应 (streaming)
- 工具调用事件
- 错误处理

沙盒特有的文件操作、状态查询等通过 REST API 补充。

---

## 十一、项目结构

```
examples/advanced_agents/sandbox_agent/
├── pyproject.toml                    # 包配置，定义 NAT 入口点
├── README.md                         # 项目文档
├── Dockerfile                        # Sandbox 镜像定义
├── src/nat_sandbox_agent/
│   ├── __init__.py
│   ├── register.py                   # Workflow 注册
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── executor.py               # SandboxToolExecutor
│   │   └── factory.py                # LangChain 工具工厂
│   ├── sandbox/
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseSandbox (ABC)
│   │   ├── docker_sandbox.py         # Docker 实现
│   │   ├── daytona_sandbox.py        # Daytona 实现
│   │   ├── factory.py                # 工厂函数
│   │   └── manager.py                # 多 Session 管理
│   ├── ui/
│   │   ├── __init__.py
│   │   └── routes.py                 # Sandbox 扩展 REST API 路由
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── system_prompt.py          # 系统提示词
│   ├── configs/
│   │   ├── config.yaml               # 基础配置
│   │   ├── config_ui.yaml            # 带 UI 的配置
│   │   ├── config_daytona.yaml       # Daytona 云端配置
│   │   └── config_gaia.yaml          # GAIA 评估配置
│   └── data/
│       └── gaia_selected_tasks.json  # 测试数据
└── tests/
    ├── conftest.py                   # Pytest fixtures
    ├── test_sandbox.py               # Sandbox 基础接口测试
    ├── test_tools.py                 # 工具执行测试
    ├── test_workflow.py              # 工作流配置测试
    ├── test_prompts.py               # 提示词测试
    ├── test_routes.py                # API 路由测试
    ├── test_manager.py               # Session 管理测试
    └── test_docker_sandbox_integration.py  # Docker 集成测试
```

---

## 十二、关键设计决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| Session-Sandbox 关系 | 1:1 | 隔离性、状态一致性、清理简单 |
| 工具注册方式 | 闭包绑定而非独立注册 | 确保工具共享同一 Sandbox 实例 |
| Sandbox 接口 | ABC 抽象基类 | 强制实现、代码整齐 |
| 工具执行位置 | 全部在 Sandbox 中 | 安全隔离、状态共享 |
| Agent 模式 | LangGraph StateGraph | 与 NAT 现有模式一致 |
| 前端框架 | 扩展 NAT FastAPI | 复用 NAT 能力 |

---

## 十三、运行方式

```bash
# 安装
cd examples/advanced_agents/sandbox_agent
uv pip install -e .

# 构建 Sandbox 镜像
docker build -t nat-sandbox:latest .

# 运行（CLI 模式）
nat run configs/sandbox_agent.yaml

# 运行（Web UI 模式）
nat serve configs/sandbox_agent_ui.yaml

# 运行评估
nat eval configs/sandbox_agent_gaia.yaml
```

---

## 十四、后续工作

1. **实现核心代码**：按本设计文档实现各模块
2. **完善 Sandbox 镜像**：优化启动时间、预装更多工具
3. **GAIA 测试集准备**：筛选和准备测试用例
4. **UI 完善**：实现完整的前端功能
5. **文档编写**：README、使用指南
6. **单元测试**：各模块的测试用例

---

## 十五、工具层重构计划 (v2)

> 本节为后续迭代计划，目标是精简和优化工具集设计，减少功能重叠和 Agent 决策困惑。

### 15.1 工具数量变化

| 当前 | 目标 | 变化 |
|------|------|------|
| 12 个工具 | 7 个工具 | 减少 ~42% |

### 15.2 工具清单对比

```
当前 (12 tools)                    目标 (7 tools)
─────────────────                  ─────────────────
shell              ───────────────→ shell (保留，改进描述)
python             ───────────────→ python (保留，改进描述)
read_file          ───────────────→ file_read (保留)
write_file         ───────────────→ file_write (保留)
list_files         ─── 删除 ──────→ (用 shell ls 替代)
delete_file        ─── 删除 ──────→ (用 shell rm 替代)
web_search         ─── 重构 ──────→ web_search (移到主机侧)
browser_navigate ──┬── 合并 ──────→ web_browse (统一浏览工具)
browser_extract  ──┘
generate_document  ─── 删除 ──────→ (用 python 直接生成)
download_file      ─── 删除 ──────→ (用 shell curl 替代)
youtube_transcript ─── 重构 ──────→ youtube_transcript (移到主机侧)
```

### 15.3 架构变更：工具执行分层

**当前问题**：所有工具都在 Docker 沙箱中执行，包括 web_search 和 youtube_transcript，导致：
- API Key 暴露给沙箱环境
- 不必要的性能开销
- 沙箱网络问题影响 API 调用

**目标架构**：

```
┌─────────────────────────────────────────────────────────┐
│                     Agent (LLM)                         │
└─────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ 主机侧   │    │ 沙箱侧   │    │ 主机侧   │
    │ 工具     │    │ 工具     │    │ 工具     │
    └──────────┘    └──────────┘    └──────────┘
         │               │               │
    web_search      shell, python    youtube_transcript
                    file_read/write
                    web_browse
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌──────────┐    ┌──────────┐
    │ Tavily  │    │ Docker   │    │ YouTube  │
    │   API   │    │ Sandbox  │    │   API    │
    └─────────┘    └──────────┘    └──────────┘
```

**分层原则**：

| 执行位置 | 工具 | 原因 |
|----------|------|------|
| **主机侧** | web_search, youtube_transcript | 只读 API 调用，无需隔离，避免 API Key 暴露 |
| **沙箱侧** | shell, python, file_*, web_browse | 执行用户代码或访问用户 URL，需要隔离 |

### 15.4 工具详细设计

#### 沙箱工具 (5个)

| 工具 | 描述 |
|------|------|
| **shell** | 执行 bash 命令，用于系统操作：文件管理、包安装、下载、进程管理 |
| **python** | 执行 Python 代码，用于数据处理和计算：pandas、numpy、文件解析 |
| **file_read** | 读取文件内容，返回文本 |
| **file_write** | 写入文件内容，自动创建目录 |
| **web_browse** | 浏览网页，支持文本提取和截图（合并 browser_navigate + browser_extract） |

#### 主机侧工具 (2个)

| 工具 | 描述 | 实现方式 |
|------|------|----------|
| **web_search** | 网络搜索 | 直接调用 Tavily API |
| **youtube_transcript** | YouTube 字幕 | 直接调用 youtube-transcript-api |

**实现方式**：使用 LangChain StructuredTool（与沙箱工具相同），不使用 NAT 的 @register_function。

### 15.5 代码结构重构

**当前结构**：
```
tools/
├── __init__.py
├── executor.py      # 863 行，所有工具实现混在一起
└── factory.py       # 348 行，所有工具定义混在一起
```

**目标结构**：
```
tools/
├── __init__.py              # 公共导出
├── base.py                  # 基类、通用工具 (truncate_output 等)
├── sandbox/                 # 沙箱工具 (在 Docker 中执行)
│   ├── __init__.py
│   ├── executor.py          # SandboxToolExecutor 基类
│   ├── execution.py         # shell, python
│   ├── file_ops.py          # file_read, file_write
│   └── browser.py           # web_browse
├── host/                    # 主机侧工具 (直接在主机执行)
│   ├── __init__.py
│   ├── web_search.py        # web_search (Tavily API)
│   └── youtube.py           # youtube_transcript (YouTube API)
└── factory.py               # 组合所有工具
```

### 15.6 实施步骤

1. **Phase 1**: 创建目录结构
2. **Phase 2**: 创建主机侧工具 (web_search, youtube_transcript)
3. **Phase 3**: 重构沙箱工具 (按模块拆分)
4. **Phase 4**: 更新 factory.py (组合 sandbox + host)
5. **Phase 5**: 更新 register.py 和 prompts.py
6. **Phase 6**: 清理旧代码，运行测试

### 15.7 预期收益

| 指标 | 当前 | 预期 |
|------|------|------|
| 工具数量 | 12 | 7 |
| 工具描述 token | ~600 | ~350 |
| Agent 决策复杂度 | 高 | 低 |
| API Key 安全性 | 暴露给沙箱 | 仅主机可见 |
| web_search 延迟 | ~500ms | ~100ms |

---

## 十六、GAIA 评估结果

> 评估日期: 2026-01-24

### 16.1 评估概述

使用 GAIA (General AI Assistants) 基准测试集对 Sandbox Agent 进行评估。GAIA 是一个衡量 AI 助手在真实世界任务上能力的基准，包含需要多步推理、工具使用和多模态处理的复杂任务。

### 16.2 评估结果

#### GPT-5.2 模型

| Level | 任务数 | 准确率 | 描述 |
|-------|--------|--------|------|
| **Level 1** | 53 | **55.66%** | 基础任务 |
| **Level 2** | 86 | **51.16%** | 中等难度任务 |
| **Level 3** | 26 | **36.54%** | 困难任务 |

#### NIM LLaMA-3.3-70B 模型 (对比基准)

| Level | 任务数 | 准确率 |
|-------|--------|--------|
| **Level 1** | 53 | **23.11%** |

### 16.3 结果分析

1. **难度递进明显**: 随着任务复杂度从 Level 1 到 Level 3 增加，准确率呈下降趋势 (55.66% → 51.16% → 36.54%)，符合预期。

2. **模型差异显著**: GPT-5.2 在 Level 1 上的准确率 (55.66%) 比 NIM LLaMA-3.3-70B (23.11%) 高出 32.55 个百分点，表明基础模型能力对 Agent 性能有重要影响。

3. **Level 3 挑战**: Level 3 任务通常需要:
   - 多步复杂推理
   - 跨模态处理 (音频、图像、PDF、电子表格)
   - 长上下文理解
   - 精确的工具链编排

4. **已知限制**:
   - 音频转录任务在 Docker 沙箱中受限于 CPU 资源，Whisper 模型加载常超时
   - 部分任务需要访问付费 API 或受限网站

### 16.4 评估配置

```yaml
# 评估命令
GAIA_LEVEL=<1|2|3> LLM_TYPE=openai LLM_MODEL=gpt-5.2 \
  EVAL_OUTPUT_DIR=.tmp/nat/sandbox_agent/gaia_eval_level<N>_gpt52/ \
  nat eval --config_file src/nat_sandbox_agent/configs/config_gaia.yaml

# 沙箱配置
sandbox:
  type: docker
  image: nat-sandbox:latest
  memory_limit: 2g
  cpu_limit: 2.0
  network_enabled: true
  default_timeout: 120s
```

### 16.5 后续优化方向

1. **工具增强**: 添加更强大的音频/视频处理工具
2. **超时优化**: 对计算密集型任务提供更长超时或 GPU 加速
3. **Prompt 优化**: 改进系统提示以提升工具选择准确性
4. **错误恢复**: 增强 Agent 在工具失败时的重试和替代策略

---

## 十七、GitHub Feature Request 内容

> 以下内容用于在 NAT 仓库提交 Feature Request Issue

### 17.1 Title

```
[Feature] Add Sandbox Agent - General-Purpose Agent with Secure Code Execution
```

### 17.2 Feature Type

**New feature** (a new feature not in NeMo Agent Toolkit today)

### 17.3 Priority

**Medium**

### 17.4 Problem Description

I want NeMo Agent Toolkit to safely execute arbitrary code, browse websites, and manipulate files without risking the host system. Current advanced agent examples in NAT lack:

1. **Safe code execution** - No existing example demonstrates running user-provided Python/shell code in isolation
2. **GAIA benchmark capability** - No reference implementation for evaluating agent capabilities on GAIA (General AI Assistants) benchmark
3. **Multi-modal tool integration** - Existing examples don't combine code execution, web browsing, file I/O, and search in a unified agent

**Use Cases:**
- Research assistants that can write and run analysis scripts
- Automated data processing pipelines with web scraping
- AI tutors that can execute and demonstrate code
- Benchmark evaluation for agent development

**Why sandboxing matters:**
- Prevents malicious or buggy code from affecting the host
- Enables safe experimentation with untrusted inputs
- Required for production deployments with multiple users

### 17.5 Ideal Solution

A **Sandbox Agent** example in `examples/advanced_agents/sandbox_agent/` that demonstrates:

**Core Capabilities:**
- Execute shell commands and Python code in Docker containers or Daytona cloud sandboxes
- Browse websites with Playwright (headless Chromium)
- Read/write files within the isolated `/workspace`
- Search the web via Tavily API
- Extract YouTube video transcripts

**Architecture:**
- LangGraph-based ReAct agent loop
- 7 modular tools (shell, python, file_read, file_write, web_browse, web_search, youtube_transcript)
- Clean separation between sandbox-side and host-side tools
- Configurable iteration limits and output truncation

**GAIA Benchmark Integration:**
- Pre-configured for GAIA validation set evaluation
- Parameterized configuration for easy LLM swapping
- Answer cleaning utilities for accurate scoring

**Expected Benefits:**
1. Provides a secure foundation for building general-purpose AI agents
2. Serves as reference implementation for GAIA-style evaluations
3. Demonstrates NAT's extensibility with external sandbox providers
4. Enables safe multi-user deployments

**Success Criteria:**
- All 145+ unit tests pass
- GAIA Level 1 accuracy ≥ 20% with LLaMA-3.3-70B
- Docker and Daytona sandbox backends both functional
- Clear documentation for setup and customization

### 17.6 相关链接

- **Branch**: `feat/sandbox-agent`
- **Target Directory**: `examples/advanced_agents/sandbox_agent/`
- **Issue Proposal**: `ISSUE_PROPOSAL.md`
- **Related Work**: [OpenHands](https://github.com/All-Hands-AI/OpenHands), [GAIA Benchmark](https://huggingface.co/datasets/gaia-benchmark/GAIA)

---

## 十八、Pull Request 内容

> 以下内容用于在 NAT 仓库提交 Pull Request

### 18.1 PR Title

```
[Feature] Add Sandbox Agent - General-Purpose Agent with Secure Code Execution
```

### 18.2 PR Description

#### Summary

This PR adds **Sandbox Agent** to `examples/advanced_agents/`, a general-purpose AI agent that executes tasks within secure, isolated Docker containers or Daytona cloud sandboxes.

**Key highlights:**
- 7 modular tools for code execution, web browsing, file I/O, and search
- GAIA benchmark integration with documented evaluation results
- 145 unit tests (14 Docker integration tests)
- Production-ready architecture following NAT patterns

#### Motivation

##### Why NAT Needs This

Current NAT advanced agent examples lack:

| Gap | Impact |
|-----|--------|
| **No safe code execution** | Can't run user-provided Python/shell code without host risk |
| **No GAIA benchmark support** | No reference for evaluating general-purpose agent capabilities |
| **No sandbox isolation** | Limits production deployment scenarios |

Sandbox Agent fills these gaps and provides a foundation for building secure, capable AI agents.

##### Why Sandboxing Matters

- **Security**: Prevents malicious or buggy code from affecting the host
- **Multi-tenancy**: Enables safe multi-user deployments
- **Reproducibility**: Consistent execution environment across runs

#### Features

##### 1. Dual Sandbox Backend Support

| Backend | Use Case |
|---------|----------|
| **Docker** | Local development, CI/CD, air-gapped environments |
| **Daytona** | Cloud-scale deployments, on-demand resources |

##### 2. Comprehensive Tool Suite (7 tools)

| Tool | Location | Description |
|------|----------|-------------|
| `shell` | Sandbox | Execute bash commands |
| `python` | Sandbox | Execute Python code with data science libraries |
| `file_read` | Sandbox | Read file contents |
| `file_write` | Sandbox | Write files |
| `web_browse` | Sandbox | Browse URLs with Playwright (headless Chromium) |
| `web_search` | Host | Tavily AI search API |
| `youtube_transcript` | Host | Extract YouTube video transcripts |

**Architecture insight**: Host-side tools keep API keys secure and reduce latency. Sandbox-side tools provide isolation for untrusted operations.

##### 3. GAIA Benchmark Results (January 2026)

**NIM LLaMA-3.3-70B:**

| Level | Tasks | Accuracy |
|-------|-------|----------|
| Level 1 | 53 | 23.11% |
| Level 2 | 86 | 20.64% |
| Level 3 | 26 | 15.38% |

These results establish a baseline for future improvements and demonstrate the agent's capability on real-world tasks.

##### 4. Production-Ready Architecture

- **LangGraph ReAct loop** - Consistent with NAT's existing agent patterns
- **Configurable limits** - `max_iterations`, `max_observation_tokens`, resource constraints
- **Proper lifecycle management** - Automatic sandbox cleanup on completion/error
- **Modular design** - Easy to add new tools or swap sandbox backends

#### Code Quality

- **159 unit tests** (145 pass, 14 skip without Docker)
- **Comprehensive mocking** for external dependencies
- **Apache 2.0 license headers** on all files
- **Type hints** throughout the codebase

```bash
# Run tests
cd examples/advanced_agents/sandbox_agent
pytest tests/ -v -m "not integration"  # Skip Docker tests
pytest tests/ -v                        # All tests (requires Docker)
```

#### Project Structure

```
examples/advanced_agents/sandbox_agent/
├── README.md                     # Comprehensive documentation
├── Dockerfile                    # Sandbox image (pandas, playwright, etc.)
├── pyproject.toml               # Dependencies with NAT entry point
├── configs/
│   ├── config.yaml              # Basic configuration
│   ├── config_daytona.yaml      # Daytona cloud configuration
│   └── config_gaia.yaml         # GAIA evaluation configuration
├── src/nat_sandbox_agent/
│   ├── register.py              # NAT workflow registration
│   ├── sandbox/                 # Docker & Daytona implementations
│   ├── tools/                   # Modular tool system
│   ├── prompts/                 # System prompts
│   └── utils/                   # Answer cleaning utilities
└── tests/                       # Unit & integration tests
```

#### Usage

```bash
# Install
cd examples/advanced_agents/sandbox_agent
uv pip install -e .
docker build -t nat-sandbox:latest .

# Run (CLI)
nat run --config_file configs/config.yaml

# Run (Web UI)
nat serve --config_file configs/config.yaml

# Evaluate on GAIA
GAIA_LEVEL=1 GAIA_ATTACHMENTS_DIR=$(pwd)/data/attachments \
  nat eval --config_file configs/config_gaia.yaml
```

#### Alignment with NAT

| NAT Pattern | Sandbox Agent Implementation |
|-------------|------------------------------|
| `@register_function` | ✅ Workflow registered via decorator |
| `FunctionBaseConfig` | ✅ `SandboxAgentWorkflowConfig` extends it |
| LangGraph StateGraph | ✅ ReAct loop with agent/tools nodes |
| `builder.get_llm()` | ✅ LLM obtained through builder |
| Async generator yield | ✅ `yield _response_fn` pattern |
| YAML configuration | ✅ Multiple config files provided |
| Entry point registration | ✅ `[project.entry-points.'nat.components']` |

#### Checklist

- [x] Comprehensive README with setup and usage instructions
- [x] Unit tests with good coverage (145 passing)
- [x] Docker integration tests (14 tests)
- [x] GAIA benchmark evaluation support
- [x] Multiple LLM support (NIM, OpenAI)
- [x] Configurable sandbox resources
- [x] Clean code structure following NAT patterns
- [x] Apache 2.0 license headers

#### Related Work

- Inspired by [OpenHands](https://github.com/All-Hands-AI/OpenHands) but fully integrated with NAT
- GAIA benchmark: https://huggingface.co/datasets/gaia-benchmark/GAIA
