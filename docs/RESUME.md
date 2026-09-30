# 简历描述与证据映射

## 可用项目描述

**DocResearch - 多 Agent 资料调研与报告生成助手**

Python · asyncio · Pydantic · Tool Calling · Elasticsearch · Milvus · Agentic RAG · RRF · Rerank

评估方案：LangSmith / OpenEvals（固定测试集与 LLM-as-judge）

面向本地技术资料调研与方案对比，构建融合 Agent Loop 与 Agentic RAG 的多 Agent 助手，支持按需任务分解、证据检索与笔记管理，输出带原文出处的结构化调研报告。

- **Agent 编排：** 基于 Python / asyncio 实现工具调用循环与按需任务委派，主 Agent 保留直接检索和文件操作能力；通过独立对话上下文与结构化结果回传，隔离子任务中间过程，控制主对话上下文规模。
- **混合检索：** 接入 Elasticsearch BM25 与 Milvus HNSW 双路召回，采用 RRF 融合与 Rerank 重排；维护版本化持久索引，兼顾精确术语匹配、语义检索与跨任务复用。
- **检索决策：** 构建查询改写、证据评估与受限补检索流程，根据缺失信息调整查询；通过补查上限、共享请求预算与超时限制，控制检索开销。
- **文件与引用管理：** 实现 Agent 独立工作区、路径约束与内容版本校验，保护只读语料并避免笔记覆盖；报告结论绑定源文件路径、行号与版本，支持证据回溯。
- **量化评估设计：** 基于 LangSmith / OpenEvals 设计固定测试集评估方案，定义检索相关性、回答忠实度与帮助性指标，以及重排、补检索的同题集对照方法。

## 每一条到底在说什么

这部分用于准备面试，不粘进简历。以“比较 pgvector 与 Milvus 的部署维护”举例：

| 简历中的能力 | 你应当能解释的具体动作 | 去哪里学 |
| --- | --- | --- |
| Agent Loop 与按需分工 | 主可以自己查，也可以让 A 查 pgvector、B 查 Milvus；主接收两者的结论与引用，不接收完整工具历史 | 理解文档第 6、7 节；面试文档第 3、7 节 |
| 持久化混合检索 | BM25 找明确提到产品名的段落，向量检索找语义相关的段落；合并重排后选择证据，下次任务复用索引 | 理解文档第 4、5 节；面试文档第 5 节 |
| 证据评估与受限补查 | 判断已有段落能否支撑部署维护的比较；缺少某一方面就换检索词补查，但不能无限搜索，更不能编造费用数字 | 理解文档第 5、10 节；面试文档第 5、8 节 |
| 文件保护与出处核对 | A 和 B 的 notes.md 位于不同目录；修改前核对版本，报告保留原文位置。引用能定位到原文，不等于模型结论必然正确 | 理解文档第 9、11 节；面试文档第 6、9 节 |
| 固定测试集评估方案 | 分辨找错资料、无依据的结论与答非所问；说明评估器实际入参、对照变量、样本与成本边界 | [量化评估博客](LANGSMITH_RAG_EVALUATION.md) 第 4-10 节 |

前四条对应项目已实现功能；第五条对应评估方案设计。学习仓库 `2e6d82a` 已编写 12 条问答样例、RAG Target、三类 OpenEvals 评估器和 LangSmith 批量评估调用；DocResearch 没有新增 SDK、评估运行代码或实验成绩。不能把学习笔记的演示分数写成本项目实测提升。

## 对应证据

| 表述 | 源码 | 测试 |
| --- | --- | --- |
| 按需委派与依赖 | runtime.py / coordination.py | test_coordination.py / test_runtime.py |
| ES / Milvus / HNSW / RRF | stores.py: PersistentRetriever | test_stores.py / test_stores_integration.py |
| 版本化入库与索引复用 | stores.py: ingest / prepare / verify_rows | 双写失败、内容改变、跨连接复用、损坏拒绝测试 |
| 改写 / 重排 / 评估 / 补检索 | agentic.py / rerank.py | test_agentic.py |
| 路径 / 版本 / 文件 | workspace.py: Corpus / WorkFiles / ArtifactWriter | test_workspace.py / test_workfiles.py |
| 工具契约与预算 | models.py / runtime.py: Budget | test_runtime.py |
| 提供方接口 | provider.py: CompatibleModel | test_provider.py 的 MockTransport |

上述四条功能描述对应实际实现，新增评估条目对应方案设计；都不等于宣称所有真实模型任务已稳定完成。已复用本机 ES+IK、Milvus，真实向量入库和重连复用已有验证；真实简单任务完成检索、读写和报告且未派发子代理。一例真实复杂任务完成两个并行研究任务和一个依赖核验任务，生成保留资料缺口的报告；实际使用 62 次请求，显式上限为 80，不证明默认 48 次预算足够。历史预算耗尽和 HTTP 402 记录仍保留。完整记录见 [VALIDATION.md](VALIDATION.md)。

20 题小测只衡量基础检索后端，不覆盖完整 Agentic RAG，不代表大样本质量或生产规模。没有前端、OCR、在线逐文件增量同步或分布式事务。“本地资料”也不意味着 live 模式不外发文本。

技术栈可写 Python、asyncio、Pydantic、Tool Calling、Elasticsearch、IK、Milvus、HNSW、RRF、Rerank、Agentic RAG、Docker。没有使用 FastAPI 或 Python LangGraph，不能仅因为原学习仓库中用过就添加。

个人技术栈可增加“LangSmith / OpenEvals（RAG 评估实践）”；放在 DocResearch 项目技术栏时标注“评估方案”，不把学习示例中的 SDK 当成本项目依赖。概念与面试回答见 [专文](LANGSMITH_RAG_EVALUATION.md)。

个人完整简历、联系方式、照片、原始输入资料不放到这个公开仓库。
