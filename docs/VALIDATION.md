# 验收证据

## 自动化验证

- 日期：2026-09-28，Asia/Shanghai。
- 本地：Windows，uv 管理的 CPython 3.12.13，99 passed、1 skipped；真实服务集成测试默认 skip，显式开启后另行 1 passed。
- Ruff 检查与格式化检查通过。
- 本轮数据库复测首次失败于 gRPC 使用不可达的本地代理 127.0.0.1:7897；仅在测试进程配置 localhost/127.0.0.1 的 NO_PROXY、no_proxy、no_grpc_proxy 后，原 Docker 服务上的同一测试通过。没有修改全局代理或重建数据库。
- GitHub Actions 配置：Windows/Linux × Python 3.11/3.12 四个组合；真实数据库集成测试在本地显式开启，不依赖 CI 启动数据库。
- [ES/Milvus 代码提交 13fb332 的 CI 记录](https://github.com/Drb-code-ing/docresearch-agent/actions/runs/36372634202) 四个组合均通过；最新提交结果以 [Actions](https://github.com/Drb-code-ing/docresearch-agent/actions) 对应 SHA 的运行记录为准。

测试证明结构、检索计算、权限和运行机制符合用例，不是模型准确率评测。符号链接测试在不支持创建链接的环境会明确 skip，应以实际任务日志为准。

## 按需委派与 Agentic RAG 验收

这里对应主保留基础工具、子独立上下文和工作区的新架构。下方旧版记录不能替代本节验收。

### 已完成的确定性验证

- 简单任务由主完成 search、write_file、read_file、edit_file、save_report，`tasks=0`。
- 两个研究子任务完成后，核验任务才能接收精简依赖结果；未知依赖、环、重复 ID、未完成依赖会被拒绝。
- 子结果不带 Source.text、文件正文和工具历史，也不更新主的 seen。主不能用没亲自读取的来源改写子结论；选用已登记 finding_id 时保留原句与引用。
- 主子都可写私有工作区；跨目录、陈旧版本覆盖、非唯一匹配编辑与超限文件被拒绝。
- 检索测试覆盖查询改写、候选融合、专用 reranker 协议、证据评估和最多一次补检索；排队取消及失败依赖也有用例。
- 离线 CLI demo：17 次模拟请求、14 次工具调用、2 个子任务。模拟轨迹只证明流程，不证明模型自主决策质量。

### 真实简单任务：完成研究，保留资料缺口

- 仅发送 `examples/corpus` 三份自编资料；请求模型标识为 deepseek-v4-flash，使用已有 Embedding 与 qwen3-rerank 配置，不公开凭据。
- `partial`、`error=null`、`es-milvus-rrf`；14 次计费相关请求计数（含聊天、向量、专用重排），10 次工具调用，0 个子任务。
- trace 可复算 10 组 tool_start/tool_end，包括检索、两次 read_source、两次写文件、两次读文件、一次编辑及 save_report。检索经过 rewrite、rerank、grade；本次 sufficient=true，没有触发补检索。
- 5 条发现、3 个缺口、2 份被引用来源。16109 ms；提供方 chat usage 为 34615 prompt / 2731 completion tokens，只是单次记录，不代表均值或完整费用对账。
- [报告](evidence/adaptive-simple/report.md)、[统计](evidence/adaptive-simple/run.json)、[轨迹](evidence/adaptive-simple/trace.json)、[任务表](evidence/adaptive-simple/tasks.json)、[来源](evidence/adaptive-simple/sources.json)。工具轨迹记录文件操作成功，工作区正文没有额外发布。
- 人工抽查：部署和维护结论能对应样例；第一条将“业务字段过滤与 SQL 查询组合”进一步解释为“同一条关系查询中”，比原文略具体。保留原始报告，不把引用 ID 有效当成每句话已被严格证明。

### 真实复杂任务：一例端到端完成，保留证据缺口

- 用户充值并授权复测后，仅用相同的三份自编资料运行；本次没有再出现 HTTP 402。请求模型标识为 deepseek-v4-flash，检索为 `es-milvus-rrf`，重排为 `dashscope+llm`。这证明接口此次可用，不能反向确认此前 402 的具体账户原因。
- `run_id=a28e423a634541128b16858b94984676`，`partial`、`error=null`；3 个子任务全部 `completed`，无子任务失败，并发峰值 2。主先规划两个研究任务，再派发依赖二者的核验任务，最后提交报告。
- 两个研究者分别在私有工作区写入、读回并按版本编辑 `notes.md`；trace 中对应工具执行成功。核验任务在前两者结束后启动。报告采用登记的子任务发现，保留费用、性能、部署细节等缺口，因此 `partial` 不代表这次执行失败。
- 62 次外部请求计数（包含聊天、改写、评估、查询向量与专用重排），34 次工具调用，94656 ms；提供方 chat usage 为 134598 prompt / 26248 completion tokens。该计数不是金额，也不包括先前文档入库费用。
- 本次显式设置 `--max-calls 80 --timeout 360`，默认请求上限仍为 48。62 次超过默认预算；本次没有再付费运行 48 次预算的同题对照，不能宣称默认配置足够，更不能据此宣称任意复杂任务稳定完成。
- [报告](evidence/adaptive-complex-success/report.md)、[统计](evidence/adaptive-complex-success/run.json)、[轨迹](evidence/adaptive-complex-success/trace.json)、[任务表](evidence/adaptive-complex-success/tasks.json)、[来源](evidence/adaptive-complex-success/sources.json)、[输入与阅读说明](evidence/adaptive-complex-success/README.md)。保留原始产物，不上传密钥、完整聊天或私有笔记正文。
- 人工抽查发现一个值得学习的问题：`milvus_study:f6` 把笔记版本号当作研究结论，并引用不能证明版本号的技术资料。核验子任务指出不匹配，主没有选入这条发现，但最终报告仍保留相关缺口。来源 ID 校验只能证明来源已读，不能单独证明结论正确；这次模型核验有效不等于以后都能发现此类问题。
- 核验子任务还出现连续多轮未结束和一次终止结果拒绝，之后才修正提交。最终成功没有消除这段请求开销，报告也有重复结论；尚未验证跨题材质量、默认预算充分性和多次运行稳定性。

### 历史失败：预算耗尽与 HTTP 402

- 首次尝试记录 80 次请求、51 次工具调用、4 个任务、并发峰值 2；其中 2 个任务完成、2 个任务 StepLimit，总体 `budget_exhausted`，没有 report.md。
- [运行统计](evidence/adaptive-complex-failed/run.json)、[轨迹](evidence/adaptive-complex-failed/trace.json)、[任务状态](evidence/adaptive-complex-failed/tasks.json)。错误包括路径使用与末轮结果校验失败，引发反复尝试和预算消耗。
- 随后补充路径指引、参数字段反馈、末两轮收束提醒，并把子轮数默认值改为 10；这些修复通过离线回归。默认总请求预算仍是 48，失败试验中的 80 是显式覆盖，不能靠提高上限宣称解决问题。
- 修复后复测首请求返回 HTTP 402，0 工具、0 子任务，已停止继续调用。[统计](evidence/adaptive-retest-402/run.json)、[含 HTTP 状态的轨迹](evidence/adaptive-retest-402/trace.json)。这表明提供方拒绝请求；没有足够信息判定具体余额或账户原因。
- 上述两次记录保留为历史故障；充值后的新记录补足一例复杂真实运行证据，没有覆盖或改写失败记录。用更多、更长的独立资料评估质量仍未完成。

上述文件是本机运行产物，不是提供方签名证明。它们记录请求模式和程序事件，不额外证明服务端实际模型身份。

## 历史：基础 ES/Milvus 后端验收

- 复用现有 Docker：ES 8.17.0 + analysis-ik；Milvus standalone v3.0.0，etcd/MinIO 为已有依赖。未重建服务、未删除原有学习数据。
- 官方客户端：elasticsearch 8.19.3、pymilvus 2.6.17。BM25 在 ES/Lucene 执行；Milvus 使用 HNSW/COSINE，M=16、efConstruction=128、查询 ef=64。
- 三份自编资料初次真实入库：3 个 Source、1024 维、1 次文档 Embedding；关闭 CLI 后再执行 ingest，`reused=true`、`embedding_requests=0`。
- 真实 run：`retrieval=es-milvus-rrf`，18 次请求（13 次聊天 + 5 次查询向量），23 次工具调用，2 个 child，并发峰值 2，child_failures 为空。
- 状态 partial、error=null，8 个发现和 8 个缺口；耗时 41531 ms，chat usage 63379 prompt / 11488 completion tokens。不包含之前入库的向量计费，也不代表平均性能。
- [报告](evidence/controlled-live-es-milvus/report.md)、[轨迹](evidence/controlled-live-es-milvus/trace.json)、[统计](evidence/controlled-live-es-milvus/run.json)、[来源](evidence/controlled-live-es-milvus/sources.json)。没有把凭据或私人材料放入公开产物。
- 人工抽查：部署与维护结论可对应原文，没有性能/费用数值；第 6 条把两方都概括为“提及向量索引”比 pgvector 原文更具体，保留原始输出作为来源校验不等于语义支持的实际例子，不把该报告视为完全正确。
- 离线测试 73 项通过；真实 ES/Milvus 集成测试使用独立随机空间与合成二维向量，1 项通过，覆盖关闭客户端后的复用、资料删除后换快照、存储内容损坏时拒绝读取。只清理测试自己创建且核验归属的空间。

同一 20 题集在基础 ES/Milvus+RRF 后端上的结果：16 个有答案题 document recall@2=0.96875、top-1=0.9375；4 个无答案题空结果率=0。查询 Embedding 20 次、测量区间 2688 ms，复用已有文档向量。逐题结果见 [ES/Milvus](evidence/retrieval-es-milvus.json)。旧内存混合的 recall@2=1.000、top-1=0.875，因此不能宣称换数据库就全面提高检索质量。这组评测没有经过新 AgenticSearch 的改写、重排、评估与补检索，不是完整 Agentic RAG 质量评测。

旧 trace 未覆盖终止工具及部分被拒绝动作，旧版 23 次工具计数不能仅由它复算。新版已补齐 tool_start/tool_end，保留旧证据原样以免混淆版本。

以下保留迁移前内存后端的真实证据，供历史与对照，不代表正式默认存储结构。

## 内存 BM25 对照运行

- 输入：仓库 `examples/corpus` 中三份自编教学资料，无个人私有资料。
- 请求模型标识：`deepseek-v4-flash`，通过已有配置的兼容接口调用；不公开 base URL 或凭据。
- 用户任务：比较 pgvector 与 Milvus 在小型知识库中的部署/维护约束，明确要求两个独立研究子任务，缺少基准时列出缺口。
- 检索模式：本地 BM25，没有启用真实向量检索。
- 预算：最多 12 次模型请求，子任务最多 2 个，单请求 90 秒，总运行 240 秒。
- 实际：10 次聊天请求，15 次计数工具调用，2 个子任务，并发峰值 2，子任务失败数 0。
- 运行区间耗时：17735 ms，仅本次样例，不代表平均性能。
- 提供方返回 chat usage 累计：prompt_tokens=22283，completion_tokens=5014。没有估算费用；这不是模型实际计费的完整对账数据。
- 最终状态：partial。报告生成成功，含 7 个发现、8 个资料缺口和 3 份来源；partial 来自资料不足，而非运行失败。

公开保存的证据只包含自编样例相关产物：

- [生成报告](evidence/controlled-live-bm25/report.md)
- [运行统计](evidence/controlled-live-bm25/run.json)
- [执行轨迹](evidence/controlled-live-bm25/trace.json)
- [被引用的来源快照](evidence/controlled-live-bm25/sources.json)

人工核对：关键部署/维护表述可对应样例原文；报告明确没有延迟、吞吐和费用数字。报告缺口提及的索引参数与基础设施名仅作为“样例未覆盖的主题”，不能据此认定样例或项目实现了这些能力。这次检查不是双人标注、盲测或统计准确率评测。

没有将完整模型聊天、密钥、个人简历、用户真实资料提交到公开仓库。

## 内存混合检索对照运行

先前 Embedding 冒烟曾超时。排查中保持端点、模型和输入不变，默认路由与显式系统代理均 ConnectTimeout；使用 `trust_env=False` 直连后，同一服务返回 HTTP 200 和 1024 维向量。HTTPX 在这台 Windows 机器上通过系统代理解析获取代理，不以是否存在 `HTTPS_PROXY` 环境变量为唯一依据。没有关闭 TLS 校验，没有更换服务或密钥。

补充独立 Embedding URL/key 配置与显式 `DOCRESEARCH_TRUST_ENV` 开关，回归测试先失败后通过。通过实际 CLI 入口 `python -m docresearch.cli run ...`（与 `docresearch run` 共用 `main`）完成了研究，不使用定制检索器绕过 CLI：

- 数据：仍仅为 `examples/corpus` 三份自编资料。
- 请求模型标识：chat `deepseek-v4-flash`，embedding `text-embedding-v4`，1024 维；服务端模型身份不作额外推断。
- 模式：`hybrid-rrf`，13 次请求，其中 10 次聊天、3 次 Embedding（1 次建索引、2 次查询）。
- 17 次计数工具调用，2 个子任务，并发峰值 2，子任务失败 0。
- 19609 ms；chat usage 为 23620 prompt tokens / 6097 completion tokens；不包含向量计费。
- 状态 `partial`、error 为 null，8 个发现、8 个缺口、3 份来源。缺口是资料缺少规模/性能/成本数据，不是链路失败。
- [报告](evidence/controlled-live-hybrid/report.md)、[统计](evidence/controlled-live-hybrid/run.json)、[轨迹](evidence/controlled-live-hybrid/trace.json)、[来源快照](evidence/controlled-live-hybrid/sources.json)。

逐项检查报告：部署、维护和检索能力表述能对应自编原文；没有编造延迟、吞吐量或费用数字。本记录证明这组配置下完整链路可用，不证明混合检索优于 BM25，也不证明真实业务准确率。

## 正确解读证据

### 历史内存后端的 20 题检索小测

标注文件为 `examples/retrieval_cases.json`，先写标注再运行。16 个有答案的问题含 2 个跨文档问题和 2 个英文改写；4 个无答案问题包含资料没给的性能/费用数字及无关安装问题。只有 3 篇短文、3 个 chunk，是自编教学回归集，不是独立标准评测集，也不是面试中的泛化准确率证明。

执行 `uv run python -X utf8 -m docresearch.evaluation` 测 BM25；加 `--hybrid` 使用同一组标签测试真实向量 + BM25 + RRF，不调用聊天模型。程序不把答案标签送入检索器。

| 指标 | BM25 | Hybrid |
| --- | --- | --- |
| 16 题平均 document recall@2 | 0.875 | 1.000 |
| 16 题 top-1 文档命中率 | 0.875 | 0.875 |
| 4 题无答案时空结果率 | 0.000 | 0.000 |
| Embedding 请求数 | 0 | 21 |
| 本次测量区间耗时 | 小于毫秒取整精度 | 2937 ms |

Recall 的算法是：前 2 个 chunk 对应的去重文档，覆盖了该题多少个应有文档，再对 16 题取平均。无答案问题不进入 recall 分母，单独看是否返回空结果。这里“无答案”指原文不能提供所问事实，并不等同于完全没有相关文本。

结果说明：在这组小样例上，混合检索补到了 BM25 漏掉的文档，但没有提高 top-1；两者对 4 个无答案问题都返回了候选，**检索命中不等于问题可回答**，仍须阅读证据并记录 gaps。不能把这组数据推广为“整体准确率 100%”或生产提升比例。中文单字重叠和宽松的余弦正值过滤都可能带来弱相关候选。

逐题结果：[BM25](evidence/retrieval-bm25.json)、[Hybrid](evidence/retrieval-hybrid.json)。保留的是 UTF-8 输出的完整运行；此前一次同配置运行也成功，但终端重定向编码不正确，因此重新导出了结果。每次 Hybrid 评测各 21 次向量请求，仅发送自编资料和查询。

### 各类证据的含义

| 证据 | 证明什么 | 不证明什么 |
| --- | --- | --- |
| pytest | 被测输入条件下的代码行为 | 真实模型决策准确率 |
| HTTP MockTransport | 请求/响应解析和错误分类 | 外部服务可用性 |
| DemoModel | 确定性工具循环与产物 | 自主研究能力 |
| 真实 BM25 样例运行 | 选定接口能完成派发、检索、回读与报告 | 所有模型兼容、实际用户效果 |
| 真实混合检索样例运行 | 独立 chat/embedding 配置下能建索引、查询、融合并生成报告 | 相对 BM25 的质量提升、大规模检索能力 |
| 来源校验 | 引用来自任务内已见快照 | 结论一定被原文支持 |
| 单次耗时/usage | 这一次调用的记录 | 平均性能、节省比例、生产成本 |
