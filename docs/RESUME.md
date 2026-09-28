# 简历描述与证据映射

## 可用项目描述

**DocResearch - 多 Agent 资料调研与报告生成助手**

Python · asyncio · Pydantic · Tool Calling · Elasticsearch · Milvus · Agentic RAG · RRF · Rerank

面向技术资料阅读与方案调研，将 Python Agent Loop 与 Agentic RAG 结合：用户输入研究问题和本地资料目录，主代理按任务复杂度选择直接研究或委派子任务，检索证据、整理笔记并生成包含结论、资料缺口和原文出处的 Markdown 报告。

- 按需规划与协作：基于 Tool Calling 实现工具循环，主代理可直接检索和读写；复杂任务通过依赖图与有界并发派发。子代理使用独立上下文，仅回传限长发现、引用和缺口，减少原文与工具历史累积。
- Agentic RAG 检索：使用查询改写、Elasticsearch IK/BM25 与 Milvus HNSW/COSINE 双路召回，RRF 融合后接入专用 Rerank 和证据充分性评估，资料不足时有限补检索；通过版本指纹与双库核验复用持久索引。
- 文件工作区与工具契约：主子代理均可在私有目录读写和编辑笔记，以 SHA-256 版本检查、单次匹配编辑和原子替换控制覆盖；Pydantic 校验参数，限制路径与体积，保留原始资料只读及最终报告统一出口。
- 证据汇总与报告生成：登记子任务发现，以 finding_id 保留结论与引用；主代理自写结论须引用亲自读取的片段。报告附来源路径、行号和内容版本，子原文不自动进入主上下文，支持按需核验。
- 运行控制与异常处理：共享聊天、向量与重排调用预算，限制轮数、检索次数和并发；结合超时取消与失败依赖处理收敛任务状态，记录工具轨迹、上下文字符数、耗时与模型用量。

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

上述项目描述对应实际实现，不等于宣称所有真实模型任务都稳定完成。已复用本机 ES+IK、Milvus，真实向量入库和重连复用已有验证；新版真实简单任务完成检索、读写和报告且未派发子代理。新版复杂流程有确定性测试，真实首次运行耗尽预算，修复后复测遇到 HTTP 402，尚未通过复杂真实验收。完整记录见 [VALIDATION.md](VALIDATION.md)。

20 题小测只衡量基础检索后端，不覆盖完整 Agentic RAG，不代表大样本质量或生产规模。没有前端、OCR、在线逐文件增量同步或分布式事务。“本地资料”也不意味着 live 模式不外发文本。

技术栈可写 Python、asyncio、Pydantic、Tool Calling、Elasticsearch、IK、Milvus、HNSW、RRF、Rerank、Agentic RAG、Docker。没有使用 FastAPI 或 Python LangGraph，不能仅因为原学习仓库中用过就添加。

个人完整简历、联系方式、照片、原始输入资料不放到这个公开仓库。
