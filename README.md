# DocResearch Agent

一个小而完整的 Python 本地资料调研项目：读取 Markdown/TXT，检索证据，派发独立上下文的研究子代理，生成带来源的 Markdown 报告。

项目已实现 CLI 闭环，默认演示不联网、不需要密钥。真实模型与 Embedding 走显式配置的 OpenAI-compatible 接口；已完成自动化测试和一次自编资料上的真实模型端到端验收。Embedding 的独立真实冒烟遇到超时，尚未完成。**单次验收不是大样本质量评测，不宣称性能提升或生产使用。**

## 快速运行

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。从仓库根目录运行：

```bash
uv sync --extra dev
uv run docresearch demo
uv run pytest -q
```

不使用 uv 时：

```bash
python -m venv .venv
# 激活虚拟环境后
python -m pip install -e ".[dev]"
docresearch demo
```

命令打印报告目录 `reports/<run_id>/`。离线样例固定比较 pgvector 与 Milvus，派发两个研究子代理；它是确定性协议演示，不接受任意自然语言问题，也不是本地 LLM。三份样例为自编教学资料，不是实际产品基准。

| 文件 | 内容 |
| --- | --- |
| `report.md` | 发现、资料缺口、来源路径/行号/版本 |
| `sources.json` | 被引用的原文快照，含相对路径和片段 ID |
| `trace.json` | 模型/工具调用与子任务阶段、耗时、错误分类 |
| `run.json` | 状态、调用计数、并发峰值和配置上限 |

演示返回 `partial` 是预期结果：它明确留下性能对比和真实推理缺口。`completed/partial` 的 CLI 退出码为 0，`failed/budget_exhausted/timeout` 为 1；严格验收时必须进一步检查 `run.json`。

## 真实模型模式

PowerShell 示例，变量仅作用于当前终端；不要把密钥写入 Git：

```powershell
$env:DOCRESEARCH_BASE_URL = "https://your-provider.example/v1"
$env:DOCRESEARCH_API_KEY = "你的密钥"
$env:DOCRESEARCH_MODEL = "支持 Tool Calling 的模型名称"
uv run docresearch run "比较两份资料的部署约束，指出缺失证据" --corpus ./my-docs --output ./reports
```

`.env.example` 只说明变量，程序**不会自动读取 `.env`**。兼容服务须支持 `/chat/completions` 的 tools/tool_calls 协议；不同提供方仍需实测。暂不支持流式输出、自动重试和 reasoning 专用参数。

默认只使用本地 BM25。要启用混合检索，再设置 `DOCRESEARCH_EMBEDDING_MODEL`，该模型使用同一 base URL 与 API key 的 `/embeddings` 接口。每次启动重新建内存索引，不持久缓存向量。

**隐私边界：live 模式会将问题、检索片段和子代理结果发送给配置的模型提供方；开启 Embedding 后会发送整个资料快照的文本块。这里的“本地”指资料来源与报告落盘，不代表推理不出设备。** 先用自编样例验证，勿直接投入隐私或无权处理的资料。

```bash
uv run docresearch run "你的问题" --max-calls 24 --timeout 180
```

调用预算包含聊天与 Embedding 请求，不是费用预算。Token 统计仅累加提供方返回的聊天 usage，缺失时为 0，不可把 0 当成免费。

## 首版范围

- CLI，本地资料目录与独立报告目录。
- BM25 关键词检索；配置真实 Embedding 服务后可启用向量 + BM25 的 RRF 混合检索。
- Tool Calling 主循环，子代理只读，主代理统一写报告。
- 总调用次数、子代理步数、并发数、单次调用及任务超时。
- 离线演示与自动化测试。离线模式是确定性脚本，不代表真实模型效果。

不包含前端、HTTP 服务、OCR、联网搜索、通用 Shell、操作系统沙箱或生产多租户能力。

## 工程检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Windows / Python 3.12 本地验证为 51 passed；GitHub Actions 配置 Windows/Linux × Python 3.11/3.12。测试使用临时目录、确定性模型及 HTTP MockTransport，不会消耗真实 API 额度。

## 深入阅读

- [详细项目理解文档](docs/PROJECT_UNDERSTANDING.md)：从最小心智模型、代码入口到预算/取消、检索、引用及已知限制。
- [项目面试文档](docs/INTERVIEW_GUIDE.md)：30 秒/2 分钟介绍，常见追问、回答证据及不能夸大的表述。
- [交付记录](docs/DELIVERY.md)：分步实现与验证过程。
- [验收证据](docs/VALIDATION.md)：真实调用、模拟测试与未完成项分开记录。
- [简历项目描述](docs/RESUME.md)：不含个人联系方式的可审计项目描述。

## 交付步骤

1. 项目骨架与范围。
2. 受控文件工具与本地检索。
3. Agent 循环、子代理、报告与 CLI。
4. 行为测试、样例验收与 GitHub Actions。
5. 项目理解文档、项目面试文档与简历描述核对。

## 来源

整理自个人学习仓库 `WROKSPACE` 中的 `ai/agent/agentic_rag` 和 `ai/harness/sub-agents`。迁移其查询分解、检索和工具循环思路，重新实现为统一 Python 包；没有直接运行原脚本的任意 Shell 工具。
