# Implementation Summary

本轮目标是把现有 Patient Ops Agent 打磨成更适合 AI FDE / AI 应用交付工程师面试演示的作品集项目；没有引入 Multi-Agent、RAG、Redis、Kubernetes 或真实医疗系统接入。

## 1. 修改内容

- 新增 `DemoScenarioController` 与 `FailureInjector`，统一管理 one-shot 场景：`COMMIT_TIMEOUT`、`TOOL_FAILURE_HANDOFF`、`NOTIFICATION_FAILURE`、`SLOT_CONFLICT`、`POLICY_BLOCK`。
- Clinic Core Mock 和 Notification Sender 在 Infrastructure 边界消费故障；默认 Scenario 为 `NONE`，消费后自动 reset，不改变 Agent Workflow 的正常决策逻辑。
- 新增受 Patient Actor 保护的 `GET/POST /api/v1/demo/scenario`；仅在 `ENABLE_DEMO_SCENARIOS=true` 且非 production profile 时可用。
- 患者工作台新增 Demo Scenarios 面板和 Run Trace Timeline。页面结果来自服务端 Run / Trace，不在前端硬编码最终业务状态。
- 新增 4 条 Scenario Integration Tests，覆盖对账、人工接管、通知失败和 Policy Block。
- Real LLM Evaluation runner 增加 dataset version、业务时钟上下文、实体 Bad Case 展示，并生成时间戳报告与 `real-llm-eval-latest.*` 快照入口。
- 新增 `docs/delivery-playbook.md`，覆盖 Customer Discovery、System Discovery、Domain Mapping、Tool Contract、Adapter、POC、UAT、Rollout、Monitoring 与 Rollback。
- README、Architecture、UI Spec、Evaluation 文档和 Agent OpenAPI Contract 已同步。

## 2. Demo 使用方式

```bash
cp .env.example .env
# 确认 ENABLE_DEMO_SCENARIOS=true
patient-ops-agent
```

打开患者工作台，在 `Demo Scenarios` 中选择场景，之后按正常预约流程操作。重点场景：

- `COMMIT_TIMEOUT`：`UNKNOWN → Reconciliation → SUCCESS`，预约数量仍为 1；
- `TOOL_FAILURE_HANDOFF`：连续失败后 `execution_owner: AGENT → OPERATOR`，后续 Agent 写操作停止；
- `NOTIFICATION_FAILURE`：预约业务保持 `SUCCEEDED`，通知最终进入 `FAILED_NEEDS_HUMAN`；
- `POLICY_BLOCK`：真实越权消息经过既有 Policy 路径，产生 `policy_denied` 且没有写 Tool Execution。

## 3. 验证结果

- `python3 -m pytest -q`：126 条通过；
- `python3 -m pytest -q tests/scenarios/test_demo_scenarios.py`：4 条通过；
- `npm run build`（`web/`）：通过；
- 新增 Trace 后的关键浏览器 E2E（预约查询详情、引导式预约）：分别通过；完整既有 E2E 套件中另有 1 条跨测试共享 SQLite 号源的隔离问题，单独运行该用例通过；
- Contracts YAML 解析：通过；
- `git diff --check`：通过；
- 使用 `.env` 中的 DeepSeek Credential，显式设置 `LLM_PROVIDER=deepseek`、`DEEPSEEK_MODEL=deepseek-chat` 后运行真实评测：成功生成报告；未输出或提交任何 Secret。

## 4. Real LLM Evaluation

运行方式：

```bash
export LLM_PROVIDER=deepseek
set -a; . ./.env; set +a
export DEEPSEEK_MODEL=deepseek-chat
python3 -m patient_ops_agent.eval_runner --output reports
```

本次真实 Snapshot：`deepseek-chat`、数据集 `llm-golden-v0.1`、30 条 Golden Cases，生成于 `2026-08-20 15:35:42 (+08:00)`。

| 指标 | 结果 |
|---|---:|
| Intent Accuracy | 63.3%（19/30） |
| Entity Service Accuracy | 80.0% |
| Entity Date Accuracy | 80.0% |
| Entity Period Accuracy | 86.7% |
| Structured Output Valid Rate | 86.7% |
| Fallback Rate（UNKNOWN） | 0.0% |
| Latency P50 / P95 | 1507.5 ms / 2231.8 ms |

报告文件：[`reports/real-llm-eval-latest.md`](reports/real-llm-eval-latest.md)、[`reports/real-llm-eval-latest.json`](reports/real-llm-eval-latest.json)。Bad Cases 主要集中在歧义、召回、无效输入、边界输入和部分 Prompt Injection 结构化输出；该结果是真实模型快照，不将确定性 CI 结果冒充为模型准确率。

## 5. 未完成项

本轮明确验收项均已完成：Demo Scenarios、Real LLM Evaluation Snapshot、FDE Delivery Playbook，以及对应代码、测试、契约和文档均已验证。完整既有浏览器 E2E 套件仍暴露 1 条跨测试共享 SQLite 号源的隔离问题；该用例单独在新数据目录运行通过，属于测试隔离待治理项，不影响本轮功能验收。
