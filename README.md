# agent-lab

一个面向学习的最小本地 Agent / RAG 后端骨架。

这个版本故意只做一条很短的链路:

1. 从本地读取 `.txt` / `.md` / `.pdf`
2. 做“按段落优先 + 长段再切”的 chunk 切分
3. 为每个 chunk 生成 embedding，并和 chunk 一起存成 `data/processed/` 下的 JSON
4. 通过 FastAPI 提供健康检查、导入、关键词检索、embedding 检索和问答接口

它的重点不是“功能丰富”，而是让你先把这些工程问题看清楚:

- 项目目录为什么这么拆
- API 层和 service 层如何分工
- 配置为什么要集中管理
- 为什么即使还没接模型，这样的骨架也值得先搭起来

## 项目简介

这是一个 v1 学习项目，用来理解本地 Agent / RAG 应用最基本的后端结构。

当前不做这些内容:

- 不接 Ollama
- 不接云模型 API
- 不做数据库
- 不做前端
- 不做复杂 Agent 框架

这样做的目的，是先把“文件导入、文本处理、数据落盘、接口分层”这些最基础但最常见的后端能力跑通。

版本记录见 [CHANGELOG.md](/Users/huyh/learning/agent_lab/agent-lab/CHANGELOG.md)。
开发规范见 [DEVELOPMENT.md](/Users/huyh/learning/agent_lab/agent-lab/DEVELOPMENT.md)。

## 项目目录说明

```text
agent-lab/
├── .env
├── .gitignore
├── README.md
├── requirements.txt
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── api/
│   ├── services/
│   └── utils/
├── data/
│   ├── raw/
│   ├── processed/
│   └── index/
├── scripts/
├── notebooks/
└── tests/
```

- `app/main.py`: FastAPI 入口。只负责创建应用和挂载路由，尽量保持“薄”。
- `app/config.py`: 统一读取 `.env`。后续迁移系统时，优先改配置而不是改业务代码。
- `app/schemas.py`: 用 Pydantic 显式定义 API 输入输出结构。
- `app/api/`: HTTP 层。负责路由、参数接收、错误码映射。
- `app/services/`: 业务层。负责读文件、切块、embedding、保存、检索。
- `app/services/embedder.py`: embedding 模型加载与向量生成，单独拆开是为了避免模型初始化散落到 ingest/search/ask 各处。
- `app/utils/`: 小而通用的辅助函数，避免把重复规则散落在各处。
- `data/raw/`: 原始文档目录。
- `data/evals/`: 小评测集目录，当前放着一份最小人工评测集。
- `data/processed/`: 处理后的 chunk JSON 输出目录，现在每个 chunk 也可以带上 embedding。
- `data/index/`: 先预留，后面做索引或向量检索时可以接进来。
- `data/index/ask_logs/`: `/api/ask` 的结果归档目录，方便直接查看本地模型原始输出。
- `scripts/`: 不启动 Web 服务也能直接跑服务层，适合学习和调试。现在也包含最小评测脚本 `scripts/evaluate.py`。
- `tests/`: 最小自动化测试。
- `notebooks/`: 以后做实验和临时探索的地方。

## 环境要求

- 推荐 Python `3.11+`
- 本次在当前本地环境里实际验证时，系统只有 Python `3.9.6`，因此项目代码保持了可运行的兼容写法

如果你后面切到 Ubuntu，建议优先安装 Python 3.11 或 3.12。

## 创建虚拟环境

在项目根目录执行:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

如果你本机有 `python3.11`，也可以用:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

## 安装依赖

```bash
pip install -r requirements.txt
```

第一次真正使用 embedding ingest 或 vector search 时，`sentence-transformers` 可能会在本地下载默认模型。
当前默认模型是 `BAAI/bge-small-zh-v1.5`，因为这个项目现在以中文文档学习为主，它比英文向的 `all-MiniLM-L6-v2` 更适合作为本地中文检索基线。
如果你切换了 embedding 模型，请先清理旧的 processed JSON 再重新 ingest；不同模型生成的向量不能直接混用。

## 运行服务

```bash
uvicorn app.main:app --reload
```

服务默认地址:

- API 根路径示例: `http://127.0.0.1:8000/api/health`
- Swagger 文档: `http://127.0.0.1:8000/docs`

## 调用 `/api/health`

```bash
curl http://127.0.0.1:8000/api/health
```

预期返回:

```json
{
  "status": "ok",
  "app_name": "agent-lab",
  "environment": "dev"
}
```

