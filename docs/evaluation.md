# 评测报告

## 评测分层

项目采用两层评测体系：

```
Deterministic CI = 验证系统工程逻辑正确（不依赖网络和模型，进入 CI）
Real LLM Evaluation = 测量真实模型能力和不稳定性（需要 API Key，不进入 CI）
```

---

## 一、Deterministic CI 评测

### 评测元数据

| 项目 | 值 |
|---|---|
| 数据集版本 | `llm-golden-v0.1`（真实 LLM） / `synthetic-v0.1`（CI） |
| Prompt / Provider 版本 | `understanding-v1` / deterministic rule-based CI provider |
| 业务时钟 | `2026-08-14T09:00:00+08:00` |
| 测试总数 | 126 |
| 覆盖范围 | Unit / State / Policy / Recall Eligibility、NLU Golden、跨服务 Integration、E2E / Failure Scenarios、API Contract |

### 执行命令

```bash
python3 -m pytest -q
```

结果：126 条全部通过。SPEC AC-01 至 AC-09 均有独立自动化场景；另有 13 条 Recall 单元+场景测试和 13 条真实 API 浏览器 E2E。

### 结果

| 指标 | 结果 | 目标 |
|---|---:|---:|
| Structured Output Valid Rate | 100% | >=99% |
| Intent Accuracy | 100%（30/30） | >=95% |
| Happy-path Appointment Completion | 100% | >=95% |
| Duplicate Appointment Count | 0 | 0 |
| High-risk Confirmation Compliance | 100% | 100% |
| Unauthorized Tool Execution | 0 | 0 |
| Idempotency / Reconciliation Pass Rate | 100% | 100% |
| Deterministic State Transition Pass Rate | 100% | 100% |
| Recall Conversion Rate | 100% | >=95% |

### 业务指标

| 指标 | 结果 | 说明 |
|---|---:|---|
| Task Completion Rate | 100% | 正常路径预约全流程可走通 |
| Appointment Success Rate | 100% | 创建的预约全部核验为 CONFIRMED |
| Duplicate Appointment Rate | 0% | 超时、重复请求均不产生重复预约 |
| Human Handoff Rate | 按场景触发 | 高风险场景自动转人工 |
| Tool Failure Rate | 0%（正常路径） | 写操作全部成功核验 |
| Reconciliation Success Rate | 100% | 超时后对账全部恢复原结果 |
| Recall Conversion Rate | 100% | 满足召回条件的患者完成预约后 `recall_status=CONVERTED` |

### 口径与限制

- CI 不调用真实 LLM；Golden Cases 使用固定业务时钟和确定性 Provider。
- SQLite Profile 覆盖 Agent Run、Trace、Outbox 与 Mock Appointment 的重启恢复；PostgreSQL Profile 保留给行锁、多 Worker 和角色隔离验证。
- Structured Output Valid Rate 统计所有 Golden Case 均产生可通过严格 Pydantic Schema 的结果。
- Duplicate Appointment Count 统计超时后对账、幂等重放和重复 Command 场景产生的额外预约。
- Unauthorized Tool Execution 统计越权与 Prompt Injection 场景中的高风险 ToolExecution。
- Recall Conversion Rate 统计满足召回条件的患者沿既有预约管线完成预约后 `recall_status` 变为 `CONVERTED` 的比例。
- 这些结果只适用于固定 Synthetic Dataset 和 Mock 系统，不外推到真实医疗生产环境。

---

## 二、Real LLM Evaluation

### 目的

测量真实 LLM Provider（如 DeepSeek）的意图理解和实体抽取能力。与 CI 确定性测试分离，不进入普通 CI，无 API Key 时不会导致项目测试失败。

### 运行方式

```bash
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=your-key
export DEEPSEEK_MODEL=deepseek-chat

patient-ops-eval-real
# 等价于：python3 -m patient_ops_agent.eval_runner
```

### 数据集

30 条 Golden Cases（[`data/eval/llm_golden_cases.yaml`](../data/eval/llm_golden_cases.yaml)），覆盖：

| 类别 | 用例数 | 说明 |
|---|---:|---|
| happy_path | 5 | 正常创建预约 |
| ambiguous | 3 | 信息不足与歧义 |
| query | 2 | 查询预约 |
| cancel | 2 | 取消预约 |
| cancel_run | 1 | 取消当前流程 |
| human | 2 | 请求人工 |
| recall | 2 | 召回/随访 |
| alternative_slots | 1 | 替代号源查询 |
| invalid | 2 | 无关输入 |
| prompt_injection | 2 | Prompt Injection 对抗 |
| field_change | 2 | 多轮字段修改 |
| period_variant | 2 | 时段变体 |
| clinic_specified | 1 | 诊所指定 |
| date_format | 2 | 日期格式变体 |
| boundary | 1 | 边界：空意图 |

### 评测指标

| 指标 | 说明 |
|---|---|
| Intent Accuracy | 意图识别准确率 |
| Entity Service Accuracy | 服务项目抽取准确率 |
| Entity Date Accuracy | 日期解析准确率 |
| Entity Period Accuracy | 时段解析准确率 |
| Structured Output Valid Rate | JSON Output + Pydantic 校验后的有效比例 |
| Fallback Rate | UNKNOWN 意图比例（过高说明模型无法理解） |
| Latency P50 / P95 | 中位和 P95 延迟 |
| 按类别分类准确率 | 每个类别的准确率 |

### 输出

- JSON 报告（机器可读）：`reports/eval_<timestamp>.json`
- Markdown 报告（人类可读）：`reports/eval_<timestamp>.md`
- 最新 Snapshot：`reports/real-llm-eval-latest.md` / `.json`

### 最近一次真实 Snapshot

最近一次实际运行使用 `.env` 中的 DeepSeek Credential，模型为 `deepseek-chat`，数据集版本为 `llm-golden-v0.1`，生成时间为 `2026-08-20 15:35:42 (+08:00)`：

| 指标 | 结果 |
|---|---:|
| Intent Accuracy | 63.3%（19/30） |
| Entity Service Accuracy | 80.0% |
| Entity Date Accuracy | 80.0% |
| Entity Period Accuracy | 86.7% |
| Structured Output Valid Rate | 86.7% |
| Fallback Rate（UNKNOWN） | 0.0% |
| Latency P50 / P95 | 1507.5 ms / 2231.8 ms |

完整报告见 [`reports/real-llm-eval-latest.md`](../reports/real-llm-eval-latest.md)；该结果是一次真实模型观测，不代表稳定上限。Bad Cases 主要集中在歧义、召回、无效输入、边界输入和部分 Prompt Injection 结构化输出。

### 口径与限制

- 评测调用真实 LLM API，结果受模型版本、网络和 Prompt 影响而波动。
- 评测不进入 CI；无 API Key 时优雅退出，不影响项目测试。
- 意图准确率衡量模型对中文医疗预约场景的理解能力。
- 结构化输出有效率衡量 JSON Output + Pydantic 校验后的有效比例。
- 这些结果不外推到真实医疗生产环境。
- 评测数据集可版本管理，Prompt 或模型变化时应重新运行。
- 最新 Snapshot 必须由真实模型运行生成；deterministic Provider 的结果不能冒充真实模型评测。
