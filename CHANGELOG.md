# Changelog

本项目变更记录。格式参考 [Keep a Changelog](https://keepachangelog.com/)。

## [0.2.0] - 2026-08-17

### Added

- **Recall 完整闭环**：基于确定性 `RecallEligibilityRule` 的患者召回资格判定
  - 新增 `domain/recall.py`：`RecallEligibilityRule` + `RecallStatus` + `RecallEligibilityResult`
  - 召回规则由确定性代码强制（距上次洗牙 ≥5 个月 + 触达许可 + 无未来预约），LLM 不参与
  - `AgentRun` 新增 `recall_status` 和 `next_best_action` 字段
  - 预约成功后回写 `recall_status=CONVERTED`，Writeback payload 包含召回状态
  - 患者可拒绝召回（`recall_status=DECLINED`），不继续自动推进
- **Real LLM Evaluation 框架**：独立于 CI 的真实模型评测
  - 30 条 Golden Dataset（`data/eval/llm_golden_cases.yaml`），覆盖 15 个类别
  - 评测脚本 `python3 -m patient_ops_agent.eval_runner`
  - 输出 JSON + Markdown 报告，不进入 CI，无 API Key 优雅退出
  - 指标：Intent Accuracy、Entity Accuracy、Structured Output Valid Rate、Fallback Rate、Latency P50/P95
- **Recall 测试**：8 条 Eligibility 单元测试 + 5 条场景测试
  - 覆盖 Case 1-7：Eligible、Not Yet Due、No Facts、Skip、Consent Denied、Decline、Handoff、Timeout

### Changed

- **README 重构**：增加 Failure Case 前置展示、Architecture Story（Why/What/How/Failure/Measure）、业务指标、Recall Demo、Real LLM Evaluation 说明
- **文档与代码 Drift 修复**：
  - `docs/architecture.md §20` 代码映射更新为真实代码结构（移除不存在的 `tools/`、`ports/`、`workers/`、`observability/` 等目录）
  - README 项目结构更新为真实目录（移除不存在的 `services/` 目录，Mock 实际在 `src/patient_ops_agent/mocks/`）
- **`docs/evaluation.md`**：增加两层评测体系说明、业务指标、Real LLM Evaluation 章节
- Follow-up 测试更新为验证完整 Recall 闭环（trace event 名称、`recall_status` 断言）

### Fixed

- 修复 `architecture.md §20` 描述了大量不存在的目录和文件的问题
- 修复 README 项目结构中引用了不存在的 `services/` 目录的问题

## [0.1.0] - 2026-08-14

### Added

- MVP 初始版本：创建预约、查询预约、取消预约、人工接管
- LangGraph 显式状态机 + Policy + 幂等 Tool Executor + Outbox
- 超时对账、号源竞争、重复请求防护
- Transactional Outbox 副作用隔离
- Human Handoff 执行权原子转移
- 109 条自动化测试（AC-01 至 AC-09）
- DeepSeek LLM Adapter + RuleBasedUnderstandingProvider
- React 前端：Patient Chat、Operator、Admin 工作台
- Follow-up 最小垂直切片（基于 `last_cleaning_date` 推荐洗牙复查）
