# Elasticsearch + Milvus 使用说明

正式 `docresearch run` 默认使用 Elasticsearch BM25 + Milvus HNSW/COSINE + RRF。`demo` 和 `walkthrough.py` 保留离线教学后端；`run --backend memory` 是显式的对照模式，不是服务失败时的自动降级。

## 1. 使用已有 Docker 服务

本机已验证：Elasticsearch 8.17.0，安装 `analysis-ik`；Milvus standalone v3.0.0，配套 etcd 与 MinIO。Python 使用官方 Elasticsearch 8.x 异步客户端和 PyMilvus 2.6.x 异步客户端，已实测这组兼容性。

已有容器先开启 Docker Desktop，再按依赖启动：

```powershell
docker start es-dev milvus-etcd milvus-minio milvus-standalone
docker ps
docker exec es-dev bin/elasticsearch-plugin list
```

程序不创建或替换已有 Docker 配置，不删除已有索引、集合、容器、volume 或学习数据。只使用 `docresearch_<namespace>_<snapshot>` 命名的独立索引与集合。

其他机器需要自己提供相同协议的服务和持久化 volume，不必照搬本机容器名称。默认端口为 ES 9200、Milvus 19530。不要把未鉴权的开发服务暴露到公网。

## 2. 显式配置

先按 README 配置聊天和 Embedding 服务，再设置存储。环境变量只作用于当前 PowerShell，项目不会自动读 `.env`。

```powershell
$env:DOCRESEARCH_ES_URL = "http://localhost:9200"
$env:DOCRESEARCH_MILVUS_URI = "http://localhost:19530"
$env:DOCRESEARCH_NAMESPACE = "docs"
$env:DOCRESEARCH_ES_ANALYZER = "ik_max_word"
$env:DOCRESEARCH_ES_SEARCH_ANALYZER = "ik_smart"
```

IK 写入时细分、查询时粗分，BM25 由 Elasticsearch/Lucene 执行，不调用本地 rank-bm25。没有 IK 插件时，可以显式把两项都改成 `cjk` 或都改成 `standard`；不会静默换分词。不同分词配置选择不同快照，需要重新入库。

需要认证时用 `DOCRESEARCH_ES_API_KEY` 和 `DOCRESEARCH_MILVUS_TOKEN`。连接信息不进入模型提示，不写进运行产物。远端连接应配置 HTTPS/安全端口；本项目不负责部署认证、网络访问控制和多租户隔离。

## 3. 先入库，再研究

```powershell
uv sync --extra dev
uv run docresearch ingest --corpus examples/corpus
uv run docresearch run "比较 pgvector 和 Milvus 的部署维护约束，引用资料并指出缺口" --corpus examples/corpus
```

首次 ingest 把原文快照写入 ES，把真实向量写入 Milvus。两边验证通过后发布 ready manifest。重复 ingest 同一快照会返回 `reused: true` 和 `embedding_requests: 0`。

run 只检查并使用已入库的快照，不重新向量化所有文档。基础后端为每条查询生成向量，两通道各取最多 20 条，以统一 Source ID 做 RRF。

Agent 调用 search 时，外层 `AgenticSearch` 先保留原问题并生成 1 至 2 条改写查询，并发搜索后再次按 ID 融合，最多留下 8 条候选；随后重排、评估充分性，必要时补检索一次。主可以直接调用，也可以把复杂问题交给子代理。改写、评估、查询向量与重排均消耗共享请求预算。

专用 DashScope 重排单独配置，三项须同时存在：

```powershell
$env:DOCRESEARCH_RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
$env:DOCRESEARCH_RERANK_API_KEY = "<你的重排服务密钥>"
$env:DOCRESEARCH_RERANK_MODEL = "qwen3-rerank"
```

代码使用 DashScope 原生请求格式，不把任意 OpenAI 兼容地址当成重排端点。未配置专用服务时，LLM 对候选排序并评估，产物的 reranker 字段标记 `llm`；配置了专用服务却失败时不会偷偷跳过。重排只改变阅读次序，不证明结论正确。

## 4. 资料更新与失败处理

快照指纹包括片段 ID 集合、Embedding 提供方地址/模型/版本的哈希、分词配置与程序 schema 版本。密钥不参与指纹。新增、修改、删除文件，或切换向量模型后，会选中新快照，必须再 ingest。

同一模型名称背后的权重变更无法由程序自动识别，手动增加 `DOCRESEARCH_EMBEDDING_REVISION`，再入库。不要复用不兼容向量。

| 现象 | 处理方式 |
| --- | --- |
| `IndexNotReady` | 检查配置后运行 ingest；run 不会自动付费重建或回退内存 |
| `IndexMismatch` | 两库内容/身份/维度不一致；检查服务与该项目快照，别直接删整个数据库 |
| IK analyze 失败 | 安装与 ES 版本匹配的插件，或显式配置内置分词并重新入库 |
| 双写中途失败、没有 manifest | 相同输入重跑 ingest，按确定 ID upsert，完成后才发布 |
| 已发布快照被手动损坏 | 保留诊断；使用新 namespace 重建，不自动覆盖已发布快照 |
| Milvus 报错指向代理端口而非 19530 | 检查 gRPC 的代理设置；本机服务可在当前终端把 localhost/127.0.0.1 加入 NO_PROXY 和 no_grpc_proxy |

`DOCRESEARCH_TRUST_ENV` 只控制模型 HTTPX 客户端，不控制 Milvus 的 gRPC 客户端。如果本机服务被误送入代理，可对当前 PowerShell 显式追加直连地址，保留既有例外：

```powershell
$env:NO_PROXY = (@($env:NO_PROXY, "localhost", "127.0.0.1") | Where-Object { $_ }) -join ","
$env:no_grpc_proxy = (@($env:no_grpc_proxy, "localhost", "127.0.0.1") | Where-Object { $_ }) -join ","
```

ready 不是分布式事务。崩溃可能留下未完成的索引/集合，但没有 ready 就不会被 run 使用；读取还核对两库 ID 集合和 ES 原文。入库约定单写者串行执行，不提供分布式锁，不支持多个入库进程同时修改同一快照。

旧快照保留供追溯，不会自动删除，因此会逐渐占用磁盘。正式运维需要保留策略与清理流程，本项目没有自动 GC。文件上限仍为 100 个文件、2 MB 总资料、400 个片段，不能仅因使用数据库就宣称百万级性能。

## 5. 验证

```powershell
uv run pytest -q
$env:DOCRESEARCH_TEST_SERVICES = "1"
uv run pytest tests/test_stores_integration.py -q
Remove-Item Env:DOCRESEARCH_TEST_SERVICES
uv run python -X utf8 -m docresearch.evaluation --backend es-milvus
```

前两类测试不调用真实模型。集成测试连接默认本机 ES/Milvus，使用随机专属测试空间与合成二维向量，结束时只清理自己创建且核验归属的索引/集合。测试覆盖客户端关闭后的复用、资料删除后换快照、存储损坏拒绝读取。

最后一条评测使用真实查询向量，会消耗 API 额度；先完成样例 ingest。它只衡量基础后端的文档覆盖，不调用外层 AgenticSearch，不是答案正确率或完整 Agentic RAG 的评估。最新实测和真实调用阻塞记录在 VALIDATION.md。
