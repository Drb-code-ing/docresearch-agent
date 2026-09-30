# DocResearch 项目理解：从一条命令到一份有出处的报告

这篇文章不是功能清单，也不要求你先懂 Python Agent 框架。我们只跟着一个问题走：

> 我有三份关于 pgvector、Milvus 和选型原则的资料。请比较两种方案用于小型知识库时的部署维护与检索能力；有依据才下结论，没有数据就说缺什么。

读完以后，你应该能自己画出“文件怎么变成模型看到的证据、模型怎么请求操作、子代理怎么返回、报告怎么写入”的过程。面试表述放在另一篇 [面试文档](INTERVIEW_GUIDE.md)，这里先把事情学明白。

想进一步判断“这些检索与生成步骤有没有用”，读 [LangSmith RAG 量化评估博客](LANGSMITH_RAG_EVALUATION.md)。它讲固定测试集、评分需要的数据和对照实验设计，不把本项目的运行时证据判断混成 LangSmith 效果评测。

**先读一遍运行故事，再看实现。** 第 1 节先回答“这个程序在忙什么”；第 3、5、6、7、9、11 节分别解释资料、工具、循环、分工、引用和文件。第 4 节的数据库参数可以第二遍再读，不需要先记住 HNSW 的参数才能理解整个项目。每读完一节，先用自己的话复述例子，再打开对应源码。

### 按你要弄明白的问题进入正文

