# AGENTS.md

> 通用 AI Coding 协作规范  
> 目标：让 AI 在明确需求和稳定边界内高效开发，确保变更可控、可验证、可维护。  
> 原则：**产品优先 · 规格驱动 · 小步修改 · 风险优先 · 验证后完成**

---

## 1. 核心原则

- 所有文档输出中文优先。
- **产品优先**：先理解问题、用户和业务价值，再写代码。
- **规格文档驱动**：以明确需求、`SPEC.md` 和稳定契约为准。
- **先设计后编码**：复杂或高风险功能先设计落地必要的相关文档，再实现。
- **风险驱动测试**：核心、高风险、易回归逻辑优先测试驱动。
- **小步修改**：只做完成当前任务所需的最小变更。
- **不猜测**：不擅自补充业务规则；重要不确定性必须明确。
- **简单优先**：优先简单、清晰、可维护的方案，避免过度工程化。
- **验证后完成**：未经实际验证，不得声称任务完成。

---

## 2. 信息优先级

发生冲突时：

```text
用户当前明确指令
>
SPEC / 稳定契约
>
Architecture / ADR
>
Plan
>
测试
>
现有代码
>
AGENTS.md
```

文档职责：

- `SPEC.md`：需求、范围、边界、验收标准
- `docs/architecture.md`：整体技术设计,基于`SPEC.md`作为输入事实
- `docs/ui-spec.md`:整体UI设计,基于`SPEC.md`作为输入事实
- `docs/adr/`：重要长期技术决策
- `plans/`：复杂任务实施计划
- `README.md`：项目价值、使用方式、核心能力

不要为了适配现有实现而反向修改需求。

---

## 3. 默认工作流

```text
理解 → 设计 → 计划 → 实现 → 测试 → 验证 → 文档同步
```

开始任务前优先阅读：

1. `SPEC.md`
2. `README.md`
3. 相关 Architecture / ADR
4. 相关代码与测试

先明确：

- 问题与目标
- 当前行为与预期行为
- 修改范围
- 风险与边界
- 验收条件

简单、低风险修改可直接执行。  
复杂或高风险任务应先给出最小必要设计和实施计划，并拆成可独立验证的小步骤。

---

## 4. 需求与范围

实现前确认：

- 用户与目标
- 核心场景
- 输入与输出
- 功能范围
- 异常与边界
- Out of Scope
- Acceptance Criteria

重要需求尽量使用可验证形式：

```text
Given 前置条件
When  执行行为
Then  预期结果
```

禁止：

- 擅自扩大 Scope
- 删除已有业务规则
- 为“代码更优雅”改变业务行为
- 因实现限制反向修改需求

仅当任务本身包含需求变化时更新 `SPEC.md`。

---

## 5. 设计与架构

遵守现有架构和模块边界：

```text
简单 > 清晰 > 可维护 > 炫技
```

原则：

- 单一职责
- 高内聚、低耦合
- 依赖方向清晰
- 优先复用，避免复制
- 避免过早抽象
- 避免隐藏副作用
- 不为单个需求大范围重构

重大、长期技术决策使用 ADR 记录：

```text
Context / Options / Decision / Reasons / Trade-offs
```

普通实现细节不需要 ADR。

---

## 6. 文档创建

仅在实际需要时创建文档：

- 缺少 `SPEC.md`：不擅自猜测需求。
- 复杂架构变化：补充最小必要 Architecture。
- 重大长期技术决策：创建 ADR。
- 复杂多步骤任务：按需创建 Plan。
- 简单修改：不额外创建文档。

避免为了流程完整而制造文档。

---

## 7. 契约与数据写入

API、Tool、Event、Schema、数据库和外部集成应明确：

```text
Input / Output / Validation / Error / Permission
Timeout / Retry / Idempotency
```

Breaking Change 必须明确说明，不得静默引入。

涉及写操作时额外考虑：

- 幂等
- 事务
- 并发
- Partial Failure
- Rollback
- Audit

数据库结构变更通过 Migration 管理。

---

## 8. AI / Agent 规则

- LLM 负责推理，确定性代码负责权限、规则和安全约束。
- Tool 必须有明确 Schema、Validation 和 Error Handling。
- 权限和安全不能只依赖 Prompt。
- 高风险或不可逆操作应经过 Policy / Approval / Human-in-the-loop。
- 不基于模型猜测 Tool 执行结果或系统真实状态。
- Prompt、Model、Workflow 变更后，应运行固定 Eval / Regression。
- Agent / Workflow 应显式处理 State、Timeout、Retry、Fallback 和 Failure State。

高风险执行优先遵循：

```text
Validation → Permission → Policy → Approval → Execution → Audit
```

