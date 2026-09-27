# 验收证据

## 自动化验证

- 日期：2026-09-28，Asia/Shanghai。
- 本地：Windows，uv 管理的 CPython 3.12.13，59 passed。
- Ruff 检查与格式化检查通过。
- GitHub Actions：Windows/Linux × Python 3.11/3.12 四个组合均通过。
- [首次 CI 记录](https://github.com/Drb-code-ing/docresearch-agent/actions/runs/36333536157)。后续文档提交也运行相同 CI，可在 Actions 查看。

测试证明结构、检索计算、权限和运行机制符合用例，不是模型准确率评测。符号链接测试在不支持创建链接的环境会明确 skip，应以实际任务日志为准。

## 受控真实模型运行

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

## 真实混合检索端到端验收

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

### 20 题检索小测

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