| 你现在的疑问 | 先看哪里 | 读完应能做什么 |
| --- | --- | --- |
| Agent Loop 和 Agentic RAG 到底怎样结合？ | 第 1 节故事、第 5 节检索、第 6 节循环 | 说明外层选动作、内层找证据，为什么一次 search 不是一次模型请求 |
| “隔离上下文”到底隔离了什么？ | [四份状态的变化](#context-ownership) | 手推子完成以后主的 messages、seen、文件、结论登记表各有什么 |
| 为什么任务不能随便执行？ | [任务状态转换](#task-transitions) | 判断提前核验、重复派发和前置失败分别怎样处理 |
| 独立工作区与版本校验怎么实现？ | [编辑冲突的完整闭环](#file-conflict) | 解释路径归属、版本冲突、重新读取再编辑，而不只背“乐观锁” |
| 简历中的版本到底是哪种？ | [三种版本的区别](#three-versions) | 区分引用原文版本、索引快照指纹、工作文件版本 |
| 这些类为什么这样拆？ | [设计与替换点](#design-boundaries) | 说明具体变化落在哪个模块，以及哪些能力没有实现 |

本文的表格与小例子是教学推演，不是假装记录了一次真实模型运行。真实验收边界在 [VALIDATION.md](VALIDATION.md)，学习时先理解机制，面试时再分清哪些行为有哪一层证据。

## 1. 先看它替你做了什么

假设没有这个程序，你会怎样完成任务？

1. 打开三份资料，找到与部署、维护和检索相关的段落。
2. 分别整理 pgvector 和 Milvus 的情况。
3. 对照原文，合并相同内容，保留差异。
4. 写一份报告，给每条结论标注来自哪个文件、哪些行。
5. 没有延迟或费用数据，就写“没有这方面的数据”，而不是猜一个数字。

DocResearch 做的就是这件事。区别是：**模型负责提出下一步动作和组织结论，Python 代码负责真正查资料、执行动作、检查限制、保存文件。**

它的输入是“问题 + 本地资料目录”，输出是“报告 + 引用原文 + 运行记录”。不是通用编程助手，不会替你运行 Shell 或随意修改电脑文件。

正式检索由两个持久化服务完成：Elasticsearch 负责关键词，Milvus 负责向量。样例资料也恰好讨论 Milvus，但“资料研究对象”和“程序实际使用的检索服务”是两个角色；本项目没有使用 pgvector。离线 demo 另有内存教学后端，方便先看懂流程。

### 先认识三个词，不要急着背框架

- **检索**：从文件里挑出可能回答问题的几段话，不是直接得到答案。例如“部署维护”能找到“监控、备份”相关段落，但不一定能找到费用数字。
- **工具**：Python 允许模型申请的一种操作。例如 search 查资料，write_file 写笔记。模型只提出申请，程序才真正执行。
- **上下文**：这一轮发给模型的内容，包括问题、之前的回复和工具结果。子 Agent 的上下文独立，意思是它不会自动收到主 Agent 之前读过的全部内容。

### 用一件小事看完整运行

先问一个小问题：“根据资料，已有 PostgreSQL 的应用如何使用 pgvector？”一条可能的执行路径是：

| 步骤 | 谁在做 | 具体发生什么 |
| --- | --- | --- |
| 1 | 用户 | 提供问题和 examples/corpus 资料目录 |
| 2 | Python | 读取允许的文件，记住正文、文件名、行号与版本 |
| 3 | 主 Agent | 请求 search，查 pgvector 与 PostgreSQL 的关系 |
| 4 | 检索代码 | 找到相关段落，把正文与出处交回主 Agent |
| 5 | 主 Agent | 阅读段落；需要整理时，在自己的 notes.md 中写下研究笔记 |
| 6 | 主 Agent | 提交结论、出处和资料没有回答的问题 |
| 7 | Python | 检查引用并生成 report.md，同时保存来源与执行记录 |

**这条路径没有子 Agent。** 写笔记也是工具能力，不是所有任务必须经过的固定步骤。真实运行的具体先后由模型选择，程序负责限制哪些动作可以执行。

把问题换成“分别整理 pgvector、Milvus 的部署维护，再比较差异”，主可以选择另一条路径：

```text
主 Agent：决定分工
  -> 子 A：读 pgvector 资料，返回结论和出处
  -> 子 B：读 Milvus 资料，返回结论和出处
主 Agent：看两份结果，决定直接汇总还是继续核对
  -> 如需核验：等 A、B 完成，再派一个核验任务或自己读原文
主 Agent：提交报告 -> Python 检查后保存
```

A 与 B 可以同时工作，核验“它们的结论”却必须等它们先交结果。这就是后文“任务依赖”的意思。这里只演示代码允许的路径，不宣称每个真实模型都会做出最优拆分。

现在可以把项目拆成两半：**Agent Loop 决定下一步做什么；Agentic RAG 决定一次 search 怎样更好地找证据。** 文件工具把读到的内容、研究笔记和最终报告连接起来。不是为了叫“多 Agent”而强制把小问题拆开。

### 先运行，再读解释

在 PowerShell 中：

```powershell
cd E:\docresearch-agent
uv sync --extra dev
uv run docresearch demo
```

`uv sync` 按锁文件安装依赖，放在项目自己的 `.venv` 中；`uv run` 使用这套环境执行命令，不需要手动激活虚拟环境。

最后会打印一个新的 `reports/<run_id>/` 目录。每次的 ID 不一样，不必记它。

先只打开里面的 `report.md`，你会看到发现、资料缺口、来源三个部分。再打开 `sources.json`，这里保存的不是模型总结，而是被引用的原文。

**`demo` 不联网，也不调用真实大模型。** 它用一个固定回答的 `DemoModel` 演示完整程序流程，所以别人克隆仓库以后，不填密钥也能运行。真实模式叫 `run`，后面会讲两者哪里相同、哪里不同。

`demo` 的状态是 `partial`，正常退出码为 0。这不是安装失败：程序成功生成报告，同时明确保留“没有进行真实推理和性能对比”的缺口。

## 2. 命令究竟从哪里进入 Python

如果你更熟悉 TypeScript，可以先这样对应：

| Python 写法 | 在这里怎么理解 |
| --- | --- |
| `list` | 有顺序的数组，例如 `messages` |
| `dict` | 键值对象，例如一条工具结果 |
| `class` / 实例 | 一套操作和它持有的数据，例如 `Corpus` 对象 |
| `def` / `return` | 定义函数 / 返回结果 |
| `async def` / `await` | 定义可等待的异步操作 / 等待它完成 |
| `try ... finally` | 不管成功失败，都执行清理，例如关闭连接 |
| 类型注解 | 说明期望类型；普通注解本身不自动检查输入 |

`pyproject.toml` 把 docresearch 这个命令指向 `docresearch.cli:main`。因此运行命令之后，真正进入的是 [cli.py](../src/docresearch/cli.py) 的 `main()`。

它先用 argparse 把命令行文字解析成对象。例如 `--max-calls 24` 会把默认的 48 覆盖为 `args.max_calls == 24`。然后通过 `asyncio.run(execute(args))` 启动一次异步任务。

先忽略错误分支，把 `execute` 看成下面的顺序。**这是帮助理解的简化代码，不是另一个需要运行的实现。**

```python
corpus = Corpus(args.corpus)  # 读入资料
model = DemoModel()  # 选择模型适配器
research = ResearchRun(corpus, args.output, model)
outcome = await research.run(question)  # 执行一次研究
print(outcome.status, outcome.directory)
```

注意三个不同的时刻：

1. `Corpus(...)` 会真正读取文件，不是只记住一个目录名。
2. `ResearchRun(...)` 装配检索器、预算和写入器，还没有让模型研究问题。
3. `await research.run(question)` 先检查检索后端，再进入研究循环。正式后端使用已经入库的 ES/Milvus 快照；内存教学后端则在当次运行准备索引。

`await` 不是“新开一个线程”。它允许当前操作在等待网络时，让同一事件循环中的其他任务继续执行。后面的子代理并发依赖这一点。

### 一个能看到中间过程的学习脚本

```powershell
uv run python -X utf8 examples/walkthrough.py
```

它全程离线，使用项目真实的 `Corpus`、`Retriever`、参数模型和运行时，逐段打印中间数据。`-X utf8` 是为了在 Windows 终端和重定向时保持中文编码一致。

下面第 3 至 8 节讲数据与执行流程。学习脚本演示内存版本的算法和共同的 Agent 循环；第 4 节重点解释正式 ES/Milvus 实现。现在不必一次读完整个 `runtime.py`。

## 3. 第一件事：文件变成什么对象

入口是 [workspace.py](../src/docresearch/workspace.py) 的 `Corpus`。`Corpus` 可以理解为“这次任务允许使用的资料集合”。

程序先检查目录，再逐个读取 UTF-8 编码的 .md 和 .txt。隐藏文件、隐藏目录和符号链接会跳过；其他格式不会进入资料集。不是让模型直接打开任意路径。

### 为什么要分块

假设有一本几十万字的文档。每个问题都把整本书发给模型，费用高，也不容易集中注意力。我们先把文本拆成小段，查询时只返回最相关的几段。这样的段叫 **chunk，文本片段**。

本项目按完整行累计，接近 1800 字符就开始下一块，不把一行从中间切断，不做相邻块重叠。三份样例都很短，所以实际是 **3 个文件、3 个片段**，不是每篇强行切成多块。

单行超过 1800 字符会直接拒绝。这与“多行累计分块”是两件事：前者是输入约束，后者是切分规则。1800 是工程选定的上限，不是测出来的最优值。

### 一段原文不只是一条字符串

每个片段保存为一个 `Source`。样例中的真实对象大致如下，这里只缩短了 `version` 和 `text` 的展示：

```text
id          = e5a95ea4d55ef429
path        = pgvector.md
start_line  = 1
end_line    = 11
version     = 2dda04bb...       # 文件完整内容的 SHA-256，实际保存 64 位
text        = # pgvector 示例资料 ...
```

每个字段都在解决一个实际问题：

- `text`：模型到底看到了什么。
- `path` + `start_line` + `end_line`：人去哪里核对。
- `version`：文件修改过以后，怎么知道报告用的是哪个版本。
- id：检索、工具返回、报告引用之间，如何指向同一个片段。

`version` 是整个文件原始字节的哈希。id 则由相对路径、文件版本、行号和片段正文一起计算，取哈希前 16 位。它是内容相关的标识，不是数据库自增序号，也不是加密保护。

### 为什么称为“快照”

文件读进内存后，`Corpus.sources` 就保存了这些 `Source`。后面 `read_source(id)` 读取的是这个对象，不会再打开磁盘上的新版本。

例如，10:00 读入资料，10:01 文件被编辑，10:02 模型回读来源，拿到的仍是 10:00 的内容。这样检索与报告依据不会在任务中途变成两个版本。

这是任务内的一致性选择，不是数据库事务。多个文件是依次读取的，并没有保证在同一个瞬间拍下整个目录。

**检查自己是否懂了：** 只保存 `pgvector.md` 这个名字够不够？不够，既不知道引用了哪几行，也不知道之后是否改过内容。

## 4. 第二件事：ES 和 Milvus 怎样持久化并找到资料

先明确分工，避免把“数据库”当成一个可以代替所有步骤的盒子：

| 部件 | 保存或执行什么 | 不负责什么 |
| --- | --- | --- |
| Corpus | 本次读入的原文快照、行号、Source ID | 不保存长期向量索引 |
| Elasticsearch | 原文和元数据、倒排索引、IK 分词、BM25 排序 | 不生成向量 |
| Embedding 服务 | 将文本或查询变成数字向量 | 不保存检索索引 |
| Milvus | 持久保存向量，建立 HNSW 索引，按 COSINE 搜索 | 不写最终报告 |
| PersistentRetriever | 入库核验、两路检索、RRF、映射回 Source | 不判断答案一定正确 |

实现集中在 [stores.py](../src/docresearch/stores.py)。离线学习脚本使用 [retrieval.py](../src/docresearch/retrieval.py) 的内存对照实现，但正式命令默认使用 ES/Milvus。

### 4.1 为什么要区分入库和查询

原先每运行一次就把文档全部重新向量化，关掉程序向量就丢了。现在把长期准备工作叫 **ingest，入库**：

```text
ingest：
读取文件 -> 分块快照 -> 生成文档向量
                    -> ES 保存原文和关键词索引
                    -> Milvus 保存向量和 HNSW 索引
                    -> 两边核验完成 -> 发布 ready 记录
```

正常调研只做：

```text
run：
读取当前资料版本 -> 找到对应的 ready 快照
-> 模型请求 search
-> ES 关键词结果 + 查询向量 -> Milvus 向量结果
-> RRF 排序 -> Source 原文 -> 模型继续研究
```

只有第一次入库需要生成所有文档向量。相同资料和配置再次 ingest 会返回 reused=true，文档 Embedding 请求数为 0。查询仍需要生成当前问题的向量，不能说以后完全没有向量 API 成本。

配置好服务后实际运行：

```powershell
uv run docresearch ingest --corpus examples/corpus
uv run docresearch run "比较两种方案的部署维护，引用原文并指出缺口" --corpus examples/corpus
```

具体 Docker、凭据与分词配置见 [使用说明](RETRIEVAL_SETUP.md)。本机复用的是已有 ES 8.17.0 + IK、Milvus standalone v3.0.0，不重新创建或覆盖学习数据。

### 4.2 ES 怎么从字符串找到相关片段

先把原文分成可查词项，这个过程由 analyzer，也就是分词分析器完成。项目默认写入用 ik_max_word，查询用 ik_smart：前者细粒度切词，后者相对简洁地分析查询。分词模式属于索引配置，修改后需要新建快照。

每个 Source 写成 ES 的一个 document，_id 与 Source.id 相同。text 字段是全文检索字段，path/version/id 等是精确值字段。ES 为 text 建立倒排索引，可以直观理解为：

```text
PostgreSQL -> 包含这个词的 Source ID 列表
向量       -> 包含这个词的 Source ID 列表
维护       -> 包含这个词的 Source ID 列表
```

查询时程序给 ES 发 match 请求，ES 自己完成分词和 BM25 评分。Python 不扫描全部文档，也不手写 BM25。

先理解 BM25 的三个直觉：

1. 查询词在片段中出现，说明可能相关。
2. 所有片段都有的词区分度低，少数片段才有的词区分度高。
3. 重复次数与文档长度要校正，不能让最长文本天然占优。

项目查询只取 kind=source 的文档，避免把 ready 元数据作为资料召回；按相关分数降序取最多 20 条，分数相同用 Source ID 确定顺序。

离线脚本的 rank-bm25 则是另一种教学实现，它打印英文词、中文单字与双字。库已实现 BM25，没有手写算法。这套分词和“小语料非正分处理”不要误说成 ES 的实现。

### 4.3 Embedding 为什么能补充关键词

原文写“独立部署会增加监控、备份与数据同步”，查询写英文 monitoring backups synchronization，关键词重叠可能很少，但意思接近。

Embedding 服务把文本变成一串语义特征数字。不是给文档随便编号，也不能把每一维直接命名为“部署”或“成本”。

用可手算的二维向量理解，以下是教学数据，不是真实服务返回值：

```text
查询 q = (1, 0)
片段 A = (0.9, 0.1)
片段 B = (0.2, 0.8)

cos(q,A) = 0.9 / sqrt(0.9²+0.1²) ≈ 0.994
cos(q,B) = 0.2 / sqrt(0.2²+0.8²) ≈ 0.243
```

A 的方向更接近查询，所以语义通道倾向 A。0.994 不是“结论 99.4% 正确”，只是方向相似度。

真实样例使用 1024 维向量。入库每批最多 32 段，检查数量、维度、NaN/Inf、零向量，再归一化。相同的向量模型用于文档和查询，查询维度必须与集合一致。

### 4.4 Milvus 做了哪些内存矩阵没有做的工作

集合是 Milvus 中组织一批记录的单位，可以类比一张具有特定字段的表。本项目集合只有两个主要字段：

```text
id      VARCHAR(16)，主键，与 ES 的 _id 相同
vector  FLOAT_VECTOR，维度取真实 Embedding 返回值
```

原文只在 ES 和本次 Corpus 保存，不重复塞进每条向量记录。入库使用按主键 upsert，重复同一 ID 不产生第二个逻辑文档。

向量索引采用 HNSW + COSINE。HNSW 可理解为一张多层的近邻导航图：搜索时从较粗的层迅速靠近目标，再在底层扩展候选；它不是每次由 Python 对全部 N 个向量逐个算距离。近似搜索以效率换取可能漏掉某些真正最近邻的风险，不能宣称永不漏召回。

参数在代码中是 M=16、efConstruction=128、查询 ef=64：

- M 控制节点连接数量，影响内存与图的连通性。
- efConstruction 控制建图时探索候选的范围。
- ef 控制查询时探索范围，通常越大越愿意用延迟换召回。

这些是明确可复现的工程参数，没有宣称已针对大数据量寻优。Milvus 的 flush 用于请求完成落盘，load_collection 用于使集合可查询，Strong consistency 用于读取已完成写入的视图。它们与 ES 的 refresh 不是一回事：refresh 主要让新文档可被搜索。

### 4.5 两路结果如何合成一个列表

ES 和 Milvus 的原始分数不在同一量纲，不能直接把 BM25 的 8.2 与余弦的 0.8 相加。RRF 按名次融合，每条通道的贡献是 1/(60+rank)，rank 从 1 开始。

| 片段 | ES 名次 | Milvus 名次 | 融合分数 |
| --- | --- | --- | --- |
| A | 1 | 3 | 1/61 + 1/63 ≈ 0.03227 |
| B | 未进入候选 | 1 | 1/61 ≈ 0.01639 |

这次 A 更靠前。两路用同一个 Source ID 去重和累加，最后拿 ID 从已核对的 Corpus 找回完整原文。索引中的未知 ID 会触发错误，不直接当合法证据。

代码并发启动 ES 查询与“查询 Embedding -> Milvus 搜索”，都成功才融合。一边失败会取消并等待另一边，不悄悄把单路结果包装成混合检索成功。

RRF 不调用额外模型，不是 Cross-Encoder 重排。它简单、不依赖原始分数校准，但丢掉了分差信息。

### 4.6 文件改了，怎么保证不搜到旧段落

不是把所有版本无限塞进同一个集合，然后希望模型忽略旧内容。程序计算一个快照指纹，覆盖：

```text
Source ID 集合 + Embedding 服务/模型/人工版本的哈希
+ ES 分词配置 + 存储 schema 版本
```

由它生成 ES 索引与 Milvus 集合的共同名称：`docresearch_<namespace>_<指纹前缀>`。地址只以哈希参与，不把 key、端点写进 manifest。

文件新增、修改或删除，Source ID 集合变化，程序就选择不同名称。未入库的新快照直接报 IndexNotReady，不继续查询旧库。因此“删了文件又查出旧内容”的情况不会靠模型自行纠正。

模型提供方在同一名称下换了权重，程序无法自动知道。手动增加 EMBEDDING_REVISION 后再入库。旧快照保留，没有自动垃圾回收，会增加存储占用。

### 4.7 写两套数据库，中途失败会怎样

两库没有分布式事务。代码用一个简单但明确的可用性协议：

1. 用项目归属标记确认操作的是本项目索引/集合。
2. ES bulk 写原文，Milvus upsert 写向量并 flush。
3. 核对 ES 原文及 ID、Milvus ID 集合和维度，必须对应同一个 Corpus。
4. 全部通过后才在 ES 写 manifest，表示这个快照 ready。

中途失败可能留下部分物理数据，但没有 manifest 就不允许研究。用同一输入重跑 ingest，可以按确定 ID 再次写入尚未发布的快照。已经 ready 的快照不自动覆写，只校验和复用；如果被外部手动损坏，报 IndexMismatch。

prepare 读取 manifest 后仍核验两库，不把“有一条成功标记”当永久正确。这个小项目假设同一快照只有一个入库写者，不提供分布式锁；它不是跨数据库 ACID 事务，也没有在线增量更新或多用户隔离。

### 4.8 现在还保留哪些内存内容

Corpus 的原文快照和 Agent messages 仍在内存，这是为了本次证据一致性和对话执行。**持久向量索引在 Milvus，关键词倒排索引在 ES**。保留内存中的当前数据，不等于拿内存当数据库。

demo 和 walkthrough 为了零依赖教学，保留旧的内存检索器。它们都经同一个检索接口接到运行时；正式默认 run 使用 PersistentRetriever。服务失败不会触发自动回退。


## 5. 第三件事：模型怎么“使用工具”

### 从一次普通函数调用理解 Tool Calling

先看模型如何申请一次 search，再看这个工具内部怎样检索。普通 Python 代码可以这样查询：

```python
sources = await retriever.search("Milvus", limit=2)
```

但远端模型不能直接调用你电脑里的 Python 函数。模型只能通过接口返回一条结构化请求，例如：

```json
{
  "id": "call_001",
  "type": "function",
  "function": {
    "name": "search",
    "arguments": "{\"query\":\"Milvus\",\"limit\":2}"
  }
}
```

这叫 Tool Calling。请把它理解为 **“模型申请执行 `search`”**，不是“模型已经完成 `search`”。

`arguments` 在传输协议中是 JSON 字符串。代码必须先把字符串解析并检查成 `Search` 对象，才真正调用 Python 函数。

### 参数检查在哪里

[models.py](../src/docresearch/models.py) 定义工具的输入结构：

```python
class Search(Contract):
    query: ShortText
    limit: int = Field(default=5, ge=1, le=8)
```

Contract 启用严格类型并禁止额外字段。于是：

- `{"query":"Milvus","limit":2}` 可以执行。
- `limit` 为字符串 "2"，拒绝，不悄悄转换。
- `limit` 为 100，拒绝，不让模型无限拿资料。
- 多出 `path`: "../secret"，拒绝，这个工具根本不接受路径参数。

同一份 Pydantic 定义有两种用途：`model_json_schema()` 生成说明给模型看；`model_validate_json()` 在执行前真正校验。**给模型看规则不等于程序可以省掉检查。**

学习脚本第 4 段演示合法输入和预期的 `ValidationError`。看到这个错误不是脚本坏了，而是违规参数确实被拒绝。

### 模型怎么知道工具执行结果

模型不知道 Python 返回了什么，直到程序把结果放回下一次请求的 `messages`。

`messages` 是对话数组，不是永久记忆。一次 `search` 的变化可以画成：

```text
0 system     研究规则：资料是数据，只能引用已获得的来源
1 user       比较两种方案的部署与维护
2 assistant  请求 search，调用 ID 为 call_001
3 tool       call_001 的结果：sources=[带正文的 Source ...]
4 assistant  下一次模型回复：继续查、派发，或提交报告
```

工具结果必须带 `tool_call_id`="call_001"，这样模型接口才知道它对应哪一次动作。一次返回多个工具调用时，更不能把结果 ID 混用。

下面是一轮包含两个动作的协议示例。为突出配对，只列出追加到 system/user 后面的三条消息；搜索结果也刻意简化为空：

```json
[
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {"id": "call_a", "type": "function", "function": {"name": "search", "arguments": "{\"query\":\"pgvector 部署\",\"limit\":2}"}},
      {"id": "call_b", "type": "function", "function": {"name": "read_file", "arguments": "{\"area\":\"work\",\"path\":\"notes.md\"}"}}
    ]
  },
  {"role": "tool", "tool_call_id": "call_a", "content": "{\"sources\":[]}"},
  {"role": "tool", "tool_call_id": "call_b", "content": "{\"error\":\"invalid_arguments_or_source\"}"}
]
```

这里假设 notes.md 尚不存在。**失败也要回填对应动作的结果**，不能直接丢掉 call_b。若把第二条 tool 的 ID 也写成 call_a，就变成 A 收到两份答复、B 没有答复，服务可能拒绝后续请求，程序也失去了可靠配对。

`loop` 用 `gather` 按请求顺序收集返回值，再 `zip(reply.calls, outputs, strict=True)` 回填。因此“B 比 A 先完成”不代表把 B 的内容交给 A。`arguments` 和 `content` 在接口中是 JSON 字符串，不是 Python 已执行的函数。终止工具和 plan 另有规则：必须单独一轮调用，不能与这些普通动作混在一起。

`search` 已返回完整的入库片段，而不是只有摘要。`read_source(id)` 用于按已知 ID 明确回读同一个片段，不会扩大成整篇长文件，也不访问任意路径。

`list_documents` 则只返回文件路径、版本、大小，不返回每份资料全文。它也不会让全部片段自动进入 `seen`。

### search 内部的 Agentic RAG 流程

底层 Retriever 只查候选；[agentic.py](../src/docresearch/agentic.py) 的 `AgenticSearch` 负责怎样组织查询、筛选证据和有限重试：

```text
原问题 -> 生成 1-2 条查询改写，同时保留原问题
       -> 最多 3 个查询并发执行 ES/Milvus 双路检索
       -> 每查询最多 8 个候选，跨查询按 ID 做 RRF，保留 8 个
       -> 可选 DashScope 专用 reranker
       -> LLM 对有用 ID 排序，并判断证据是否回答所问事实
       -> 证据不足且有新查询时，只补检索 1 轮
       -> 返回正文、sufficient、missing、attempts
```

先把这串术语翻译成一次查资料的过程。下面是帮助理解的例子，不是实际模型输出的逐字转录：

| 处理步骤 | 输入是什么 | 做什么、交出什么 |
| --- | --- | --- |
| 查询改写 | “哪个维护成本更低？” | 生成“部署维护要求”“监控备份”等其他问法，原问题也保留，避免只换个词就丢掉原意 |
| 两路召回 | 每一种问法 | ES 查关键词，Milvus 查意思接近的文本，各交出一个候选片段列表。“召回”就是先把可能有用的片段找回来 |
| RRF 合并 | 多个候选列表 | 用同一片段 ID 去重，综合它在各列表中的名次；这一步没有理解原文的含义 |
| Rerank 重排 | 问题 + 少量候选正文 | 更仔细地比较哪段与问题相关，把值得先读的段落排前面 |
| 证据评估 | 问题 + 排序后的正文 | 不只问“相关吗”，而是问“这些话是否真的足够回答问题？”例如只有维护事项，没有费用，就仍然不足 |
| 补查或返回 | 不足原因、可选新查询 | 最多补查一次。仍缺费用数字，就把缺口交回 Agent，而不是编价格 |

这里最重要的区别是：**“监控和备份”与费用问题相关，但相关不等于已经证明哪种方案更便宜。** 重排不能代替证据判断，补查也不能保证资料中本来没有的事实会出现。

改写使用 `QueryRewrite` 契约；评估使用 `EvidenceGrade`，包含 ordered_ids/sufficient/missing/retry_query。程序拒绝未知 ID、重复 ID、超量候选，以及“零片段却声称充分”。模型仍可能误判证据，结构校验不是事实证明。

不配置专用接口时，LLM 明确执行排序与证据判断。配置 `DOCRESEARCH_RERANK_URL/API_KEY/MODEL` 三项后，先经 [rerank.py](../src/docresearch/rerank.py) 的 DashScope 适配器，再由 LLM 判断。专用接口失败不会暗中当作成功。两层 RRF 分别融合两个库与多个查询，不是答案置信度。

## 6. 第四件事：把一次工具调用接成循环

[runtime.py](../src/docresearch/runtime.py) 的 `ResearchRun.loop()` 反复做下面的事情：

```text
请求模型 -> 检查返回动作 -> 执行工具 -> 把结果交回模型
    ^                                      |
    +--------------------------------------+
```

“Agent”在这里不是另一个神秘组件。它就是模型、这段循环，以及可以被调用的工具。

真实模式中，下一步由模型决定。模型发现信息不够，可以换查询再 `search`；问题有独立方面，可以 `task`；有足够资料则提交报告。固定 RAG 通常把“检索一次再生成”写死，本项目把有边界的动作选择交给模型，这就是 Agentic RAG 的部分。

### 一轮循环里程序做什么

1. 先占用一次共享请求额度，再调用 `model.chat(messages, tools)`。
2. 把回复变成内部 `Reply`，里面有文字、`ToolCall` 列表和 `usage`。
3. 如果只有文字，就记录文字并提醒模型使用正式终止工具，不能仅凭“我完成了”保存报告。
4. 普通工具先检查角色权限，再检查参数，然后交给 `dispatch()`。
5. 工具结果按调用 ID 回填，进入下一轮。
6. 终止工具必须单独调用，结构和引用检查都通过才结束。

主通过 save_report 表示“可以生成报告了”；子通过 finish_research 表示“我的研究做完了”。findings 是研究结论，gaps 是资料没回答的问题。主既能提交自己查证的结论，也能选用子已交付的结论；后者的编号叫 finding_id，第 9 节用具体例子解释，不必现在背字段。

save_report **不会立刻写磁盘**。模型先交“报告申请单”（代码里的 SaveReport），程序检查内容，把选中的子结论取出来，整理成完整 Report，最后由 run 统一保存。这样模型不能自己指定任意路径，子任务也不能抢先覆盖最终报告。

普通工具参数错了，会收到受控错误；Pydantic 反馈包含字段名和错误类型，不回显完整输入。模型可在剩余步数内修正。主子默认各最多 10 轮，每代理最多 search 3 次；最后两轮提示收尾，硬上限仍由程序执行。

### 三种“状态”别混在一起

| 名称 | 谁使用 | 存什么 |
| --- | --- | --- |
| `messages` | 发给模型 | 对话、动作请求、工具结果 |
| `AgentState` | Python 运行时 | 是否主代理、`seen`、`search` 次数 |
| `Budget` | 全部代理共享 | 全局调用数、工具数、`chat` `usage` |

模型说“我读过 pgvector.md”不能修改 seen。只有这个代理自己 search/read 得到正文才登记来源。子结果不修改主 seen，其结论走独立登记表。

## 7. 第五件事：为什么还需要子代理

单个代理已经能完成简单问题。子代理不是每次必须用，也不是越多越智能。

我们的比较任务可以拆成两个独立问题：“部署维护有什么差别”和“检索能力有什么差别”。它们都能直接读同一份资料，不必等待对方结论，适合并发研究。

“先比较方案，再核对比较结论”有依赖，不能盲目同时执行。主用 plan 显式声明 depends_on，程序检查重复 ID、未知依赖和环；提前启动后继会被拒绝，由主在前置完成后重新请求。它不是自动等待依赖的调度器，也不自动证明语义依赖是否合理。

### task 实际执行了什么

用前面的比较问题，先按人能理解的顺序过一遍：

1. 主把三项工作记入计划：A 研究 pgvector，B 研究 Milvus，C 核对 A、B 的结论。
2. plan 只是登记计划，**不会自动启动 A 或 B**。主接下来还要调用 task 请求执行。
3. A、B 没有前置任务，可以一起申请。Python 为每个子创建新的对话列表与自己的笔记目录。
4. 子各自查资料并交出简短结果。程序记录谁完成、谁失败，主收到结果后才继续决定下一步。
5. 主再请求执行 C。C 只有在 A、B 都成功后才能开始；提前请求会被拒绝，不会让它凭空核验尚不存在的结果。
6. 若 A 失败，依赖 A 的 C 也会被标记为不能继续。主仍可基于其他有效结果提交带缺口的报告。

“依赖图”只是把上面的先后关系写下来，图没有神奇的自动规划能力。**模型提出分工，Coordinator 这个 Python 类检查分工是否合法并记住进度。**

先 plan，再 task。例如：

```json
{"tasks":[
  {"task_id":"pg","question":"研究 pgvector 部署约束","depends_on":[]},
  {"task_id":"mv","question":"研究 Milvus 部署约束","depends_on":[]},
  {"task_id":"check","question":"对照原文核对比较结论","depends_on":["pg","mv"]}
]}
```

主可同轮派发 task({task_id:"pg"}) 和 task({task_id:"mv"})；check 必须等待前两项成功。child 创建新 AgentState，调用同一个 loop，只接收问题与精简依赖结果。前置失败会让后继标记 dependency_failed，不永远卡在 pending。计划只能追加新 ID，不改写已完成问题。

<a id="task-transitions"></a>
### 手推一次计划的状态变化

实际状态只有 `pending/running/completed/failed`；`dependency_failed` 是失败原因，不是第五种状态。状态由 [Coordinator](../src/docresearch/coordination.py) 修改，不由模型在回答里宣布。

| 动作 | pg / mv / check 的状态 | 谁执行检查或修改 |
| --- | --- | --- |
| plan 登记三项 | pending / pending / pending | plan 全部检查通过后一次加入任务表 |
| 提前 task(check) | 仍全部 pending；返回工具错误 | start 发现前置未完成，拒绝本次派发，不自动排队 |
| task(pg)、task(mv) | running / running / pending | start 先标记 running，child 再申请 Semaphore 名额 |
| 两个子提交有效结果 | completed / completed / pending | loop 校验结果后，finish 登记发现并记完成 |
| 再次 task(check) | completed / completed / running | start 把两份精简结果交给 child |
| check 完成，主 save_report | 全部 completed，可整理报告 | report 检查没有未完成计划，并展开已登记结论 |

两种失败要分开：如果 pg 执行失败，check 在尝试启动或发布报告时会被置为 `failed`，原因是 `dependency_failed`；如果只是 pg 还没做完，check 仍是 `pending`。后者不能直接发布报告跳过。

重复 task(pg) 也被 start 拒绝，因为它已经不是 pending。需要补研究就追加新 ID，不把完成记录改回 pending。`running` 表示已接纳派发，可能还在等 Semaphore，不等于此刻正在请求模型；看实际并发要看 `child_start` 和活跃计数。这是一套内存中的状态检查，tasks.json 是结果导出，不是崩溃后恢复执行的检查点。

**不是复制一份 Agent 代码，也不是另起一个 Python 进程。** `parent=False` 选择子角色的工具集合与轮数配置，`loop()` 自己创建新的 `system`/`user` 消息。主、子轮数可分别配置，但默认都为 10 轮。

| 内容 | 父子之间是否共享 |
| --- | --- |
| 资料快照 `Corpus`、检索索引 | 共享，避免重复读取和建索引 |
| 模型连接、全局 `Budget` | 共享，费用相关调用统一计数 |
| `messages` | 不共享历史，只交子问题和完成依赖的精简结果 |
| `AgentState.seen` / `searches` | 各自独立 |
| 文件工作区 | 每代理独立，同名 notes.md 不冲突 |
| 最终报告、再派发工具 | 子代理没有 |

主子都有 list_documents/search/read_source/read_file/write_file/edit_file。子还可 finish_research；主额外有 plan/task/save_report。**简单任务由主直接做，不强制创建子代理。** 子不能递归派发或保存最终报告，但能在自己工作区读写编辑笔记。

Schema 和 dispatch 是两层权限检查。子即使凭空构造 task/save_report 也会被拒绝；写权限不是全部取消，而是将路径绑定到本代理工作目录。

### 子代理把什么交回来

不是只交一句“pgvector 比较适合”，而是结构化结果。例如 `result` 部分可以是：

```json
{
  "findings": [
    {
      "statement": "资料说明，已有 PostgreSQL 的小型应用可以复用它保存向量。",
      "source_ids": ["e5a95ea4d55ef429"]
    }
  ],
  "gaps": ["资料没有提供同条件费用数据。"]
}
```

运行时校验后为每条发现分配 pg:f1 一类 finding_id。task 回传 task_id/status/findings/gaps/files；files 只有路径、hash、字节数。发现最多 6 条、缺口最多 4 条，单条文字最多 500 字符。子工具历史和 Source.text 不回传。

这意味着主收到的是：“A 的工作完成了；结论是这句话，来自这段资料；还有这个问题没查到；A 写过这些文件。”主**不会因为收到文件名，就自动读到文件正文**；当前 read_file 只能读取输入资料或自己的工作目录，不能读取子私有笔记。主核验结论时，应按 source_id 读取共享的原文，或明确派发新的核验任务。

减少原文累积不等于彻底消除污染：摘要也可能误导或遗漏条件。主需要核对时，可以主动 read_source 或派验证任务；不是为了省 token 就禁止核验。

<a id="context-ownership"></a>
### 手推一次子完成后的四份状态

假设主刚登记了 pg，自己还没读任何正文。子 pg 搜到片段 `s1`，写了 notes.md，再交出结论。`s1` 在这里是片段编号的教学简称，真实 ID 是 16 个十六进制字符（64 bit）。

| 状态放在哪里 | 子研究时发生什么 | 子结束以后主得到什么 |
| --- | --- | --- |
| 每次 loop 的局部 messages | 子的新列表保存自己的 search 请求与含正文的结果 | 主列表只加入 task 的结果摘要，不拼接子的 messages |
| 每个 AgentState.seen | 子获得正文后变成 {s1} | 主仍为空；没有“把子已读集合并进主”的操作 |
| 每个 WorkFiles.root | 子在 workspaces/run_id/pg/notes.md 写笔记 | 主只见 files 元数据；自己的同名笔记仍在 coordinator 目录 |
| 共享 Coordinator.findings | 子终止结果通过检查后，登记 pg:f1 -> 结论及 source_ids | 主拿 pg:f1 选用原结论；登记表由程序保存，不是主的阅读记录 |

对应到代码只有几处关键动作：

```python
# child 中为这项任务建立状态与工作区；不是复制父状态。
state = AgentState(task_id, False)
self.workspaces[task_id] = WorkFiles(self.writer.root / "workspaces" / self.run_id / task_id)
# loop 内每次新建列表；只有问题和已完成依赖的摘要被显式传入。
messages = [{"role": "system", "content": role_rules}, {"role": "user", "content": question}]
# 以下表示实际回传路径，省略了参数校验、限额及事件记录。
result = await self.loop(question, state)
summary = self.coordinator.finish(task_id, result, self.workspaces[task_id].inventory())
```

这段是帮助阅读源码的摘录式伪代码，role_rules 代表实际选择的主/子系统提示。并不是把这个片段粘贴出来就能单独运行。

现在回答三个问题：

1. **主想直接采用子结论？** save_report 传 finding_ids=["pg:f1"]，程序原样取出已经登记的 statement 和引用。
2. **主想改成一个新判断？** 先 read_source(s1)，这时主 messages 才出现原文，主 seen 才增加 s1，然后提交自己的 findings。是否推理正确还需核对语义。
3. **主想打开子 notes.md？** 当前工具不支持。主的 read_file(area="work", path="notes.md") 只会读自己的文件；核验事实应读共享 corpus 的原文。

所以，简历的“隔离子 Agent 上下文”不是“主什么都看不到”，而是**不自动传探索过程；通过明确的结果契约交接；需要证据时按需回读**。共用 HTTP 客户端也不等于共用聊天记录，本项目每次 chat 都显式发送本次 loop 的 messages。

### 并发 2 和最多 4 个任务不是一回事

`asyncio.Semaphore(2)` 可以理解为两张执行通行证：同时最多两个 `child` 进入研究区。假设派发四个，第 3、4 个先等；某个完成并释放通行证后，后面的才能开始。

`max_tasks=4` 限制的是一次研究累计派发多少个。即使前四个都结束，也不能继续派发第五个。

所以“最多两个同时执行”不能代替“总共最多四个”。真实并发主要让两个网络等待重叠，不保证总耗时减半，更不保证结果更好。

## 8. 把已经学过的部分接回完整流程

现在再看整体图，里面的每个词应该都有具体含义：

```mermaid
flowchart TD
    A[命令行: 问题与目录] --> B[Corpus: 文件变成 Source 快照]
    B --> C[核验 ES 与 Milvus 已入库快照]
    C --> D[主代理 loop]
    D --> E[直接 search / read_source]
    D --> F[task: 新上下文子代理]
    F --> G[检索与私有文件操作，提交限长结论和引用 ID]
    E --> D
    G --> D
    D --> H[save_report: 结构与引用检查]
    H --> I[run: 判定状态并统一发布五个产物]
```

全离线 `demo` 的固定顺序是：

```text
主代理：plan -> 两个 task -> save_report
每个子代理：search -> write_file -> read_file -> edit_file -> finish_research
每次 search 内部：改写 -> 检索 -> 排序与证据判断
```

CLI demo 为 17 次模拟请求和 14 次工具调用。请求包括改写与评估，工具包括计划、派发、文件操作和终止工具。模拟器固定这些决定，只用于观察程序流程，不代表真实效果。

真实简单任务已在 0 个子任务的情况下完成检索、写笔记、读回、编辑与报告。复杂流程的真实成功/失败边界见 [VALIDATION](VALIDATION.md)，不要把旧架构成功记录当作全部新路径都通过。文档向量在之前的 ingest 中生成。

两种模式都由 `Corpus` 提供原文快照，由 `ResearchRun` 执行工具循环，最后交给 `ArtifactWriter` 发布文件。不同的是两个可替换组件：demo 使用 `DemoModel` 和内存 `Retriever`，正式模式使用 `CompatibleModel` 和 `PersistentRetriever`。运行时通过统一的 `chat`、`prepare`、`search` 接口调用它们。这叫依赖注入：把“由谁回复、到哪里检索”与“怎么执行循环”分开，测试就不需要外部模型和数据库每次作出相同响应。

## 9. 报告的引用为什么可以核对，但不能保证正确

先区分两种编号。它们不是两个数据库，也不要求模型理解哈希算法：

| 名称 | 指向什么 | 为什么需要它 |
| --- | --- | --- |
| source_id | 一段原始资料 | 让代码知道引用到底是哪份文件的哪些行 |
| finding_id | 子 Agent 已提交的一条结论，以及它的引用 | 让主直接选用这条完整结论，不必把子读过的全部原文再塞进主上下文 |

例如，子 A 读到 pgvector.md，提交：“已有 PostgreSQL 的小型应用可以复用它保存向量。”程序先检查 A 是否收到过引用的原文，再把这句话和出处保存起来，编号为 pg:f1。这份保存在程序中的列表，就是“结论登记表”。

主此时有两种不同操作：

1. **选用原结论：** 提交 finding_ids=["pg:f1"]。代码取出已经登记的原句和出处，不让主偷偷替换句子。
2. **提出新判断：** 先 read_source 阅读相关原文，再提交自己的 findings。例如要补充部署约束，不能仅凭子给出的引用编号，就假装自己已经看过资料。

seen 可以理解成“程序给这个 Agent 记的一张已读片段清单”。主、子各有一张；收到子结论不会自动把子的清单抄给主。对应实现是：子 findings 的 source_ids 必须属于子 seen，主自己写的 findings 必须属于主 seen。

| 主提交什么 | 前提 | 程序是否接受这一种引用用法 |
| --- | --- | --- |
| finding_ids=["pg:f1"] | 子已成功登记该结论 | 接受，保留登记的原句和出处，不要求主再读一遍 |
| findings=[新句子，source_ids=[s1]] | 只有子读过 s1 | 拒绝，主自己的 seen 没有 s1 |
| 同样的新句子与 s1 | 主先主动读到了 s1 | 引用资格检查通过；仍需满足其他报告契约 |
| 内容不被 s1 支持的新句子 | 主确实读过 s1 | 可能通过结构检查，语义却错，不能称为自动验真 |

`validate_evidence()` 的关键逻辑很短：

```python
for finding in result.findings:
    if any(key not in state.seen for key in finding.source_ids):
        raise ValueError("Citation was not observed by this agent")
```

这能阻止引用一个不存在或没有见过的片段。但请看反例：

```text
原文：本资料没有给出百万向量的延迟数据。
模型结论：百万向量查询延迟为 10 毫秒。
引用：恰好引用了上述原文的真实 ID。
```

ID 检查可能通过，结论仍然错误。因为“出处存在”与“原文支持这个说法”是两个不同问题。

本项目处理前者，并把原文保存下来方便人工核对后者；没有自动的事实蕴含判定器。面试时应说“引用来源可追溯”，不说“彻底消除幻觉”。

## 10. 如果模型一直查、不结束，怎么办

不要指望只在 prompt 里写“尽快结束”。停止条件必须由程序维护。

| 限制 | 默认值 | 防什么问题 |
| --- | --- | --- |
| 聊天 + Embedding + 专用 rerank 请求数 | 48 | 包括改写与证据评估 |
| 计数工具调用 | 64 | 单次响应带出很多工具请求 |
| 主 / 子代理循环轮数 | 10 / 10 | 只说话不结束，或不断返回错误参数 |
| 每代理 `search` 次数 | 3 | 无限改写检索 |
| 子任务总数 / 并发数 | 4 / 2 | 无限制拆分 / 同时压满服务 |
| 单请求 / 研究区间超时 | 30 / 180 秒 | 外部服务卡住、研究一直不完成 |

不是每个数字都能从 CLI 设置。CLI 暴露 `--max-calls` 和 `--timeout`，其他默认值在 [models.py](../src/docresearch/models.py) 的 `Limits` 中。

### 为什么两个子代理同时请求，不会抢过预算

`Budget.invoke()` 的顺序是先检查、先加一，最后才 `await`。简化后是：

```python
if self.calls >= self.limits.max_calls:
    raise BudgetExceeded("Model call budget exhausted")
self.calls += 1
return await function()  # 原实现还包裹了单请求 timeout
```

同一个 `asyncio` 事件循环里，在没有 `await` 的这几行之间不会切换协程。额度先预留，之后才等待网络，因此另一个 `child` 看到的计数已经更新。请求失败也占这一次，不退回。

这不是跨线程、跨进程的锁。将来变成多个服务器共享额度，必须另外设计原子存储或事务。

### 错了以后不能只退出父函数

同一轮多个工具通过 `create_task` 启动，`gather` 等待结果。一个失败时，其他任务可能还在执行，所以 `finally` 会做两步：

```text
给未完成的兄弟任务发 cancel
再 await gather(..., return_exceptions=True)，等它们清理退出
```

`cancel` 是取消请求，不是远端退款按钮。已经到达提供方的请求仍可能生成并计费。

总 `timeout` 覆盖后端 prepare 检查和 Agent 循环；ingest 是另一项受预算与时间限制的操作。CLI 前面的同步文件读入、最后的同步写出不在这个 `timeout` 中。它不是整个操作系统进程的硬超时。

### 状态应该怎么读

| 状态 | 含义 | 正式报告 |
| --- | --- | --- |
| `completed` | 接受了结构化报告，未报告缺口且没有 `child` 失败 | 有 |
| `partial` | 有报告，但有资料缺口或子任务失败 | 有 |
| `budget_exhausted` | 全局调用或工具额度用尽 | 无 |
| `timeout` | 总超时或传播到主运行的请求超时 | 无 |
| `failed` | 轮数耗尽、协议异常等其他失败 | 无 |

后三种通常仍保存四个诊断 JSON，包括任务状态 tasks.json。启动参数、空资料或磁盘写入失败可能发生在这个收尾范围之外，不保证有产物；Ctrl+C 也不保证写完。

局部 `child` 超时可以被转为失败结果交回父代理，父代理仍可输出 `partial`。全局预算耗尽则继续向上传播，终止整次研究。

`completed` 只是程序状态，不是内容质量认证。请求数预算也不是金额预算：`chat` `usage` 只做统计，没有精确金额预留或完整的输入 token 裁剪。

## 11. 最后一步：文件由谁写，写到哪里

`Report` 只有标题、发现和缺口，没有用户可控输出路径。`run()` 统一渲染 Markdown，收集引用原文，再交给 `ArtifactWriter`。

| 文件 | 你应该拿它回答什么问题 |
| --- | --- |
| `report.md` | 结论是什么？缺哪些资料？ |
| `sources.json` | 报告引用的原文到底是什么版本？ |
| `trace.json` | 哪个代理何时开始请求、执行哪个工具、在哪里结束？ |
| `run.json` | 状态、调用数、工具数、并发峰值、耗时、限制是多少？ |
| `tasks.json` | 计划中的依赖是什么？每项任务的状态和精简结果是什么？ |

输出目录必须与资料目录互不包含。每次使用新 run ID，最终产物名只允许这五种；中间工作文件写到 reports/workspaces/<run_id>/<agent_id>/，与最终发布目录分开。

单文件先写同目录临时文件，再 os.replace 到目标；五个文件不是同一事务，磁盘出错可能留下部分发布目录。

### 主子代理怎样读写编辑文件

先看目录，不看实现。假设某次运行编号叫 run-123：

```text
examples/corpus/pgvector.md                  输入资料，谁都不能用工具改它
reports/workspaces/run-123/coordinator/notes.md  主自己的笔记
reports/workspaces/run-123/pg/notes.md           子 pg 自己的笔记
reports/workspaces/run-123/mv/notes.md           子 mv 自己的笔记
reports/run-123/report.md                       Python 统一生成的最终报告
```

run-123 是示意名，真实运行使用随机 ID。工具只需要传 notes.md，代码会把它放进当前 Agent 对应的目录。这里的“私有”表示**工具不允许代理互读互写这些目录**，不是文件被加密，也不是启动了多个容器。电脑上的用户仍能打开这些文件。

因此，“主保留读写权限”具体指能读共享输入资料、创建和修改自己的工作文件、提交最终报告；不是获得任意路径或覆盖别人的笔记的权限。

[workspace.py](../src/docresearch/workspace.py) 的 WorkFiles 只有 read/write/edit 三个主要操作，把路径、版本、限额和原子替换封装在一起。输入目录仍只读，工作文件允许 md/txt/json，单个最多 12000 字符且 48000 字节，每代理最多 8 个文件、96000 字节。

例如第一次写 notes.md 的内容是“待确认维护要求”，代码根据这份内容算出版本标记 v1。读文件时会同时返回正文与这个标记。编辑请求要带上“我依据的版本是 v1”，以及要替换的旧句和新句；成功后内容改变，版本也变为 v2。再有一个请求还拿着 v1，代码就拒绝，避免它用旧笔记覆盖新笔记。v1/v2 是便于讲解的名字，真实标记是 SHA-256 哈希。旧句还必须恰好出现一次，防止一条编辑误改多处。

<a id="file-conflict"></a>
### 旧版本被拒以后，怎样继续工作

独立目录防“不同 Agent 写同一个文件”；版本校验防“同一个 Agent 根据旧内容提交修改”。不是解决同一个问题两次。

假设 pg 的笔记有两行：`结论：待确认` 和 `费用：待确认`。下面 H1/H2/H3 是真实哈希的简称：

| 时刻 | 请求或结果 | 磁盘状态 |
| --- | --- | --- |
| 1 | write_file 新建，expected_version="" | 写入两行，返回 H1 |
| 2 | 基于 H1，把第一行改为“结论：可复用 PostgreSQL” | 成功，内容变成 H2 |
| 3 | 另一个旧请求仍带 H1，要把“费用：待确认”改成“费用：资料未给出” | 旧句虽然仍存在，但当前哈希是 H2，所以拒绝，不覆盖 |
| 4 | read_file 重新读取 | 得到新结论、旧费用行与 H2 |
| 5 | 检查修改仍适用，重新构造 edit_file，带 H2 | 只替换费用这一行，返回 H3，新结论保留 |

旧 H1 可以来自同轮发出的两个编辑请求，也可以来自模型保留的旧阅读结果；程序不负责自动保存或合并旧请求。不能只把 H1 换成 H2、盲目重放原请求：新的内容可能让原修改不再适用。`edit` 还要求 old_text 恰好出现一次；若另一条编辑已经移走或复制了这句话，会先因匹配次数失败。`write` 则先读当前字节并计算哈希，再比较 expected_version，最后写同目录临时文件并 os.replace。

实际 dispatch 为避免回显资料，把多种路径/版本错误归为 `invalid_arguments_or_source` 并给通用提示；模型不一定直接看到 Python 的 Stale file version 文本。正确做法是核对路径与参数、必要时重读，在剩余轮数内修正，不是内置自动合并或无限重试。

**哈希不是递增版本号。** 相同内容会得到相同哈希；内容从 A 变 B 再变回 A，也会回到原哈希。这里检查的是内容相等，不记录完整修改历史。同步的检查与替换只对本进程事件循环避免协程插入；外部进程仍可能竞争。os.replace 解决单文件替换，不使“检查版本 + 写入”成为跨进程原子 CAS，也不保证断电持久性。

<a id="three-versions"></a>
### 项目里三种版本不要混为一谈

| 名称 | 什么时候生成、依据什么 | 保护的对象 | 改变后怎么办 |
| --- | --- | --- | --- |
| Source.version | Corpus 加载时，对源文件字节做 SHA-256 | 本次引用是哪一版原文 | 当前运行继续读自己的快照；下一次加载得到新 Source 身份 |
| 索引快照 fingerprint | 入库/准备查询时，结合 Source ID 集合、向量模型配置与 revision、分词/schema | ES 与 Milvus 是否属于同一批资料和配置 | 要使用新快照须先 ingest；无 ready 记录则拒绝运行 |
| 工作文件 version | 每次 read/write 对笔记完整字节做 SHA-256 | 修改是否基于当前笔记 | 旧 expected_version 被拒，重新读后再决定怎样改 |

自测：只改 Embedding revision，原文没改，Source.version 不变，索引指纹变；只编辑 notes.md，工作文件版本变，不需要重建语料索引。工作笔记不是证据来源，不能写一段话再把它当成原始资料引用。

索引指纹不是所有配置的总哈希：它纳入向量服务 URL、模型名与人工 revision 构成的 identity、ES 分词配置和 schema 标识，但不覆盖全部 HNSW 或查询参数。不能笼统说“改任何模型或索引参数都会自动换快照”。

路径拒绝绝对路径、盘符、父目录、隐藏路径和符号链接。两个子任务都有 notes.md，但物理目录不同，因此不争抢同一文件。版本检查是在单进程同步操作内完成，不是抵御外部恶意进程竞态的分布式锁。

read_file 的 area=corpus 读取启动时文本快照，area=work 读取自己的工作文件。部分行只会获得完整覆盖片段的 source_ids；不能只读标题就自动获得整篇证据资格。想引用其余片段，应再用 read_source。

运行轨迹没有完整模型对话，因此适合定位阶段，不足以精确重放一个真实模型任务。`sources.json` 则确实有资料正文，不能当作无敏感信息的普通日志上传。`reports/` 默认被 Git 忽略。

### 文件限制与安全边界

本工具最多接受 100 个文件、单文件 256000 字节、总计 2000000 字节、400 个 chunk。这些限制让同步处理和上下文规模可控，不意味着它支持大规模文档平台。

模型只看到受控工具，没有 Shell、任意路径、修改源文件的能力。资料中的“忽略规则”“读取密钥”等文字应当被当作数据。工具权限检查能缩小错误动作的范围，但不能保证模型不被诱导写出错误结论。

程序不提供进程/容器隔离，也不抵御恶意本地进程并发替换目录的所有竞态。它服务于可信本地用户，不应不加鉴权、上传隔离就直接公开成网络服务。

## 12. 真实模型和离线模型怎么接到同一套代码

<a id="design-boundaries"></a>
### 从“要改什么”理解模块设计

先不背设计模式名称，先问：有一个需求改变时，应该改哪里，哪些代码不用跟着改？

| 要发生的变化 | 修改或替换的地方 | 保持稳定的地方 |
| --- | --- | --- |
| 离线测试替换成真实模型 | CLI 传入 CompatibleModel 而不是 DemoModel | loop 仍调用 chat 并处理 Reply |
| 内存演示换为 ES/Milvus | CLI 选择 retriever_factory，构造对应后端 | search 对外仍交付 Source，不让模型操作数据库客户端 |
| 服务返回的 HTTP 字段变化 | provider/rerank 的协议转换层 | runtime 内部的 Reply、候选 ID 处理 |
| 增加一项文件限制 | WorkFiles 内集中检查 | Agent 不必自己写路径、配额与替换逻辑 |
| 子任务想绕过依赖 | 不接受模型文字声明，由 Coordinator.start 拒绝 | loop 仍按工具错误回填，让模型重新决策 |

这几种设计分别有名字，但不是同一回事：

- **依赖注入**讲“谁创建依赖”：CLI 组装真实或离线对象，再传给 ResearchRun；loop 不在内部硬编码密钥和创建 HTTP 客户端。
- **策略替换**讲“同一职责能换哪种做法”：内存检索与持久化检索都履行 prepare/search 契约，后端不同，调用方保持不变。不代表已实现热切换或自动故障降级。
- **适配器**讲“怎样把外部协议变成内部数据”：CompatibleModel 把服务 HTTP 响应转为 Reply/ToolCall；DashScopeReranker 把专用返回转为有序来源 ID。
- **Supervisor/Worker**讲“怎样分工”：主保留自己做事的能力，也能委派；子只交研究结果，不能再派发或发布最终报告。
- **显式状态机**讲“哪些转换合法”：Coordinator 的状态字段与条件检查约束任务生命周期。没有为每种状态创建一个类，因此不称为 GoF State 模式的完整实现。

WorkFiles 是集中维护文件规则的封装，版本比较是一种乐观并发检查；不需要为了凑模式再加一组空类。设计的价值是改变只落在相关模块、规则有统一执行位置，而不是接口或类的数量。面试中的口头回答与替代方案见 [设计模式追问](INTERVIEW_GUIDE.md#pattern-defense)。

[provider.py](../src/docresearch/provider.py) 定义 `CompatibleModel` 与 `DemoModel`。运行时只需要对方实现 `chat(messages, tools)`，并得到统一的 `Reply`。

真实适配器用 HTTPX 调用 `/chat/completions`；向量接口是 `/embeddings`。HTTP 200 只意味着传输状态正常，如果 `choices=[]`、`message` 为空或向量索引缺失，仍会抛 `ProviderProtocolError`。

配置方式在 [README](../README.md#真实模型模式)。重点理解四件事：

1. `demo` 不读真实凭据；`ingest` 和 `run` 从 `DOCRESEARCH_*` 环境变量创建客户端。
2. 正式 ES/Milvus 后端必须配置 Embedding，并先 ingest。只有显式选择 `--backend memory` 时，不配向量模型才表示本地 BM25；任何正式服务失败都不会静默退回内存。
3. 聊天和向量可以使用不同服务。独立向量 URL/key 必须一起给，防止聊天密钥被发往另一个端点。
4. `.env.example` 是说明文件，程序不会自动加载 `.env`。连接在 CLI 的 `finally` 中关闭。

专用 rerank 有独立 URL/key/model，必须成组配置；不会自动把聊天 key 发给另一个端点。没配置时使用显式 LLM 排序与评估。所有改写、评估、向量和专用 rerank 请求都进入共享 Budget，但 usage 只累计聊天 token。

这个项目遇到过一个实际排错点：Windows 上，即使没有 `HTTPS_PROXY`，HTTPX 仍可能通过系统配置使用代理。既有 Embedding 服务走代理连接超时，保持端点和输入不变、显式直连后返回成功。

所以提供 `DOCRESEARCH_TRUST_ENV=false` 作为显式选择，不自动猜路由。它关闭环境/系统代理和环境证书配置，仍开启 TLS 证书验证。企业网络依赖代理或自定义 CA 时不能照搬这个选项。

**资料在本地，不代表推理也在本地。** 真实聊天会把问题及检索到的正文发给提供方；开启 Embedding 会发送全部入库片段。真实验收只使用自编样例，没有上传私人简历或个人资料。

## 13. 怎么判断项目真的能运行，而不只是看起来能

现在再理解三种不同的验证，目的就很清楚了。

### 确定性测试：代码规则有没有兑现

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

例如“子代理不能写 corpus、其他代理工作区和最终报告，但可以读写自己的笔记”“预算不能超额”“文件修改后仍返回旧快照”，这些是代码规则，用固定输入就能验证，不需要大模型随机回答。

测试中的假模型会故意返回错误引用、慢响应或重复调用 ID，检查运行时是否处理正确。HTTP MockTransport 则替代网络，检查 URL、认证与响应解析。它们不是模型准确率测试。

### 真实链路：提供方能不能完成这类任务

持久化 ES/Milvus 的真实入库、重复复用与旧版双子代理报告已有[存档](evidence/controlled-live-es-milvus/report.md)。按需委派架构已跑通[主代理直接研究与读写](evidence/adaptive-simple/report.md)，0 个子任务，实际经过查询改写、专用重排和证据评估。另有一例[真实复杂报告](evidence/adaptive-complex-success/report.md)：两个研究者并行查证，各自写入、读回和编辑 notes.md，第三个子任务等待两者结束后核验，主选择子结论生成报告。三个任务均完成，最终 partial 表示保留了资料与证据缺口。

读这次记录时，要同时看成功与代价：实际用了 62 次请求，而默认上限是 48，本次显式设为 80；核验子任务也经历多轮未结束和一次结果拒绝。它证明完整路径在这个样例与预算下能执行，不证明默认预算足够或任意任务都稳定。核验还发现了一条把笔记版本号引用到技术资料上的错误，主没有选入该条发现。这正好说明：程序验证来源 ID，模型核对语义，两者职责不同，后者仍可能漏错。此前预算耗尽和 HTTP 402 的记录作为历史保留，详情见 [VALIDATION](VALIDATION.md)。真实服务集成测试另外用合成向量验证重连复用、资料删除后换快照和存储损坏拒绝读取。

这证明选定接口、Tool Calling 和真实向量能协同工作。不代表所有兼容服务都正常，也不代表已有真实用户使用。

### 标注小测：召回了应该找到的资料吗

```powershell
uv run python -X utf8 -m docresearch.evaluation
# 已配置并入库后，对照正式服务（会调用真实查询向量）：
uv run python -X utf8 -m docresearch.evaluation --backend es-milvus
```

评测命令不调用聊天模型，也不调用 `AgenticSearch` 的改写、重排、评估和重试。它从 `examples/retrieval_cases.json` 读取 20 道预先标注的问题，逐题查询基础检索后端；答案标签只用于评分，不会交给检索器。因此以下数字只衡量基础召回，不能解释成完整 Agentic RAG 的质量。

其中 16 题有答案，4 题没有。对有答案题，取前两个 chunk，看它们覆盖多少个预期文档。例如一道题需要 A、B 两篇，实际只找到 A，就得到 1/2 的 recall。最后取 16 题平均值。

在这组只有 3 个片段的教学集上，旧内存 BM25 / 内存混合检索的 document recall@2 是 0.875 / 1.000；正式 ES/Milvus 为 0.96875，top-1 为 0.9375。换存储后第一名表现与候选覆盖并非一起提升，**不能宣称换数据库就一定更准，也不能把这个小样例推广为生产提升。**

更重要的是：4 道无答案题，三种后端都返回了候选。例如问“百万向量 P95 延迟多少毫秒”，原文虽包含“百万向量”“延迟”，却明确没有数值。程序必须阅读原文、记录 gap，不能见到检索命中就编答案。

详细定义、逐题结果、耗时和调用数见 [VALIDATION.md](VALIDATION.md)。要扩展为真正的质量评估，还需要更大、独立标注的语料与问题，以及答案是否被原文支持的人工检查。

## 14. 五个练习，把“看过”变成“会解释”

每次只做一个。下面有预期现象，先自己观察，再看说明。

### 练习一：认出一个 Source

```powershell
uv run python -X utf8 examples/walkthrough.py
```

看第 1 段，指出路径、行号、版本、正文分别在哪。然后回答：文件编辑后，旧 report 引用的是旧内容还是新内容？答案是保存下来的旧快照。

### 练习二：解释检索不等于回答

```powershell
uv run python -X utf8 -m docresearch.evaluation
```

找到“P95 延迟是多少”的用例。它的 `expected_documents` 是空，返回的候选却非空。打开候选原文，说明为什么它不能回答具体数字。

### 练习三：亲眼看预算阻止后续动作

```powershell
uv run docresearch demo --max-calls 1
```

这条命令预期退出码为 1。主模型的第一次模拟回复用掉额度；子代理请求无法继续。应看到 `budget_exhausted`，新目录里有诊断 JSON，没有 `report.md`。不是把旧目录中的报告删除了，每次都是新目录。

### 练习四：看程序怎样拒绝非法引用与写入

```powershell
uv run pytest tests/test_runtime.py -q -k "citation_must_be_seen or child_cannot_delegate_or_publish"
uv run pytest tests/test_coordination.py tests/test_workfiles.py -q
```

打开同名测试：它故意注入坏动作，断言代码拒绝。测试通过意味着“拒绝行为符合预期”，不是坏动作执行成功。

### 练习五：解释并发与清理

```powershell
uv run pytest tests/test_runtime.py -q -k "shared_budget or timeout_cancels_children or tool_budget_and_concurrency_one"
```

先回答三句：一个 Semaphore 控制同时执行数量；一个 `Budget` 控制全局请求总数；`finally` 中 `cancel` 后还要等待清理。再去测试里找对应断言。

## 15. 最后按这条路线读源码

你已经知道每个数据代表什么，再按下面顺序看完整实现，比较不容易迷路：

| 顺序 | 入口 | 带着什么问题看 |
| --- | --- | --- |
| 1 | [cli.py](../src/docresearch/cli.py) `main` / `execute` | 用户参数怎样变成一次运行？ |
| 2 | [workspace.py](../src/docresearch/workspace.py) `Corpus` / `Source` | 原文、行号和版本如何保存？ |
| 3 | [stores.py](../src/docresearch/stores.py) `ingest` / `prepare` / `search` | ES/Milvus 如何持久化、核验和检索？ |
| 3a | [retrieval.py](../src/docresearch/retrieval.py) | 离线对照和 RRF 小函数如何工作？ |
| 3b | [agentic.py](../src/docresearch/agentic.py) `AgenticSearch` | 一次 search 为什么还要换问法、重排、判断缺口？ |
| 3c | [rerank.py](../src/docresearch/rerank.py) `DashScopeReranker` | 怎样把问题和候选正文交给专用重排服务？ |
| 4 | [models.py](../src/docresearch/models.py) `Search` / `Finding` / `Report` | 哪些输入会被拒绝？ |
| 5 | [provider.py](../src/docresearch/provider.py) `chat` / `embed` | HTTP 如何变成统一回复？ |
| 6 | [runtime.py](../src/docresearch/runtime.py) `loop` / `dispatch` / `child` | 动作如何执行、结果如何返回？ |
| 6a | [coordination.py](../src/docresearch/coordination.py) `Coordinator` | 哪项任务能开始？子结论如何登记并选入报告？ |
| 7 | 同文件 `Budget` / `run` / `render` | 何时停、如何定状态和生成报告？ |
| 8 | [workspace.py](../src/docresearch/workspace.py) `WorkFiles` / `ArtifactWriter` | 中途笔记和最终报告分别由谁写、写到哪里？ |
| 9 | [evaluation.py](../src/docresearch/evaluation.py) | 检索表现怎样被量化，而不冒充答案准确率？ |

源码不需要一次背完。先能用自己的话说清这段话，再去准备面试：

> 文件先变成带出处的快照。检索流程改写查询、融合召回、重排并判断证据，必要时补一次检索。主可直接读写工作文件，也可把复杂问题交给独立上下文与私有目录的子代理。子只回传限长结论，主需要时再核对原文；最后程序校验来源与结论登记表，保留缺口并统一生成报告。
