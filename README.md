# agent-lab

一个面向学习的最小本地 Agent / RAG 后端骨架。

这个版本故意只做一条很短的链路:

1. 从本地读取 `.txt` / `.md` / `.pdf`
2. 做“按段落优先 + 长段再切”的 chunk 切分
3. 把 chunks 存成 `data/processed/` 下的 JSON
4. 通过 FastAPI 提供最基础的健康检查、导入、检索接口

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
- `app/services/`: 业务层。负责读文件、切块、保存、检索。
- `app/utils/`: 小而通用的辅助函数，避免把重复规则散落在各处。
- `data/raw/`: 原始文档目录。
- `data/processed/`: 处理后的 chunk JSON 输出目录。
- `data/index/`: 先预留，后面做索引或向量检索时可以接进来。
- `scripts/`: 不启动 Web 服务也能直接跑服务层，适合学习和调试。
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

其中 `demo.pdf` 已经扩充到约 2000-3000 字级别，更适合练习长文导入和搜索预览。

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

## 调用 `/api/search`

先执行过一次导入后，再搜索关键词:

```bash
curl -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"FastAPI","top_k":5}'
```

预期返回示例:

```json
{
  "query": "FastAPI",
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

这个版本的检索仍然很朴素，只做关键词包含和简单计数打分。
但接口返回已经更偏“给人读”而不是“给调试看”:

- `total_hits`: 所有命中的结果数
- `returned_count`: 当前因为 `top_k` 实际返回的条数
- `rank`: 当前返回列表内的排序名次
- `match_count`: 命中的次数
- `match_term`: 实际命中的词
- `preview`: 更短、更容易扫读的文本片段

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

这两个脚本复用了 `app/services/`，可以帮助你看清“HTTP 只是壳，业务逻辑应该能脱离 Web 单独运行”。

## 运行测试

```bash
pytest
```

当前已经提供这些基础测试:

- `tests/test_health.py`
- `tests/test_api_e2e.py`
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

- 把 `searcher.py` 的关键词检索换成 embedding + 向量检索
- 在 `storage.py` 旁边新增真正的索引层或向量库适配层
- 在 API 之上新增问答接口，例如 `/api/ask`
- 在 service 层新增 prompt 组装、模型调用、工具调用
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
2. 把 `searcher.py` 升级成 embedding 检索
3. 增加一个问答 service，把“问题 + 检索结果”拼成 prompt
4. 再接入本地模型或云模型
5. 最后再考虑多工具、多步骤的 Agent 行为

建议不要一开始就跳到“复杂 Agent 框架”，因为你会更难判断问题到底出在:

- 文档导入
- chunk 质量
- 检索召回
- prompt 设计
- 模型输出
- Agent 编排

这个最小骨架的价值，就是先把这些层一层层拆开。
