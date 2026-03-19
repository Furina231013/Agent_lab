# Development Guide

这个文件定义 `agent-lab` 的日常开发约定。

目标不是增加流程负担，而是让每次改动都更可解释、更可回归、更适合学习。

## Core Rule

本仓库默认区分两类开发:

1. `deterministic code`
2. `LLM behavior`

前者默认采用 TDD；后者默认采用 eval-driven development。

不要把所有工作都机械地套进 TDD。对确定性逻辑，TDD 能有效防回归；对本地模型回答质量、prompt 调整和检索问答表现，评测集与人工复核比“证明 mock 输出会被规则拦住”更重要。

## Deterministic Code: TDD

`deterministic code` 包括这类内容:

- loader / chunker / searcher / storage / schema / config
- API 输入输出、错误映射、状态码
- 纯文本处理、路径处理、校验逻辑
- 明确、可重复、输入输出稳定的 service 行为

这类改动默认采用 TDD:

1. 先写测试
2. 先看到红灯
3. 再写或修改实现
4. 最后跑到绿灯

如果没有先经历红灯，就不算完成了这轮 TDD。

## LLM Behavior: Eval-Driven Development

`LLM behavior` 包括这类内容:

- prompt 调整
- 本地模型回答风格
- `vector` / `direct_read` 回答质量
- 检索问答链路在真实题集上的表现

这类改动默认采用评测驱动，而不是强行把每个现象都写成 mock 单元测试。

推荐顺序:

1. 明确想改善的错误类型或题集样本
2. 运行评测脚本，生成新的 `run.json`
3. 做人工复核，确认问题是否稳定复现
4. 只把稳定、可程序化的错误下沉成代码校验或小型测试
5. 再跑评测，对比前后结果

判断一条 LLM 改动是否完成，优先看:

- 评测集结果是否改善
- 人工标注后的错题是否减少
- 剩余错误是否变得更集中、更可解释

## Required Workflow

每次开发默认遵循下面的顺序:

1. 明确这次改动要验证的行为
2. 判断它属于 `deterministic code` 还是 `LLM behavior`
3. `deterministic code`：先添加或修改测试，让测试表达这个行为
4. `deterministic code`：在不改实现的情况下先运行测试，确认失败
5. 再修改实现代码或评测相关逻辑
6. `deterministic code`：先回跑刚才失败的测试
7. 如果涉及模型行为，运行评测并做人工复核
8. 再跑全量测试
9. 如果需要，再做小幅重构
10. 重构后再次确保相关验证仍然有效

## Red-Green-Refactor

### Red

红灯阶段要求:

- 测试必须先于实现改动出现
- 失败原因要和目标行为直接相关
- 不要为了让测试更容易通过而弱化断言

### Green

绿灯阶段要求:

- 只做让测试通过所需的最小实现
- 优先修正真实设计问题，不要用临时绕过掩盖问题
- 新实现要和当前目录分层保持一致

### Refactor

重构阶段要求:

- 只能在已有测试为绿灯的前提下进行
- 重构不应改变外部行为
- 重构后必须再次运行相关测试和全量测试

## Testing Rules

默认要求:

- 新功能必须先有测试
- 修 bug 必须先补能复现 bug 的测试
- API 改动优先补端到端或路由级测试
- service 逻辑改动优先补 service 测试
- 文本处理、路径处理、边界条件优先补小而准的单元测试
- prompt / 回答质量 / 本地模型表现改动，默认先跑评测，不要求为每一道题都补 mock 单元测试
- 只有当某类 LLM 错误稳定复现且可程序化约束时，才值得补单元测试锁住

测试通过不代表可以省略人工检查，但没有测试的功能默认不算完成。

## Test Scope Guide

不同层的测试放置建议:

- `tests/test_health.py`: 最小健康检查
- `tests/test_api_e2e.py`: 走完整 HTTP 链路的端到端 API 测试
- `tests/test_loader.py`: 文件读取与格式支持
- `tests/test_chunker.py`: chunk 策略与 overlap
- `tests/test_search.py`: 搜索排序、返回结构、空结果
- `tests/test_text_utils.py`: 文本归一化和小型边界规则

新增测试时，优先放到最接近行为发生位置的测试文件里。
如果现有文件不合适，再新建新的测试文件。

## What Counts As Done

一次开发任务默认只有在下面条件都满足时才算完成:

- `deterministic code` 的新行为已经被测试表达
- `deterministic code` 的测试先红过
- 相关测试已经转绿
- 如果涉及 LLM behavior，已经完成至少一轮评测与人工复核
- 全量测试为绿灯
- 必要的 README / CHANGELOG / 开发文档已经同步

如果其中任何一项缺失，任务应视为未完全完成。

## Commands

常用命令:

```bash
source .venv/bin/activate
pytest
pytest tests/test_api_e2e.py
pytest tests/test_search.py
python scripts/evaluate.py run
```

开发 API 时常用:

```bash
uvicorn app.main:app --reload
```

## Design Constraints

写代码时继续遵守这些约定:

- 入口文件保持薄
- API 层只处理路由、请求参数、状态码和错误映射
- 业务逻辑放在 `app/services/`
- 配置统一放在 `.env` 和 `app/config.py`
- 数据结构通过 `app/schemas.py` 显式建模
- 优先选择简单、透明、方便调试的实现

## Change Notes

下面这些场景通常需要同步更新文档:

- API 输入输出结构变化
- 支持的文件类型变化
- chunk 策略变化
- 搜索结果结构变化
- 新增测试策略或开发流程约定

至少优先检查:

- `README.md`
- `CHANGELOG.md`
- 本文件 `DEVELOPMENT.md`

## Collaboration Note

以后在这个仓库里开发时，默认先读取本文件并按这里的规则执行。

如果遇到必须偏离 TDD 的情况，需要先明确说明原因，例如:

- 纯文档改动
- 仅重命名且行为不变
- 上游依赖或环境问题阻塞测试运行

即便如此，也应该尽量补回测试或说明为什么这次无法补。
