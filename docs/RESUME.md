# 简历描述与证据映射

## 可用项目描述

**DocResearch - 本地资料调研与报告生成 Agent**

Python · asyncio · Pydantic · Tool Calling · BM25 / RRF · pytest · GitHub Actions

面向本地技术资料调研，将文件读取、证据检索、子代理派发与报告落盘串成 CLI 工作流；支持 Markdown/TXT 资料和带引用的 Markdown 报告，通过离线测试与受控真实调用验证执行链路。

- 主从 Agent 执行：实现 Tool Calling 循环，将独立任务派发到隔离对话上下文的只读子代理；通过 asyncio 限制并发，统一回收证据、失败状态与资料缺口。
- 检索与来源追踪：使用 BM25 检索分块资料，提供 Embedding 余弦召回与 RRF 融合接口；保存文件路径、行号和内容版本，校验报告引用来自当前任务读取的证据。
- 受控工具与运行预算：以 Pydantic 校验工具参数，分离资料读取与报告写入目录；限制调用次数、子代理步数和任务时长，对越界路径、预算耗尽及超时返回明确状态。
- 验证与交付：51 项 pytest 测试及跨平台 CI 通过；以自编资料完成真实模型双子代理调研与报告生成，保存执行轨迹和来源快照，沉淀项目理解及面试文档。

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
