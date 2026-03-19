# AGENTS.md

`AGENTS.md` 是本仓库的精简宪法。
只放最硬、最稳定、最值得每次先看到的规则；细节流程放在
[DEVELOPMENT.md](/Users/huyh/learning/agent_lab/agent-lab/DEVELOPMENT.md)。

## Core Rules

- 先读 [DEVELOPMENT.md](/Users/huyh/learning/agent_lab/agent-lab/DEVELOPMENT.md)，再做代码改动。
- 区分两类工作：`deterministic code` 默认按 TDD；`LLM behavior` 默认按 eval-driven development。
- 保持分层清晰：API 层保持薄，业务逻辑放在 `app/services/`，配置放在 `.env` 和 `app/config.py`，输入输出通过 `app/schemas.py` 显式建模。
- 对稳定复现的系统性错误，优先增加代码校验、结构化约束和可回归测试；不要靠无限堆长 prompt 解决。
- 行为、接口或开发规则变化后，同步更新 `README.md`、`CHANGELOG.md`，必要时更新 [DEVELOPMENT.md](/Users/huyh/learning/agent_lab/agent-lab/DEVELOPMENT.md)。
- 如果一次任务同时涉及确定性逻辑和模型行为：确定性部分走 TDD，模型部分走评测集与人工复核。
- 如果必须偏离既定流程或无法完成验证，在工作总结里明确说明原因。
