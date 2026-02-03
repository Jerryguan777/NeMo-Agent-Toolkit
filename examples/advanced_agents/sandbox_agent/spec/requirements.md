Sandbox Agent spec

功能定位
在NeMo-Agent-Toolkit的examples/advanced_agents/下添加一个sandbox_agent

核心能力：
1. 文件操作（在沙盒中）：读取、写入、转换、压缩等
2. 文档生成（在沙盒中）：PPT、Word、PDF、Markdown 等
3. 网络搜索与调研：集成搜索工具、结果汇总
4. 代码执行（在沙盒中）：Python 脚本运行、数据处理
5. 浏览器操作（在沙盒中）：页面访问、截图、交互
6. 命令执行（在沙盒中）：Shell 命令、系统操作

前端：
   1. 具体UI参考Manus
   2. 使用NAT （NeMo-Agent-Toolkit)提供的UI来实现

Evaluation：
    1. 使用GAIA测试集上的selected tasks
    2. 将来使用scale ai的RLI测试集
   
在项目中的意义
1. 展示沙盒安全能力
* 演示如何在隔离环境中执行代码、命令和文件操作
* 展示资源限制、隔离执行和错误处理
1. 展示工具集成能力
* 集成多种工具类型（文件、网络、代码、浏览器）
* 展示复杂工具组合的使用方式
1. 展示通用 Agent 构建模式
* 作为通用助手参考实现
* 展示如何组织多工具 Agent
1. 展示生产级应用能力
* 安全、错误处理、资源管理
* 适用于企业环境
1. 展示扩展性
* 易于添加新工具
* 展示 NAT 的可扩展架构


NVIDIA NeMo Agent Toolkit 项目总结
项目概述
NVIDIA NeMo Agent Toolkit 是一个用于构建和管理 AI 代理工作流的开源工具包。它提供统一接口，连接企业级代理与数据源和工具，支持多种框架，无需重构现有系统。
> "一个灵活、轻量级、统一的库，让你能够轻松地将现有企业代理连接到任何框架的数据源和工具。"
核心特性
1. 框架无关（Framework Agnostic）
* 支持多种代理框架：
* LangChain / LangGraph
* LlamaIndex
* CrewAI
* Microsoft Semantic Kernel
* Google ADK (Agent Development Kit)
* Microsoft AutoGen
* Strands Agents
* 自定义企业框架
* 可与现有技术栈协同，无需迁移
2. 可重用性（Reusability）
* 代理、工具和工作流以函数形式存在
* 支持组合和复用
* 一次构建，多处使用
3. 快速开发（Rapid Development）
* 提供预构建的代理、工具和工作流
* 支持快速定制和扩展
* 降低开发门槛
4. 性能分析（Profiling）
* 工作流、工具和代理级别的性能分析
* 跟踪输入/输出 tokens 和耗时
* 识别性能瓶颈
5. 可观测性（Observability）
* 集成 Phoenix、Weave、Langfuse
* 兼容 OpenTelemetry
* 支持性能监控、执行追踪和行为分析
6. 评估系统（Evaluation）
* 内置评估工具
* 验证和维护工作流准确性
* 支持多种评估指标
7. 用户界面（UI）
* 提供 Web UI 聊天界面
* 可视化输出和调试
* 交互式工作流测试
8. MCP 支持
* 支持 Model Context Protocol (MCP)
* 可作为 MCP 客户端或服务器
* 支持工具发布和调用
支持的代理类型
* ReAct Agent：推理与行动循环
* Tool-Calling Agent：工具调用
* ReWOO Agent：推理与观察
* Reasoning Agent：推理
* Router Agent：路由分发
* Sequential Executor：顺序执行
* Responses API Agent：API 响应
主要功能模块
src/nat/
├── agent/          # 代理实现
├── tool/           # 工具系统
├── llm/            # LLM 集成（NIM, OpenAI, LiteLLM, AWS Bedrock 等）
├── embedder/       # 嵌入模型
├── retriever/      # 检索系统（RAG）
├── memory/         # 内存管理（Redis, Mem0 等）
├── eval/           # 评估系统
├── profiler/       # 性能分析
├── observability/  # 可观测性
├── finetuning/     # 微调支持（DPO, RL 等）
├── front_ends/     # 前端系统（FastAPI, Web UI）
├── authentication/ # 认证系统
├── control_flow/   # 控制流（路由、顺序执行）
└── cli/            # 命令行工具

插件生态系统
项目采用模块化插件架构，包含 20+ 个可选插件包：
* nvidia-nat-langchain - LangChain 集成
* nvidia-nat-llama-index - LlamaIndex 集成
* nvidia-nat-crewai - CrewAI 集成
* nvidia-nat-mcp - MCP 协议支持
* nvidia-nat-redis - Redis 内存
* nvidia-nat-phoenix - Phoenix 可观测性
* nvidia-nat-weave - Weave 可观测性
* nvidia-nat-a2a - A2A 协议支持



