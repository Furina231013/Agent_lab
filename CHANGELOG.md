# Changelog

## v0.6.1

- 继续沿着“少量 prompt、更多代码校验”的方向收紧 ask 纠偏逻辑，新增 5 类更硬的验证：范围外问题不得从“未明示”跳成“明确不适用”、`420` 硬切题必须同时答出“段落优先 + 超长再切”、冲突处理题必须显式提示“结合来源进行确认”、例外项题的结论极性必须和依据一致、关键数字不得被串改
- 范围外适用题现在不仅会拦截“范围内规则外推为范围外适用”，也会拦截“明明写了未明示，却直接下结论说不适用”的过度判断
- 数字校验的纠偏提示现在更直接，会明确要求保留题目中的关键数字，不要把 `15` 改写成别的数字
- 新增 LM Studio 单元测试，锁住 `test-md-016/028/029/030/047` 这几类稳定残留错对应的校验与重试行为

## v0.6.0

- 继续沿着“少量 prompt、更多代码校验”的方向收紧 ask 纠偏逻辑，不再新增更长的题型提示
- 范围外适用题现在会明确拦截“把范围内规则直接外推成范围外结论”的答案，并识别“既说适用又说未明示”的自相矛盾
- 冲突处理题现在除了检查“保留冲突 / 提示不一致 / 禁止强行合并”，还会在来源要求固定提示语时，强制答案显式包含该提示语
- 数字校验现在会把 `3.3 / 4.3` 这类章节号从数值比较里剔除，避免把目录编号误报成真正的数字错误
- 新增 LM Studio 单元测试，锁住“范围外推”“冲突固定提示语”“章节号误报”这些刚刚识别出的稳定残留问题

## v0.5.8

- 延续“少量新增 prompt，更多把稳定约束变成代码校验”的策略，LM Studio 现在会额外识别 5 类稳定残留错误：并列映射题漏半边、范围外推、例外规则误判、关键数字被串改、冲突处理漏核心动作
- ask 返回后会用更具体的轻量校验去检查：是否同时覆盖 `Lookup/Explain` 两边、是否明确交代范围外是否已明示、是否命中了例外项、是否保留了题目关键数字、冲突处理是否同时覆盖“保留冲突/提示不一致/禁止强行合并”
- 纠偏重试仍然只保留 1 次，但现在更偏向程序化发现稳定错误，而不是继续把总 prompt 越写越长
- 新增 LM Studio 单元测试，直接锁住 `test-md-009/016/028/030/047` 这几类残留错误对应的校验与重试行为

## v0.5.7

- 继续收紧 `/api/ask` 的 LM Studio 提示词，新增题型级约束：会区分 `Lookup/Explain` 分类题、`会不会/是否` 判定题、`数量 + 条件` 双问句，以及“表达方式”题
- ask 现在会在本地模型答案返回后做一层轻量校验；如果发现“题型没答中”“结论与后文冲突”或“出现上下文里没有的数字”，会自动做一次纠偏重试
- 输出清洗层现在能把单行连写的 `结论/依据/边界` 自动拆回三行，减少本地模型把结构化答案挤成一行时的可读性和后处理问题
- 新增 LM Studio 单元测试，锁住题型提示、输出拆分和单次纠偏重试行为

## v0.5.6

- `python scripts/evaluate.py run` 现在默认只跑 `vector + direct_read`，不再默认带上 `keyword`，以减少完整评测耗时
- 评测服务仍保留 `keyword` 作为可选模式；如果你确实需要三路对比，可以手动传 `--modes keyword vector direct_read`
- 评测测试已同步锁住新的默认模式，避免后续默认配置悄悄回退

## v0.5.5

- 基于 `test-md` 评测里的生成错样本，收紧了 `/api/ask` 的 LM Studio 提示词，重点约束“不要把计划态写成现态”“不要外推未明示规则”“关键数值必须逐字复制”
- ask 现在要求本地模型按固定三行输出：`结论 / 依据 / 边界`，减少回答时的漏项、自相矛盾和边界丢失
- 新增输出清洗层，会移除 `<think>` / `Thinking Process` 等推理痕迹，只保留最终答案骨架
- LM Studio 请求现在默认使用更保守的生成参数，降低本地模型在事实问答里漂移和数值改写的概率
- 增加 LM Studio 单元测试，锁住新的 prompt 约束、输出清洗和 payload 参数

