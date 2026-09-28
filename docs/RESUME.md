# 简历描述与证据映射

## 可用项目描述

**DocResearch - 多 Agent 资料调研与报告生成助手**

Python · asyncio · Pydantic · Tool Calling · Elasticsearch · Milvus · Agentic RAG · RRF · Rerank

独立开发面向技术资料调研与方案对比的多 Agent 助手，将 Agent Loop 与 Agentic RAG 结合，支持自主检索、笔记整理和任务分工，生成可追溯原文的调研报告。

- 用 Python 实现 Agent Loop 与 Tool Calling，主 Agent 可直接检索、读写文件，复杂任务按需拆分；通过 asyncio 并发执行子任务，隔离子 Agent 上下文，仅回传结论与引用，避免中间记录堆入主对话。
- 采用 Elasticsearch BM25 + Milvus 向量检索互补召回，经 RRF 融合、Rerank 重排筛选证据，兼顾技术术语匹配与语义相似检索；持久化文档索引，支持跨任务复用。
- 在检索工具中加入查询改写与证据评估，对资料不足的问题按缺失信息发起补查，而非单次检索后直接生成答案；通过补查上限和共享请求预算，控制重复搜索与模型调用次数。
- 为各 Agent 设计独立文件工作区与内容版本校验，避免笔记相互覆盖及旧版本覆盖新内容；原始资料保持只读，报告结论关联文件路径、行号与版本，支持逐条核对出处。

## 每一条到底在说什么

这部分用于准备面试，不粘进简历。以“比较 pgvector 与 Milvus 的部署维护”举例：

| 简历中的能力 | 你应当能解释的具体动作 | 去哪里学 |
| --- | --- | --- |
| Agent Loop 与按需分工 | 主可以自己查，也可以让 A 查 pgvector、B 查 Milvus；主接收两者的结论与引用，不接收完整工具历史 | 理解文档第 6、7 节；面试文档第 3、7 节 |
| 持久化混合检索 | BM25 找明确提到产品名的段落，向量检索找语义相关的段落；合并重排后选择证据，下次任务复用索引 | 理解文档第 4、5 节；面试文档第 5 节 |
| 证据评估与受限补查 | 判断已有段落能否支撑部署维护的比较；缺少某一方面就换检索词补查，但不能无限搜索，更不能编造费用数字 | 理解文档第 5、10 节；面试文档第 5、8 节 |
| 文件保护与出处核对 | A 和 B 的 notes.md 位于不同目录；修改前核对版本，报告保留原文位置。引用能定位到原文，不等于模型结论必然正确 | 理解文档第 9、11 节；面试文档第 6、9 节 |

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

上述项目描述对应实际实现，不等于宣称所有真实模型任务都稳定完成。已复用本机 ES+IK、Milvus，真实向量入库和重连复用已有验证；真实简单任务完成检索、读写和报告且未派发子代理。一例真实复杂任务完成两个并行研究任务和一个依赖核验任务，生成保留资料缺口的报告；实际使用 62 次请求，显式上限为 80，不证明默认 48 次预算足够。历史预算耗尽和 HTTP 402 记录仍保留。完整记录见 [VALIDATION.md](VALIDATION.md)。

20 题小测只衡量基础检索后端，不覆盖完整 Agentic RAG，不代表大样本质量或生产规模。没有前端、OCR、在线逐文件增量同步或分布式事务。“本地资料”也不意味着 live 模式不外发文本。

技术栈可写 Python、asyncio、Pydantic、Tool Calling、Elasticsearch、IK、Milvus、HNSW、RRF、Rerank、Agentic RAG、Docker。没有使用 FastAPI 或 Python LangGraph，不能仅因为原学习仓库中用过就添加。

个人完整简历、联系方式、照片、原始输入资料不放到这个公开仓库。
