# Changelog

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
