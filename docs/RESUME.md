# 简历描述与证据映射

## 可用项目描述

**DocResearch - 多 Agent 资料调研与报告生成助手**

Python · asyncio · Pydantic · Tool Calling · BM25 · 向量检索 · RRF · pytest

面向技术资料阅读与方案调研，用户输入研究问题和本地资料目录，系统自动检索文档、拆分研究任务并汇总证据，生成包含研究结论、资料缺口和原文出处的 Markdown 报告，支持多文档分析与结果追溯。

- 任务规划与子代理协作：基于 Tool Calling 实现“模型决策、工具执行、结果回填”的循环；主代理将独立研究维度派发给子代理，以独立对话上下文和有界并发完成研究，再统一汇总发现与证据。
- 资料处理与混合检索：对 Markdown/TXT 建立分块快照，使用 BM25 关键词召回、可选 Embedding 余弦召回与 RRF 排名融合定位资料；支持代理改写查询、补充检索和按片段 ID 回读原文。
- 证据汇总与报告生成：以结构化结果承接研究发现、引用和资料缺口，校验引用来自任务内已读取的片段；统一生成报告与原文快照，保留来源路径、行号和内容版本，便于核对结论依据。
- 文件与工具权限：通过 Pydantic 校验工具参数，限制资料类型、体积和目录范围；子代理只读且不可递归派发，不开放通用 Shell，报告由统一出口写入独立目录，避免覆盖原始资料。
- 运行控制与异常处理：共享调用次数预算，限制代理步数、检索次数和并发数；结合请求与任务超时取消未完成子任务，区分完成、部分完成和失败状态，记录工具轨迹、耗时与模型用量。
- 工程验证：51 项 pytest 测试及 Windows/Linux CI 通过，覆盖检索、权限、引用与失败路径；完成真实模型双子代理调研和报告生成验收，沉淀模块设计与面试文档。

## 对应证据

| 表述 | 源码 | 测试 |
| --- | --- | --- |
| 子代理与并发 | runtime.py: child / loop | test_runtime.py |
| BM25 / RRF | retrieval.py: Retriever | test_retrieval.py |
| 路径 / 版本 / 文件 | workspace.py: Corpus / ArtifactWriter | test_workspace.py |
| 工具契约与预算 | models.py / runtime.py: Budget | test_runtime.py |
| 提供方接口 | provider.py: CompatibleModel | test_provider.py 的 MockTransport |

真实 BM25 端到端运行已通过；Embedding 的独立真实冒烟超时，接口计算路径通过模拟测试。没有大样本模型质量评测、生产使用、向量数据库服务、前端和 OCR。不要把这些写成已实现；“本地资料”也不意味着 live 模式不外发文本。

技术栈可补 Python、asyncio、Pydantic、pytest、Tool Calling、BM25/RRF。没有使用 FastAPI 或 Python LangGraph，不能仅因为原方案提到就添加。

个人完整简历、联系方式、照片、原始输入资料不放到这个公开仓库。