## v0.5.4

- 新增 `scripts/build_eval_dataset.py`，可以一键把 `data/raw/evaluatetest.md` 重新生成成 `data/evals/test_eval_set.json`
- 新增 `app/services/eval_dataset_builder.py`，把 markdown 解析和 JSON 生成逻辑单独收口，避免评测主流程直接依赖更脆弱的 markdown 结构
- 生成器现在按题目块解析，不再强依赖每一题之间都写了标准 `---` 分隔，因此对手工维护的题库更稳

## v0.5.3

- `data/evals/test_eval_set.json` 已同步到 `data/raw/evaluatetest.md` 的最新内容，默认评测集现在包含 50 条题
- 评测测试已改为检查 `test_eval_set.json` 与 `evaluatetest.md` 的题目数量一致，避免以后再次出现“markdown 已加题，但 JSON 还停留在旧数量”的不同步问题

## v0.5.2

- 新增默认评测集 `data/evals/test_eval_set.json`，将 `data/raw/evaluatetest.md` 中的 20 条问题转换成评测脚本可直接使用的 JSON
- `python scripts/evaluate.py run` 现在默认会对 `data/raw/test.md` 跑这 20 条评测题，不再默认指向旧的 `small_eval_set.json`
- `scripts/ingest_demo.py` 也已切换为默认读取 `data/raw/test.md`，让命令行演示和评测目标文档保持一致

## v0.5.1

- 将评测 `run.json` 精简成更适合人工标注的结构，只保留 `answer_preview`、`evidence` 和 `log_path`
- 完整回答与完整 chunk 继续保存在 ask 日志里，人工打标签时默认不必再翻大段原文
- 脚本提示和 README 已同步改为新的“先看预览，再按需打开 log”流程
- 将原本容易引起歧义的 `data/raw/embedding_demo.md` 重命名为 `data/raw/vector_demo.md`，并改成中文内容
- 评测集和测试已同步切换到 `vector_demo.md`，并新增测试确保评测集里的 `source_paths` 不会再指向缺失文件

## v0.5.0

- 新增最小人工评测闭环，支持用一份小评测集比较 `keyword`、`vector`、`direct_read` 三种模式
- 新增 `app/services/evaluator.py` 和 `scripts/evaluate.py`，让评测运行、结果落盘和报告汇总都有固定入口
- 每次评测会在隔离工作区重新 ingest 评测文档，避免污染日常 `data/processed/`
- 评测结果 JSON 里为每题、每种模式预留了 `manual_review`，方便人工标注 `correct / incorrect / insufficient` 和 `error_type`
- 新增 markdown 汇总报告，按模式统计标签分布和错误类型，并给出轻量的下一步建议
- 附带一份 24 条的小评测集 `data/evals/small_eval_set.json`

## v0.4.2

- 将默认 embedding 模型从 `sentence-transformers/all-MiniLM-L6-v2` 切换为更适合当前中文学习场景的 `BAAI/bge-small-zh-v1.5`
- 新增配置测试，锁住这个默认值，避免后续无意间退回到英文向 baseline
- README 补充模型切换后的重新 ingest 提醒，避免混用不同模型生成的向量

## v0.4.1

- 修复 `/api/ask` 在 `mode=vector` 下返回小数相似度时触发 schema 校验失败的问题
- `AskChunk.score` 现在与关键词检索和向量检索共用 `float` 类型，避免 ask 接口把合法的 cosine score 误判为错误输入
- 补强 ask 的向量模式测试，明确覆盖“小数分数也应返回 200”的场景

## v0.4.0

- 保留原有关键词检索作为 baseline，同时新增第一版 embedding 检索
- ingest 现在会为每个 chunk 生成 embedding，并和 chunk 一起保存到 `data/processed/` JSON 中
- 新增 `app/services/embedder.py`，集中负责 embedding 模型加载与向量生成
- `/api/search` 和 `/api/ask` 现在支持 `mode=keyword` / `mode=vector` 切换
- 新增向量检索测试与 embedder 测试，确保 embedding 生成和 cosine 排序行为可验证

## v0.3.3

