# FDE Delivery Playbook：从 Mock Clinic Core 到客户现场

这份 Playbook 描述如何把当前 Demo 交付到客户真实的 HIS、CRM 或预约系统。重点不是把 Agent 重新写一遍，而是先确认业务目标、系统事实和失败语义，再用 Port / Adapter 替换外部系统边界。

## 1. Customer Discovery

第一步不是写 Prompt，而是和业务、运营、客服及系统负责人确认：

- 业务目标、当前 SOP、关键角色和人工节点；
- 系统边界、数据来源、可自动化范围和高风险操作；
- 验收标准、异常升级规则和必须保留的 Audit；
- 哪些动作需要患者确认，哪些动作必须由人工完成。

以本项目为例，目标是减少预约确认的人工处理；用户包括患者、客服和医护运营；核心系统是 CRM、Appointment System 和 Notification System；创建、修改、取消预约属于高风险写操作，最终预约确认需要患者显式确认。

## 2. System Discovery

拿到 API 文档后，仍要在 Sandbox 中逐项确认：

| 维度 | 现场要确认的问题 |
|---|---|
| System / API | 哪个系统是业务事实来源？读写边界是什么？ |
| Authentication / Permission | API Key、OAuth 还是 Service Account？权限按角色还是患者范围隔离？ |
| Timeout / Retry | HTTP 200 是否代表业务成功？超时后是否可能已经 Commit？ |
| Idempotency | 是否支持幂等 Key？Key 的作用域、保存时长和复用规则是什么？ |
| Consistency | 是否存在 Eventual Consistency？Commit 后多久可以查询到结果？ |
| Error / Rate Limit | 错误码、可重试语义、限流和 SLA 如何定义？ |
| Webhook / Audit | 是否有结果回调、操作审计和 External ID 查询能力？ |

如果不能通过 `operation_id`、External ID 或业务查询确认超时结果，就不能把 Retry 设计成盲目重试 Create；应先进入 UNKNOWN / Reconciliation 或强制人工接管。

## 3. Domain Mapping

Agent 内部 Domain Model 不直接依赖客户 API DTO。先建立可评审的 Mapping：

| Agent Domain | Customer System | Mapping |
|---|---|---|
| `patient_id` | `customer_id` | ID Mapping |
| `mobile` | `phone` | Normalize |
| `appointment_id` | `booking_id` | ID Mapping |
| `appointment_status` | `booking_status` | Enum Mapping |
| `recall_status` | `followup_status` | Enum Mapping |

```text
Agent Domain
    ↓
Port
    ↓
Customer Adapter
    ↓
HIS / CRM / Appointment System
```

Adapter 负责 DTO 转换、认证注入、超时和错误码映射；Workflow 继续依赖稳定的 Port，不因客户系统换供应商而重写。

## 4. Tool Contract

每个 Tool 在接入前形成一份可测试契约，至少包括：Input Schema、Output Schema、Timeout、Retry、Idempotency、Permission、Side Effect、Confirmation Requirement、Failure Semantics 和 Audit。

例如 `create_appointment`：

| 属性 | 约束 |
|---|---|
| Tool 类型 | Write Tool |
| Side Effect | YES |
| Confirmation | REQUIRED |
| Idempotency | REQUIRED，复用同一 `operation_id` |
| Permission | 当前患者范围 + 资源归属校验 |
| Failure | `NOT_EXECUTED` 可按策略重试；`UNKNOWN` 先对账 |
| Audit | 记录 Tool、Operation、结果和脱敏输入 |

## 5. Adapter Integration

交付顺序建议是：

1. 先接客户 Sandbox 的只读查询，验证身份、患者范围、号源和状态枚举；
2. 以一个写 Tool 建立 Port / Adapter，并录制真实错误码与超时行为；
3. 验证幂等重放、Commit 后响应丢失、并发冲突和 Eventual Consistency；
4. 再接 Notification 和运营回写，并保持它们与核心预约结果分离；
5. 把真实接口封装在 Adapter 中，不把客户 DTO、Token 或 Retry 规则散落到 Agent。

当前项目中的 `Mock Clinic Core` 就是这个边界的替身，Agent Workflow 无需知道它是 Mock 还是客户系统。

## 6. Security & Permission

真实集成至少确认 API Key / OAuth / Service Account 的保管方式、Role Permission、Patient Scope、Audit 和 Secret Rotation。权限由确定性 Policy 和服务端校验强制，不能只依赖 LLM 指令或 Prompt。

高风险动作遵循：

```text
Validation → Permission → Policy → Confirmation → Execution → Audit
```

## 7. POC 与 Evaluation

POC 只选一个高价值、边界清楚的场景：接真实 Sandbox、建立 20～50 条 Golden Cases、验证核心 Tool、人工确认和失败路径，并定义业务指标。评测分两层：

- Deterministic Regression：验证状态机、Policy、Tool Contract、幂等、对账和 Handoff；
- Real LLM Evaluation：验证真实模型的 Intent、Entity、Structured Output、Fallback 和 Latency。

## 8. UAT

UAT 不只是“页面能不能点击”，而是可复用的业务场景验收：

```text
Happy Path
Business Error
Commit Timeout
Duplicate Request
Permission / Policy Block
Human Handoff
Notification Failure
Reconciliation / Recovery
```

本项目的 Demo Scenario 同时可以作为 UAT Scenario 和 Regression Scenario，减少交付资产重复建设。

## 9. Rollout 与 Change Management

高风险写操作建议沿以下阶段推进：

```text
Shadow → Pilot → Limited Users → Gradual Rollout
```

先上线 `AI Recommend → Human Confirm`，通过真实数据验证成功率、Unknown Outcome、Handoff 和重复防护，再逐步扩大自动执行范围。Prompt、Model、Tool Contract 或外部 API 变更都要关联 Golden Cases、UAT 结果和回滚方案。

## 10. Monitoring 与 Rollback

最小可用监控应覆盖：

- Agent Task Success Rate；
- Tool Failure Rate；
- UNKNOWN Outcome Rate；
- Human Handoff Rate；
- Fallback Rate；
- P95 Latency；
- Duplicate Prevention；
- Notification Failure。

上线前明确三条可执行的止损路径：Feature Flag 关闭写 Tool、强制所有高风险任务转人工、切换到既有人工 / Fallback Workflow。Rollback 不应删除已经成功的业务事实，也不能通过补偿操作制造第二笔预约。