---

## 9. 测试

采用 **Risk-Based TDD**，优先覆盖：

- 核心业务逻辑
- 权限与数据隔离
- API / Tool Contract
- 状态流转
- 安全逻辑
- 异常与边界
- Retry / Timeout / Fallback
- 已发生过的 Bug

推荐：

```text
失败测试 → 最小实现 → 测试通过 → 必要重构
```

简单 UI、样式和低风险胶水代码不强制 TDD。

禁止：

- 删除或跳过测试制造“通过”
- 降低断言强度
- 修改需求适配错误实现
- 伪造测试结果

测试价值优先于覆盖率数字。

---

## 10. 代码质量

遵循项目已有 Formatter、Linter、Type System、命名规范和目录结构。

代码应：

- 职责单一
- 命名清晰
- 优先复用
- 避免重复
- 避免过早抽象
- 不做无关重构
- 不因个人偏好修改无关代码

---

## 11. 错误、安全与权限

重要流程不能只实现 Happy Path，至少考虑：

- Invalid Input
- Permission Denied
- Missing Data
- External Failure
- Timeout / Rate Limit
- Invalid Response
- Partial Failure / Retry Failure

禁止静默吞掉异常。

默认采用最小权限原则。禁止：

- 硬编码 Secret / Token / Password
- 默认信任外部输入
- 绕过认证、授权或审批
- 仅依赖 Prompt 实现权限控制
- 在日志中记录不必要的敏感信息
- 为解决依赖问题关闭 TLS、签名或完整性校验

---

## 12. 依赖与镜像源

新增依赖前确认：

- 是否真的需要
- 现有能力能否解决
- 是否仍在维护
- 是否增加明显复杂度或安全风险

中国大陆网络环境下：

- 优先使用可信的中国大陆软件源和镜像源。
- 镜像不可用、版本滞后或校验失败时回退官方源。
- 镜像配置放在环境或包管理器配置中，不硬编码到业务代码。
- 镜像加速不替代可信来源和完整性校验。

---

## 13. 可观测性

核心流程按需提供：

- Structured Log
- Metric
- Trace
- Error Reporting
- Request / Trace ID

日志应能回答：

```text
发生了什么？在哪里？为什么失败？如何追踪？
```

AI / Agent 场景按需记录 model、latency、token、route/node、tool call 和 final status。

不得记录不必要的敏感数据。

---

## 14. 发布与回滚

影响部署、数据库、配置或外部契约的修改应考虑：

- Compatibility
- Environment Variable
- Migration
- Health Check
- Rollback

高风险变更应有明确回滚路径。

```text
代码通过测试 ≠ 发布成功
```

---

## 15. 验证与完成标准

按项目实际情况执行相关检查：

```text
Lint / Type Check / Unit Test / Contract Test
Integration Test / Build / E2E / AI Eval
```

无需机械执行项目不存在或与本次修改无关的检查。

任务完成前确认：

- [ ] 满足明确需求
- [ ] 未擅自扩大 Scope
- [ ] Acceptance Criteria 已验证
- [ ] 核心测试通过
- [ ] 关键异常路径已验证
- [ ] 无明显安全或权限问题
- [ ] 无遗留调试代码
- [ ] Breaking Change 已明确说明
- [ ] 相关文档已同步
- [ ] 可以说明实际执行的验证

不得声称执行了未实际执行的命令或测试。

---

## 16. 文档同步

只更新真正受影响的文档：

| 变化 | 文档 |
|---|---|
| 用户使用方式 | `README.md` |
| 需求 / 产品行为 | `SPEC.md` |
| 架构 | Architecture / ADR |
| API / Tool | Contract 文档 |
| 部署方式 | Deployment / README |
| 重要版本变化 | `CHANGELOG.md`（若使用） |

README 优先让新人理解：

1. 解决什么问题
2. 为什么有价值，尽量可量化
3. 核心能力
4. Demo / Screenshot
5. 架构或流程,为什么选择这样实现
6. Quick Start
7. 已知限制

复杂流程优先使用 Mermaid 等可视化表达。

---

## 17. Agent 行为准则

始终：

- 先理解，再修改
- 明确重要假设
- 优先最小可行改动
- 保留现有合理设计
- 主动发现风险和边界问题
- 不隐藏错误
- 不伪造结果
- 不顺手修改无关代码
- 不因追求完整而过度工程化

最终原则：

```text
先理解，再编码。
先明确需求，再设计。
复杂功能先设计，再实现。
测试真正重要的部分。
验证后再宣布完成。
保持需求、代码、测试和文档一致。
用最简单可靠的方案解决真实问题。
```
