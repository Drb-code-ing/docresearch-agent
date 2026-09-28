# DocResearch Agent

一个 Python 资料调研与文件工作流项目：主 Agent 可直接处理简单任务，复杂任务按依赖派发独立上下文的子 Agent；主子均可在私有工作目录读写编辑文件，最终生成带来源的 Markdown 报告。

正式检索采用 **Elasticsearch IK/BM25 + Milvus HNSW/COSINE + RRF**，外层包含查询改写、相关性排序、证据判断和最多一次补检索。专用 DashScope reranker 可显式配置。离线 demo 不联网、不需要密钥。当前真实简单任务已通过；新复杂链路曾耗尽预算，修正后复测被模型 HTTP 402 阻断，不能声称已完成真实复杂验收。详见 [验收证据](docs/VALIDATION.md)。

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
| `tasks.json` | 任务依赖、状态、精简研究结果和文件元数据 |

demo 返回 partial 是预期的教学缺口，不是崩溃。固定 17 次模拟请求、14 次工具调用，覆盖计划、子任务、检索、文件创建/读回/编辑与报告。completed/partial 退出码 0，其余运行状态为 1。工作笔记位于 reports/workspaces/<run_id>/<agent_id>/，不混入原始资料。

## 真实模型模式

PowerShell 示例，变量仅作用于当前终端；不要把密钥写入 Git：

```powershell
$env:DOCRESEARCH_BASE_URL = "https://your-provider.example/v1"
$env:DOCRESEARCH_API_KEY = "你的密钥"
$env:DOCRESEARCH_MODEL = "支持 Tool Calling 的模型名称"
```

`.env.example` 只说明变量，程序**不会自动读取 `.env`**。兼容服务须支持 `/chat/completions` 的 tools/tool_calls 协议；不同提供方仍需实测。暂不支持流式输出、自动重试和 reasoning 专用参数。

正式后端需要 Embedding，设置 `DOCRESEARCH_EMBEDDING_MODEL`，默认复用聊天的 base URL 和 API key。若是不同服务，再成对设置：

```powershell
$env:DOCRESEARCH_EMBEDDING_MODEL = "你的向量模型名称"
$env:DOCRESEARCH_EMBEDDING_BASE_URL = "https://your-embedding-provider.example/v1"
$env:DOCRESEARCH_EMBEDDING_API_KEY = "该向量服务的密钥"
```

单独设置 URL 或 key 会被拒绝，避免把聊天密钥误发给另一个服务。服务和资料准备好后：

```powershell
uv run docresearch ingest --corpus ./my-docs
uv run docresearch run "比较两份资料的部署约束，指出缺失证据" --corpus ./my-docs --output ./reports
```

默认连接本机 ES 9200、Milvus 19530，使用已有 IK 插件。部署、认证、分词配置及更新策略见 [ES + Milvus 使用说明](docs/RETRIEVAL_SETUP.md)。重复 ingest 会核验并复用已有快照，不重复生成文档向量；新增、修改、删除资料或更换向量模型后，需要重新 ingest。run 不自动重建，不静默降级。

要运行旧的内存对照模式，显式使用 `run --backend memory`；不设 Embedding 时为 rank-bm25，设置后为内存余弦 + RRF。离线 demo 和教学脚本也使用这套后端。

HTTPX 默认读取环境配置，在 Windows 上也可能采用系统代理，即使没有 `HTTPS_PROXY`。如果代理不可达而提供方允许直连，可在当前终端设置 `$env:DOCRESEARCH_TRUST_ENV = "false"`。这会禁用环境/系统代理与环境证书配置，**仍开启 TLS 证书校验**；需要企业代理或自定义 CA 时应保留默认 `true`。程序不会自动切换端点、降低 TLS 安全性或静默退回 BM25。

**隐私边界：live 模式会将问题、检索片段和子代理结果发送给配置的模型提供方。首次 ingest 新快照会把全部文本块发给向量服务；复用快照后，run 只为查询生成向量。内存对照模式则在每次 run 准备时生成文档向量。这里的“本地”指资料来源与报告落盘，不代表推理不出设备。** 先用自编样例验证，勿直接投入隐私或无权处理的资料。

```bash
uv run docresearch run "你的问题" --max-calls 48 --timeout 180
```

调用预算包含聊天、查询改写、证据判断、Embedding 和专用 rerank，不是金额预算。Token 统计只累加聊天 usage。专用重排可成组设置 DOCRESEARCH_RERANK_URL、DOCRESEARCH_RERANK_API_KEY、DOCRESEARCH_RERANK_MODEL，协议为 DashScope；不设则由 LLM 显式排序/评估，设了但失败不会静默跳过。

## 项目范围

- CLI，本地资料目录与独立报告目录。
- ES 执行 BM25 与 IK 分词，Milvus 持久化向量并使用 HNSW/COSINE，按统一 Source ID 做 RRF。
- 版本化入库、幂等复用、双写完成后发布 ready manifest；读取核对来源，不使用半成品索引。
- 自适应主代理：简单任务直接做，复杂任务 plan/task；显式依赖、失败传播、限长子结果，不自动回灌原文。
- 主子都有受控文件工具，各自目录、hash 版本检查、单文件原子替换；源资料只读，最终报告统一发布。
- 改写、多查询检索、融合、重排、证据判断和一次补检索；判断结果不代表事实证明。
- 总调用次数、子代理步数、并发数、单次调用及任务超时。
- 离线演示与自动化测试。离线模式是确定性脚本，不代表真实模型效果。

不包含前端、HTTP 服务、OCR、联网搜索、通用 Shell、操作系统沙箱或生产多租户能力。

## 工程检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

GitHub Actions 覆盖 Windows/Linux × Python 3.11/3.12。测试使用临时目录、确定性模型及 HTTP MockTransport，不会消耗真实 API 额度。最新测试与真实调用记录见 [验收证据](docs/VALIDATION.md)。

## 深入阅读

先跑这个离线学习脚本：它逐步打印真实 Source、分词、检索结果、参数校验、子代理执行顺序，玩具向量另作明确标记。

```bash
uv run python -X utf8 examples/walkthrough.py
uv run python -X utf8 -m docresearch.evaluation
# 配置好向量服务后才运行下一条，会发送样例并消耗向量 API 额度：
uv run python -X utf8 -m docresearch.evaluation --hybrid
# 已入库时，测试正式 ES + Milvus 后端：
uv run python -X utf8 -m docresearch.evaluation --backend es-milvus
```

- [详细项目理解文档](docs/PROJECT_UNDERSTANDING.md)：用同一个问题，从 Python 启动、资料变片段，到检索、工具循环、子代理与报告逐步讲解。
- [项目面试文档](docs/INTERVIEW_GUIDE.md)：每个模块的实现、选择理由、口述答案、追问和代码证据。
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
