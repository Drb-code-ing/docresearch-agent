# 简历描述与证据映射

## 可用项目描述

**DocResearch - 多 Agent 资料调研与报告生成助手**

Python · asyncio · Pydantic · Tool Calling · Elasticsearch · Milvus · Agentic RAG · RRF · Rerank

开发一个基于本地资料的调研助手：用户提供问题和资料目录，系统查找相关段落、整理研究笔记，生成带文件出处和行号的报告。简单问题由主 Agent 直接完成；需要比较多个方面时，再分配给子 Agent 分别研究，最后汇总结果。

- 主 Agent 与子 Agent 协作：通过 Tool Calling 让模型选择检索、读写或派发任务，由 Python 校验并执行。独立子任务可并发执行，有前后依赖的任务须等待前置结果；子 Agent 只返回结论、出处和资料缺口，不回传全部阅读过程。
- 文档检索与补查：将问题改写为检索词，用 Elasticsearch 的 IK/BM25 查关键词、Milvus 的 HNSW 查语义相近片段；经 RRF 合并和 Rerank 重排后，检查资料能否回答问题，不足时最多补查一次。文档索引持久保存，可跨运行复用。
- 文件读写与保护：主子 Agent 都可创建、读取和修改研究笔记，但各用独立目录，不能改动输入资料。通过 Pydantic 检查参数，限制文件路径与大小；修改时核对内容版本，避免用旧内容覆盖新文件。
- 来源核对与报告生成：保存每条结论对应的文件、行号和原文版本。主 Agent 可选用子 Agent 已提交的结论；若要补充自己的判断，须先读取相关原文。最终统一生成报告，并列出资料无法回答的问题。
- 运行限制与排错：为所有 Agent 共用一份请求次数预算，限制循环轮数和同时执行的子任务数；超时或失败时停止相关任务、记录原因，避免无限调用。保存工具执行记录与模型用量，便于定位问题。

## 每一条到底在说什么

这部分用于准备面试，不粘进简历。以“比较 pgvector 与 Milvus 的部署维护”举例：

| 简历中的能力 | 你应当能解释的具体动作 | 去哪里学 |
| --- | --- | --- |
| 主子协作 | 主可以自己查；也可以让 A 查 pgvector、B 查 Milvus，等两者返回再决定是否补查 | 理解文档第 6、7 节；面试文档第 3、7 节 |
| 检索与补查 | 先找有关段落，再判断这些段落有没有提供维护或费用依据；没有数值就不能比较价格 | 理解文档第 4、5 节；面试文档第 5 节 |
| 文件保护 | A 和 B 都写 notes.md，却位于不同目录，不会互相覆盖；原始资料不能修改 | 理解文档第 11 节；面试文档第 6 节 |
| 来源核对 | 主收到“可复用已有 PostgreSQL”这个结论，可以选用；不能把它改成“性能更好”却照搬原引用 | 理解文档第 9 节；面试文档第 9 节 |
| 运行限制 | 资料没有费用数字，继续搜索也可能无用；程序限制调用次数，失败时留下记录而不是无限跑 | 理解文档第 10 节；面试文档第 8 节 |

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
