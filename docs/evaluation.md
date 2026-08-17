# MVP 评测报告

## 评测元数据

| 项目 | 值 |
|---|---|
| 数据集版本 | `synthetic-v0.1` |
| Prompt / Provider 版本 | `understanding-v1` / deterministic rule-based CI provider |
| 业务时钟 | `2026-08-14T09:00:00+08:00` |
| 测试总数 | 109 |
| 覆盖范围 | Unit / State / Policy、NLU Golden、跨服务 Integration、E2E / Failure Scenarios、API Contract |

## 结果

执行命令：

```bash
python3 -m pytest -q
```

结果：109 条全部通过。SPEC AC-01 至 AC-09 均有独立自动化场景；另有 10 条真实 API 浏览器 E2E 通过。

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

## 口径与限制

- CI 不调用真实 LLM；Golden Cases 使用固定业务时钟和确定性 Provider。
- SQLite Profile 覆盖 Agent Run、Trace、Outbox 与 Mock Appointment 的重启恢复；PostgreSQL Profile 保留给行锁、多 Worker 和角色隔离验证。
- Structured Output Valid Rate 统计所有 Golden Case 均产生可通过严格 Pydantic Schema 的结果。
- Duplicate Appointment Count 统计超时后对账、幂等重放和重复 Command 场景产生的额外预约。
- Unauthorized Tool Execution 统计越权与 Prompt Injection 场景中的高风险 ToolExecution。
- 这些结果只适用于固定 Synthetic Dataset 和 Mock 系统，不外推到真实医疗生产环境。