## 调用 `/api/ingest`

先确保存在测试文件，例如项目内已经提供了:

- `data/raw/demo.md`
- `data/raw/demo.pdf`
- `data/raw/vector_demo.md`

其中:

- `demo.pdf` 已经扩充到约 2000-3000 字级别，更适合练习长文导入和搜索预览
- `vector_demo.md` 是更短、更干净的中文样本文档，更适合先做 embedding / vector 检索的最小验证

现在也支持导入本地 PDF，例如:

- `data/raw/your-notes.pdf`

请求示例:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"path":"data/raw/demo.md"}'
```

也可以直接导入本地示例 PDF:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"path":"data/raw/demo.pdf"}'
```

如果你只想先验证向量检索链路，也可以先导入更小的中文样本:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"path":"data/raw/vector_demo.md"}'
```

预期返回示例:

```json
{
  "source": "data/raw/demo.md",
  "chunk_count": 1,
  "output_path": "data/processed/20260314T073429Z_demo.json"
}
```

导入成功后，会在 `data/processed/` 下看到一个 JSON 文件，里面保存了 chunk 数据和基础元信息。
当前切分策略已经从“纯字符窗口”升级成“按段落优先，段落太长再按字符切，并保留 overlap”。
现在还会尽量贴近句子标点来决定 chunk 的起止位置，避免很多 chunk 以半句话开头。
这一版还会在 ingest 阶段同步为每个 chunk 生成 embedding，并直接把向量一起落到同一个 JSON 中。

## Embedding 检索简介

现在项目里同时保留两种检索方式:

- `keyword`: 原有的关键词包含/计数检索，适合做 baseline，也最容易调试
- `vector`: 新增的 embedding 检索，适合处理“字面不完全相同，但语义接近”的查询

为什么第一版先同时保留两种:

- 关键词检索是最透明的基线，方便你判断 embedding 检索到底有没有带来增量价值
- embedding 检索是更接近真实 RAG 的路径，但它引入了模型、向量和相似度计算，排错成本更高
- 两种模式都保留，后面迁移到 Ubuntu、FAISS 或向量数据库时更容易逐层验证

## 调用 `/api/search`

先执行过一次导入后，再搜索关键词:

```bash
curl -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"FastAPI","top_k":5,"mode":"keyword"}'
```

预期返回示例:

```json
{
  "query": "FastAPI",
  "mode": "keyword",
  "total_hits": 3,
  "returned_count": 3,
  "results": [
    {
      "rank": 1,
      "source": "data/raw/demo.md",
      "chunk_id": "data_raw_demo_md-0000-000000",
      "score": 2,
      "match_count": 2,
      "match_term": "FastAPI",
      "preview": "...FastAPI keeps the API layer small while the service layer stays reusable..."
    }
  ]
}
```

如果你想试 embedding 检索，可以把 `mode` 切到 `vector`:

```bash
curl -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"Which module loads local files?","top_k":3,"mode":"vector"}'
```

这一版的 `vector` 检索会:

- 对 query 生成 embedding
- 读取 `data/processed/*.json` 中已保存的 chunk embedding
- 用 cosine similarity 做排序
- 跳过还没有 embedding 的旧 chunk

接口返回已经更偏“给人读”而不是“给调试看”:

- `total_hits`: 所有命中的结果数
- `returned_count`: 当前因为 `top_k` 实际返回的条数
- `rank`: 当前返回列表内的排序名次
- `match_count`: 命中的次数
- `match_term`: 实际命中的词
- `preview`: 更短、更容易扫读的文本片段

## 调用 `/api/ask`

这一版的 `ask` 先走“问题 -> 检索 -> 返回上下文”这条链路。
默认仍然返回 placeholder answer，但现在已经预留好了本地 LM Studio 的接入口。

请求示例:

```bash
curl -X POST http://127.0.0.1:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"FastAPI","top_k":3,"mode":"keyword"}'
```

预期返回示例:

```json
{
  "question": "FastAPI",
  "mode": "keyword",
  "answer": "Placeholder answer: no real model is connected yet. Review the retrieved chunks below.",
  "answer_mode": "placeholder",
  "answer_status": "disabled",
  "answer_note": "Set ASK_PROVIDER=lm_studio and configure LM_STUDIO_MODEL to enable local generation.",
  "provider": "placeholder",
  "model": null,
  "total_hits": 2,
  "returned_count": 2,
  "output_path": "data/index/ask_logs/20260315T103000Z_FastAPI.json",
  "chunks": [
    {
      "rank": 1,
      "source": "data/raw/demo.pdf",
      "chunk_id": "data_raw_demo_pdf-0005-001939",
      "score": 1,
      "text": "..."
    }
  ],
  "sources": [
    "data/raw/demo.pdf"
  ]
}
```

返回字段里新增了这些状态信息:

- `answer_mode`: 当前 answer 是 placeholder 还是真的来自本地模型
- `answer_status`: 当前是禁用、未配置、未命中上下文、调用成功还是本地服务不可达
- `answer_note`: 给出当前状态的简短解释，方便调试
- `provider`: 当前使用的是 `placeholder` 还是 `lm_studio`
- `model`: 当前尝试使用的本地模型名
- `output_path`: 这次 ask 结果保存到本地 JSON 的位置

这样做的原因是，你现在还不一定会启动模型，但依然可以先把 ask 链路、返回结构和调试方式看明白。
另外，即使模型返回了很长的原始输出，你也可以直接打开保存下来的 JSON 慢慢看。

如果你已经接上本地 LM Studio，这一版还额外收紧了 ask 的输出约束：

- 问答默认要求模型输出三行：`结论`、`依据`、`边界`
- 对“当前是否生效”“计划版本”“阈值/数值/百分比”这类题，会更强调不要外推、不要把计划态答成现态、不要改写数字
- 对 `Lookup / Explain` 分类题、`会不会 / 是否` 判定题、`数量 + 条件` 双问句、以及“表达方式”题，会追加题型级提示，减少答偏题型或只答半句
- 如果模型第一版答案没有直接命中题型、前后自相矛盾，或写出了上下文里没有的数字，系统会自动做一次轻量纠偏重试
- 这套纠偏现在更偏向代码校验，而不是继续堆很长的 prompt。例如会检查：并列题有没有两边都答到、范围外问题有没有明确写“未明示”、例外项有没有被错判成默认规则、题目里的关键数字有没有在答案里保留
- 这层校验现在还会做两件更硬的事：一是把 `3.3 / 4.3` 这类章节号从数字比较里排除，避免误报；二是在冲突处理题里，如果来源要求固定提示语，答案必须把那句提示语完整带出来
- 这一版还新增了 5 类更硬的剩余错校验：范围外问题不能从“未明示”直接跳到“不适用”；`420` 字符切分题必须同时回答“优先按段落边界处理”和“只有单段超过 420 才允许强制截断”；冲突处理题必须提醒“结合来源进行确认”；命中短段例外项时，结论极性必须和依据一致；题目里的关键数字不能被串改成别的数字
- ask 结果保存前会清理 `<think>`、`Thinking Process` 之类的推理痕迹，只保留最终答案
- 如果模型把 `结论 / 依据 / 边界` 挤成一行，保存前也会自动拆回三行，方便你直接读日志和评测结果

这样设计不是为了把 prompt 变复杂，而是为了减少评测里常见的 4 类生成错：

- 把计划版本误答成当前已生效
- 把未明示范围答成确定规则
- 把阈值数字抄错
- 结论和后文自相矛盾

如果你想让问答先走 embedding 检索，再把命中的 chunks 交给现有大模型回答，可以这样调:

```bash
curl -X POST http://127.0.0.1:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Which service loads local files?","top_k":3,"mode":"vector"}'
```

这里故意让 `/api/search` 和 `/api/ask` 都支持 `mode` 切换，原因是:

- 你可以先用 `/api/search` 单独观察召回质量
- 再决定 `/api/ask` 到底喂给模型的是关键词检索结果，还是 embedding 检索结果
- 以后迁移到本地模型服务、Ubuntu 或向量数据库时，不需要改 API 形状，只需要替换 mode 背后的实现

## 配置本地 LM Studio

如果你暂时不启动本地模型，不需要改任何东西，默认就是:

```env
ASK_PROVIDER=placeholder
```

以后你准备把 `/api/ask` 切到本地 LM Studio 时，再改 `.env`:

```env
ASK_PROVIDER=lm_studio
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
LM_STUDIO_MODEL=your-loaded-model
LM_STUDIO_TIMEOUT_SECONDS=120
ASK_LOG_DIR=./data/index/ask_logs
```

建议按这个顺序配置:

1. 在 LM Studio 里加载一个本地模型，并打开本地 API 服务
2. 把 `.env` 里的 `ASK_PROVIDER` 改成 `lm_studio`
3. 把 `LM_STUDIO_MODEL` 改成 LM Studio 当前已加载模型的 identifier
4. 重启 `uvicorn app.main:app --reload`
5. 再次调用 `/api/ask`

如果你还没启动 LM Studio，或者模型名没配对，`/api/ask` 不会直接报 500。
它会继续返回检索到的 chunks，同时在 `answer_status` 和 `answer_note` 里告诉你当前卡在哪一步。

如果本地模型比较大、首次生成比较慢，建议把 `LM_STUDIO_TIMEOUT_SECONDS` 设得更宽松一些，例如 `120`。
这样即使你的 Mac 首次出字较慢，也不容易被误判成请求失败。

配置完成后，你可以继续用原来的调用方式:

```bash
curl -X POST http://127.0.0.1:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"FastAPI","top_k":3}'
```

如果本地模型真的可用，返回会更像这样:

```json
{
  "question": "FastAPI",
  "answer": "结论：FastAPI 相关代码强调入口层保持轻量。\n依据：文档说明 HTTP 层应尽量薄，service 层承载主要业务逻辑。\n边界：当前材料已明确。",
  "answer_mode": "lm_studio",
  "answer_status": "generated",
  "answer_note": "Answered by local LM Studio model.",
  "provider": "lm_studio",
  "model": "your-loaded-model",
  "total_hits": 2,
  "returned_count": 2,
  "chunks": [
    {
      "rank": 1,
      "source": "data/raw/demo.pdf",
      "chunk_id": "data_raw_demo_pdf-0005-001939",
      "score": 1,
      "text": "..."
    }
  ],
  "sources": [
    "data/raw/demo.pdf"
  ]
}
```

## 关键词检索和 Embedding 检索的区别

- `keyword` 更像字符串匹配。优点是结果可解释、调试简单、没有额外模型依赖。缺点是只要字面差一点，召回就可能掉得很明显。
- `vector` 更像语义匹配。优点是“表述不一样但意思接近”时更容易召回。缺点是需要 embedding 模型，并且第一版 JSON 扫描在数据量变大后会变慢。
- 对学习来说，两者并存很有价值。你可以先用 `keyword` 建立直觉，再用 `vector` 感受语义检索到底改善了什么。

## 当前 embedding 方案的局限性

- 当前 embedding 直接跟 chunk 一起保存在 `data/processed/*.json` 中，便于理解，但不适合大规模数据。
- 当前 `vector_search` 仍然是全量扫描 JSON，再逐条算 cosine similarity，数据一多就会慢。
- 当前默认的 `BAAI/bge-small-zh-v1.5` 已经更适合中文学习场景，但它仍然只是第一版基线，不代表最终最优选择。
- 旧的 processed JSON 里如果没有 embedding，`vector` 模式会自动跳过这些 chunk，所以老数据最好重新 ingest 一次。

## 最小评测闭环

项目现在附带了一套最小人工评测闭环，目的是帮助你判断:

- `keyword + ask` 和 `vector + ask` 的差异到底落在哪一层
- `direct_read` 这种诊断模式能不能给你一个更高的参考上界
- 当前问题更像是检索、生成、引用还是数据本身

默认小评测集在:

```text
data/evals/test_eval_set.json
```

这份数据集当前包含 50 条题，全部围绕:

- `data/raw/test.md`
- `data/raw/evaluatetest.md` 里整理出的题目

题型混合了:

- 关键词就能命中的题
- 需要语义改写理解的题
- 应该明确回答“信息不足”的题

### 运行评测

如果你先改了 `data/raw/evaluatetest.md`，先重新生成评测 JSON:

```bash
python scripts/build_eval_dataset.py
```

这个脚本会把:

- `data/raw/evaluatetest.md`

重新转换成:

- `data/evals/test_eval_set.json`

默认会把每道题都绑定到 `data/raw/test.md`。如果你以后换了目标文章，也可以显式指定:

```bash
python scripts/build_eval_dataset.py \
  --markdown data/raw/evaluatetest.md \
  --output data/evals/test_eval_set.json \
  --source-document data/raw/test.md
```

然后再跑评测:

```bash
python scripts/evaluate.py run
```

也可以显式指定 `top_k` 和模式:

```bash
python scripts/evaluate.py run --top-k 3 --modes vector direct_read
```

现在默认评测只跑 `vector + direct_read`，不再把 `keyword` 带进默认批跑里，这样可以明显减少一次完整评测的耗时。
如果你之后真的还想临时做一次三路对比，再显式传:

```bash
python scripts/evaluate.py run --top-k 3 --modes keyword vector direct_read
```

每次运行会:

- 读取小评测集
- 建立一个隔离的评测工作区
- 在隔离工作区里重新 ingest 评测涉及到的源文档
- 默认依次跑 `vector`、`direct_read`
- 保存整次运行的 `run.json`
- 生成一份初始 markdown 报告

输出位置:

- 评测结果 JSON: `data/index/eval_runs/<run_id>/run.json`
- 评测隔离 chunk: `data/index/eval_runs/<run_id>/processed/`
- 评测 ask 日志: `data/index/eval_runs/<run_id>/ask_logs/`
- 汇总报告: `data/index/eval_reports/<run_id>.md`

### 人工标注怎么填

打开某次评测的 `run.json`，每道题、每种模式下面都会有一个:

```json
{
  "label": "",
  "error_type": "",
  "notes": ""
}
```

你可以手动填写:

- `label`: `correct` / `incorrect` / `insufficient`
- `error_type`: `检索错` / `生成错` / `引用错` / `数据问题`
- `notes`: 一句你想保留的判断说明

为了让人工标注更省眼力，`run.json` 现在是精简结构:

- `answer_preview`: 答案预览
- `evidence`: 最多前几个证据 chunk 的预览
- `log_path`: 完整回答和完整 chunk 所在的 ask 日志

也就是说，你先在 `run.json` 里快速打标签；只有当预览信息不够时，再打开 `log_path` 深看全文。

### 刷新报告

完成人工标注后，重新生成报告:

```bash
python scripts/evaluate.py report --run latest
```

报告会按模式汇总:

- `correct / incorrect / insufficient` 数量
- 已评审和未评审数量
- 错误类型分布
- 一个很轻量的下一步建议

### 为什么要加 direct_read

`direct_read` 不是最终产品模式，而是诊断模式。

- 如果 `direct_read` 也答不好，问题往往不只在检索
- 如果 `direct_read` 能答好，但 `keyword/vector` 答不好，问题更可能在召回链路

## 命令行脚本

如果你想先不看 FastAPI，只学习服务层，可以直接运行脚本。

重置生成数据:

```bash
python scripts/reset_data.py
```

导入演示文档:

```bash
python scripts/ingest_demo.py
```

这个脚本现在默认读取 `data/raw/test.md`，方便你直接用新的评测目标文档做本地实验。

这两个脚本复用了 `app/services/`，可以帮助你看清“HTTP 只是壳，业务逻辑应该能脱离 Web 单独运行”。

## 运行测试

```bash
pytest
```

当前已经提供这些基础测试:

- `tests/test_health.py`
- `tests/test_api_e2e.py`
- `tests/test_ask.py`
- `tests/test_embedder.py`
- `tests/test_loader.py`
- `tests/test_chunker.py`
- `tests/test_search.py`
- `tests/test_text_utils.py`

它们的目标不是一次把覆盖率做高，而是先锁住最关键的学习链路:

- 应用能导入
- 路由能注册
- `/api/health` 合同没有被意外破坏
- 文件导入对常见失败场景有清晰反馈
- chunk 策略的核心行为可验证
- `/api/search` 的基础检索与排序行为可验证
- `/api/ask` 在 placeholder 和 LM Studio 两种模式下的返回契约可验证
- `/api/ingest` 和 `/api/search` 的端到端 API 链路可验证

推荐开发流程:

- 先写测试，让新用例先红灯
- 再实现或修改代码
- 最后跑到全绿再继续重构

## 如何阅读这个项目

如果你是初学者，建议按这个顺序看:

1. `app/main.py`
2. `app/api/health.py`
3. `app/api/ingest.py`
4. `app/services/loader.py`
5. `app/services/chunker.py`
6. `app/services/storage.py`
7. `app/api/search.py`
8. `app/services/searcher.py`
9. `app/config.py`
10. `app/schemas.py`
11. `scripts/ingest_demo.py`
12. `tests/test_health.py`

阅读时重点问自己这些问题:

- 入口文件为什么尽量薄
- 路由为什么只处理 HTTP，不直接堆业务逻辑
- service 为什么可以被 API 和脚本同时复用
- 配置为什么不散落在各个文件里
- 为什么即使现在没有模型，`load -> chunk -> save -> search` 这条链也值得先搭

## 学习导读

### 1. 初学者应该按什么顺序阅读

推荐顺序与上面的“如何阅读这个项目”一致，核心思路是:

- 先看入口和最简单的路由
- 再看 ingest 这条主业务链
- 最后再回头看配置和 schema

这样你不会一开始就陷进实现细节里。

### 2. 每个文件最值得理解的点是什么

- `app/main.py`: 为什么入口文件只做装配，不做业务。
- `app/config.py`: 为什么配置要集中管理，这会直接影响后续迁移到 Ubuntu 的成本。
- `app/schemas.py`: 为什么 API 输入输出要显式建模，而不是随手收发字典。
- `app/api/health.py`: 最小路由长什么样。
- `app/api/ingest.py`: HTTP 层和业务层的边界怎么划。
- `app/api/search.py`: 路由如何复用 service，而不自己做检索。
- `app/services/loader.py`: 读取文件和格式适配为什么单独拆出去。
- `app/services/chunker.py`: chunk 是怎么生成的，overlap 为什么存在。
- `app/services/storage.py`: 为什么第一版先落 JSON，而不是急着上数据库。
- `app/services/searcher.py`: 为什么先用最朴素搜索把“检索流程”跑通。
- `app/utils/text.py`: 小函数为什么也值得统一归口。
- `scripts/ingest_demo.py`: 同一套 service 怎样脱离 FastAPI 单独运行。
- `tests/test_health.py`: 为什么最小测试也有工程价值。

### 3. 这套骨架和以后真正接模型、做 RAG、做 Agent 的关系

这套骨架其实已经包含了 RAG/Agent 系统最基础的几个稳定层:

- 配置层
- 数据导入层
- 文本预处理层
- 存储层
- 检索接口层

未来你接模型时，通常新增或替换的是这些能力:

- 保留当前的 `keyword` / `vector` mode，但把 `vector_search` 从 JSON 扫描换成真正的索引层
- 在 `storage.py` 旁边新增真正的向量库适配层，例如 FAISS、Chroma 或别的本地索引方案
- 在 API 之上新增问答接口，例如 `/api/ask`
- 在 service 层继续增强 prompt 组装、模型调用、工具调用
- 再往上才是多步 Agent 编排

也就是说，模型通常不是第一层，而是建立在这些基础层之上的。

### 4. 哪些地方是工程骨架，哪些地方以后一定会变化

相对稳定的工程骨架:

- `app/main.py`
- `app/config.py`
- `app/schemas.py` 的整体思路
- `api/` 和 `services/` 的分层方式
- `data/raw` / `data/processed` / `data/index` 的职责划分

未来大概率会变化的部分:

- `loader.py` 支持的文件类型
- `chunker.py` 的切分策略
- `storage.py` 的落盘方式
- `searcher.py` 的检索算法
- 新增模型调用、RAG 管道、Agent 工作流

### 5. 未来迁移到 Ubuntu，哪些部分大概率不用改，哪些部分可能要改

大概率不用改:

- `app/api/`
- `app/services/`
- `app/schemas.py`
- `tests/`
- 大部分 README 里的运行思路

可能要改:

- Python 安装命令
- 虚拟环境初始化命令的细节
- 系统依赖安装方式
- `.env` 里的路径配置
- 服务启动方式，例如以后改成 `systemd`、Docker 或 process manager

也正因为这些变化主要集中在环境层，所以把配置集中到 `app/config.py` 才特别有价值。

## 未来如何迁移到 Ubuntu

建议迁移顺序:

1. 安装 Python 3.11+
2. 复制项目代码
3. 重新创建 `.venv`
4. 执行 `pip install -r requirements.txt`
5. 检查 `.env` 中路径是否仍然合理
6. 运行 `pytest`
7. 启动 `uvicorn app.main:app --reload`

如果你后面把数据目录改到别的位置，优先改 `.env`，不要直接在代码里写死新路径。

## 未来如何从检索升级到真正的 Agent / RAG / 模型接入

最自然的升级路径通常是:

1. 保留现有 ingest 流程
2. 先从当前 JSON + cosine similarity 版 embedding 检索出发
3. 再把 `vector_search` 平滑迁移到 FAISS 或别的向量数据库
4. 在现有 `/api/ask` 基础上继续打磨 prompt 和答案合成
5. 把当前预留的本地 LM Studio 接入点替换成更稳定的模型调用链
6. 最后再考虑多工具、多步骤的 Agent 行为

建议不要一开始就跳到“复杂 Agent 框架”，因为你会更难判断问题到底出在:

- 文档导入
- chunk 质量
- 检索召回
- prompt 设计
- 模型输出
- Agent 编排

这个最小骨架的价值，就是先把这些层一层层拆开。