- `/api/ask` 现在会把每次问答结果落成 JSON，方便离线查看本地模型的原始输出
- 新增 `ASK_LOG_DIR` 配置项，默认保存到 `data/index/ask_logs/`
- ask 响应新增 `output_path`，会直接告诉你这次结果保存到了哪里
- 增加 ask 落盘测试，覆盖 placeholder、生成成功和回退场景

## v0.3.2

- 修复 `/api/ask` 在本地 LM Studio 请求超时时直接返回 500 的问题
- 现在 `socket.timeout` 和超时错误会被转换成可回退的 `LMStudioError`，接口会继续返回检索结果和状态说明
- 新增 LM Studio 超时测试，锁住这个回退行为
- 将本地模型默认超时配置提高到 120 秒，减少首次生成或较慢机器上的误判

## v0.3.1

- `/api/ask` 现在预留了本地 LM Studio 模型接入点，但默认仍使用 placeholder 模式
- 新增 `.env` 配置项，可显式切换 `ASK_PROVIDER=lm_studio` 并指定本地模型名和服务地址
- ask 返回现在包含 `answer_mode`、`answer_status`、`answer_note`、`provider`、`model`，更容易判断当前是否真的走到了本地模型
- 增加 ask 的 TDD 测试，覆盖默认 placeholder、LM Studio 成功生成、以及本地服务未启动时的优雅回退

## v0.3.0

- 新增 `/api/ask`，但暂时不接真实模型
- ask 第一版只接收 `question`，调用现有 search 拿 `top_k` chunks
- ask 返回命中的 chunks、来源列表和一个占位的 `answer`
- 增加 `/api/ask` 的 API 测试，确保检索型问答链路先可用

## v0.2.5

- 修复 chunk 开头常被 overlap 截断的问题，新的 chunk 起点会尽量贴近完整句子的开头
- chunk 结束位置除了段落边界，也会优先尝试句子标点边界，减少上一段过早截断
- 增加复现该问题的 chunker 测试，确保后续不会退化回“半句开头”的行为

## v0.2.4

- 新增 `DEVELOPMENT.md`，把仓库的 TDD 开发约定整理成单独文档
- 新增项目级 `AGENTS.md`，要求进入仓库开发时先读取并遵守 `DEVELOPMENT.md`
- 约定以后默认采用“先写测试、先红灯、再实现、最后全绿”的开发流程

## v0.2.3

- 按 TDD 的红灯到绿灯流程补充 `/api/ingest` 和 `/api/search` 的端到端 API 测试
- ingest 现在支持优先按配置的 `raw_dir` 解析简化相对路径，便于隔离测试和切换数据目录
- README 补充新的 API 端到端测试与推荐开发流程说明

## v0.2.2

- 扩充 `data/raw/demo.pdf`，现在包含约 2000-3000 字级别的示例内容，适合更真实地练习导入与检索
- 优化 `/api/search` 返回结构，结果现在包含 `rank`、`match_count`、`match_term` 和 `preview`
- `total_hits` 现在表示全部命中数，新增 `returned_count` 表示当前实际返回条数
- 增加和更新搜索测试，确保排序、预览和空结果行为稳定

## v0.2.1

- 为 `/api/search` 增加自动化测试，覆盖命中、排序与空结果场景
- 补充可直接导入的本地示例文件 `data/raw/demo.pdf`
- README 同步更新，说明示例 PDF 的用途

## v0.2.0

- 新增 `.pdf` 读取支持，导入层现在支持 `.txt`、`.md`、`.pdf`
- 为空 PDF 或无法解析的 PDF 返回清晰错误，避免静默失败
- chunk 策略从“纯字符切分”升级为“按段落优先 + 长段再切”
- 保留 `overlap`，让 chunk 边界附近的信息仍然有重叠覆盖
- 更新 README，补充 PDF 支持与新的 chunk 设计说明
- 增加针对 PDF 读取和 chunk 策略的测试

## v0.1.0

- 初始化最小可运行的 FastAPI 学习项目骨架
- 支持导入本地 `.txt` 和 `.md` 文件
- 实现基础的文件读取、简单字符切块和 JSON 落盘
- 提供 `/api/health`、`/api/ingest`、`/api/search` 三个基础接口
- `/api/search` 使用最简单的关键词包含/计数打分
- 提供 README、命令行脚本和最小健康检查测试
