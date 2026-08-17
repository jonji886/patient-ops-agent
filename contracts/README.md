# API / Tool Contract 说明

本目录是 `docs/architecture.md` 所要求的 Contract Skeleton。业务范围和验收标准仍以 [`SPEC.md`](../SPEC.md) 为准。

## 文件职责

- `common.yaml`：共享错误、幂等、号源、预约和 Operation Result Schema；
- `agent-api.yaml`：患者 Command、Operator Command、Run View 和 Trace；
- `patient-ops-api.yaml`：Patient Context、Facts、Consent、NBA 和 AgentResult Writeback；
- `clinic-core-api.yaml`：Clinic、Service Item、Slot、Appointment 和 Reconciliation；
- `data/synthetic/fixtures.yaml`：仅用于测试和演示的虚构数据。

外部 `$ref` 以相对路径引用 `common.yaml`。实现阶段应使用同一组 Pydantic Model 生成或校验 HTTP Schema，不允许单独维护一套不一致的 DTO。

## 权限与执行策略

| 接口/Tool | 权限 | Timeout | Retry | 幂等 |
|---|---|---:|---|---|
| Patient Context / Facts 查询 | `READ` | 3s | 最多 3 次 | 不需要 |
| Slot 查询 | `READ` | 3s | 最多 3 次 | 不需要 |
| Agent `POST /messages` | `READ + WORKFLOW` | 30s | 不透明重试 | `X-Request-ID` |
| Clinic `POST /appointments` | `WRITE_HIGH_RISK` | 5s | 结果未知先对账 | `Idempotency-Key` 必须 |
| Clinic `POST /appointments/{id}/cancel` | `WRITE_HIGH_RISK` | 5s | 结果未知先对账 | `Idempotency-Key` 必须 |
| Patient Ops `POST /agent-results` | `WRITE_LOW_RISK` | 5s | Worker 最多 3 次 | `Idempotency-Key` 必须 |
| Notification | `WRITE_LOW_RISK` | 5s | Outbox 最多 3 次 | Event ID |
| Manual Task Resolve / Return | `HUMAN_ONLY` | 5s | 不自动重试 | `X-Request-ID` |

这些是 MVP 默认值，代码必须从 Settings 注入，测试可以缩短时间但不能改变语义。

## 写操作统一要求

所有写请求必须：

1. 通过服务端身份和权限校验；
2. 验证资源归属、参数和资源版本；
3. 在需要时验证 Patient Confirmation；
4. 生成或复用稳定 `operation_id`；
5. 保存 `request_hash`；
6. 返回 `outcome`：`NOT_EXECUTED`、`EXECUTED` 或 `UNKNOWN`；
7. 记录 ToolExecution 和 Audit；
8. 在 `UNKNOWN` 时禁止生成新的 Operation。

## Contract 测试最低要求

- 每个 endpoint 至少一个成功响应和一个错误响应；
- OpenAPI Schema 与实际 Pydantic 响应一致；
- 相同幂等键和请求体返回原业务结果；
- 相同幂等键但不同请求体返回 `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST`；
- 省略写请求的 `Idempotency-Key` 时返回 `400`；
- 过期或错误 `state_version` 返回 `STATE_VERSION_CONFLICT`；
- 外部服务不返回未校验的原始异常给 Agent Workflow。
