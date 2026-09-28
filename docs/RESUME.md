# 简历描述与证据映射

## 可用项目描述

**DocResearch - 多 Agent 资料调研与报告生成助手**

Python · asyncio · Pydantic · Tool Calling · Elasticsearch · Milvus · Hybrid RAG · RRF

面向技术资料阅读与方案调研，用户输入研究问题和本地资料目录，系统自动检索文档、拆分研究任务并汇总证据，生成包含研究结论、资料缺口和原文出处的 Markdown 报告，支持多文档分析与结果追溯。

- 任务规划与子代理协作：基于 Tool Calling 实现“模型决策、工具执行、结果回填”的循环；主代理将独立研究维度派发给子代理，以独立对话上下文和有界并发完成研究，再统一汇总发现与证据。
- 持久化与混合检索：基于 Elasticsearch 的 IK 分词/BM25 与 Milvus 的 HNSW/COSINE 实现双路召回，按统一片段 ID 做 RRF 融合；分离入库与查询，以资料和模型指纹复用索引，双库核验完成后发布，避免混用旧版本或半成品数据。
- 证据汇总与报告生成：以结构化结果承接研究发现、引用和资料缺口，校验引用来自任务内已读取的片段；统一生成报告与原文快照，保留来源路径、行号和内容版本，便于核对结论依据。
- 文件与工具权限：通过 Pydantic 校验工具参数，限制资料类型、体积和目录范围；子代理只读且不可递归派发，不开放通用 Shell，报告由统一出口写入独立目录，避免覆盖原始资料。
- 运行控制与异常处理：共享调用次数预算，限制代理步数、检索次数和并发数；结合请求与任务超时取消未完成子任务，区分完成、部分完成和失败状态，记录工具轨迹、耗时与模型用量。

## 对应证据

| 表述 | 源码 | 测试 |
| --- | --- | --- |
| 子代理与并发 | runtime.py: child / loop | test_runtime.py |
| ES / Milvus / HNSW / RRF | stores.py: PersistentRetriever | test_stores.py / test_stores_integration.py |
| 版本化入库与索引复用 | stores.py: ingest / prepare / verify_rows | 双写失败、内容改变、跨连接复用、损坏拒绝测试 |
| 路径 / 版本 / 文件 | workspace.py: Corpus / ArtifactWriter | test_workspace.py |
| 工具契约与预算 | models.py / runtime.py: Budget | test_runtime.py |
| 提供方接口 | provider.py: CompatibleModel | test_provider.py 的 MockTransport |

已复用本机 Docker 的 Elasticsearch 8.17.0 + IK、Milvus v3.0.0，真实 Embedding 入库与双子代理调研通过。重复入库没有重复调用文档 Embedding，单独集成测试验证重连复用和存储损坏拒绝。20 题检索小测仅为教学回归，不代表大样本质量或生产规模；没有前端、OCR、在线逐文件增量同步或分布式事务。“本地资料”也不意味着 live 模式不外发文本。

技术栈可写 Python、asyncio、Pydantic、Tool Calling、Elasticsearch、IK、Milvus、HNSW、RRF、Docker。没有使用 FastAPI 或 Python LangGraph，不能仅因为原学习仓库中用过就添加。

个人完整简历、联系方式、照片、原始输入资料不放到这个公开仓库。
