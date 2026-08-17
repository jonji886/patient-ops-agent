# AGENTS.md

> 通用 AI Coding 协作规范  
> 目标：让 AI 在明确需求和稳定边界内高效开发，确保变更可控、可验证、可维护。  
> 原则：**产品优先 · 第一性原理 · 规格驱动 · 小步交付 · 风险优先 · 验证后完成**

---

## 1. Core Principles

- 所有文档输出中文优先。
- **产品优先**：先理解用户、问题和业务价值，再写代码。
- **第一性原理**：复杂问题先回到目标、事实和不可变约束，再推导最简单可行方案，不被现有实现或惯例绑架。
- **规格驱动**：以用户当前明确指令、`SPEC.md` 和稳定契约为事实依据。
- **先设计后编码**：复杂、高风险或跨模块功能先完成最小必要设计，再实现。
- **小步交付**：优先可运行、可验证的 Vertical Slice，避免一次性大范围实现。
- **风险驱动测试**：核心、高风险、易回归逻辑优先测试；高风险边界主动进行对抗性测试。
- **不猜测**：不擅自补充业务规则；重要不确定性必须明确。
- **简单优先**：避免过早抽象、无关重构和过度工程化。
- **验证后完成**：未经实际验证，不得声称任务完成。

---

## 2. Source of Truth

发生冲突时：

```text
用户当前明确指令
>
SPEC / 稳定契约
>
Architecture / UI Spec / ADR
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

- `SPEC.md`：需求、范围、边界、Acceptance Criteria
- `docs/architecture.md`：整体技术设计
- `docs/ui-spec.md`：整体 UI / UX 设计
- `docs/adr/`：重大长期技术决策
- `plans/`：复杂任务的临时实施计划
- `README.md`：项目价值、核心能力、Demo、使用方式

不得为了适配现有实现而反向修改需求。

---

## 3. Default Workflow

```text
理解 → 设计 → 计划 → 实现 → 测试 → 验证 → 文档同步
```

开始任务前按需阅读：

1. `SPEC.md`
2. `README.md`
3. 相关 Architecture / UI Spec / ADR
4. 相关代码与测试

实现前至少明确：

- 用户与目标
- 当前行为与预期行为
- 输入与输出
- Scope / Out of Scope
- 风险与边界
- Acceptance Criteria

简单、低风险修改可直接执行。

复杂、高风险或跨模块任务应：

1. 回到目标、事实和约束判断真正问题
2. 形成最小必要设计
3. 必要时创建 Plan
4. 拆成可独立验证的小步骤
5. 优先交付可运行的 Vertical Slice

---

## 4. Requirements & Scope

重要需求优先使用：

```text
Given 前置条件
When  执行行为
Then  预期结果
```

禁止：

- 擅自扩大 Scope
- 删除已有业务规则
- 为代码“更优雅”改变业务行为
- 因实现限制反向修改需求
- 未经确认引入新的产品行为

仅当任务包含需求变化时更新 `SPEC.md`。

若缺少 `SPEC.md`：

- 明确、低风险的小任务可依据用户当前指令执行
- 涉及核心业务规则、产品行为或范围不明确时，不擅自猜测，应先明确需求或补充 SPEC

---

## 5. Design & Architecture

设计优先级：

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
- 不为单个需求做大范围无关重构

当现有方案明显复杂、存在根本矛盾或有多个候选方案时，先区分：

```text
事实 / 约束 / 假设 / 惯例
```

再做设计。

### Architecture

复杂架构变化按需明确：

- 目标与约束
- 模块边界
- 数据流
- 外部依赖
- 核心接口
- 失败路径
- 关键取舍

重大长期决策使用 ADR：

```text
Context / Options / Decision / Reasons / Trade-offs
```

### UI Spec

前端开发前按需明确：

- Target User
- Information Architecture
- Page / Route
- User Flow
- Layout / Component
- Interaction
- Empty / Loading / Error / Success State
- Responsive Behavior
- Design Token / Visual Direction
- Reference Style（如有）

避免由 LLM 在开发过程中临场自由发挥 UI。

---

## 6. Documentation Policy

仅在实际需要时创建文档：

- 复杂需求：补充 `SPEC.md`
- 复杂架构变化：补充 Architecture
- 重要 UI / 交互设计：补充 `ui-spec.md`
- 重大长期决策：创建 ADR
- 跨模块、长链路或高风险任务：按需创建 Plan
- 简单修改：不额外创建文档

Plan 是临时执行资产，不作为永久知识库。

避免为了流程完整而制造文档。

---

## 7. Contracts, Data & Side Effects

API、Tool、Event、Schema、数据库和外部集成应按需明确：

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

数据库结构变更使用 Migration 管理。

---

## 8. AI / Agent Rules

- LLM 负责推理；确定性代码负责权限、规则和安全约束。
- Tool 必须有明确 Schema、Validation 和 Error Handling。
- 权限和安全不能只依赖 Prompt。
- 不基于模型猜测 Tool 执行结果或系统真实状态。
- 高风险或不可逆操作应经过 Policy / Approval / Human-in-the-loop。
- Prompt、Model、Workflow 变更后，应运行固定 Eval / Regression。
- Agent / Workflow 应显式处理 State、Timeout、Retry、Fallback 和 Failure State。

高风险执行优先遵循：

```text
Validation → Permission → Policy → Approval → Execution → Audit
```

---

## 9. Testing

采用 **Risk-Based TDD + Adversarial Testing**。

优先覆盖：

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

高风险边界主动挑战：

- 权限与身份边界
- 不可信或畸形输入
- 非法状态跳转
- 重复、乱序、并发请求
- Tool 参数或返回异常
- 外部依赖失败
- Prompt Injection / Tool Misuse
- 高风险或不可逆操作

对抗性测试按风险执行，不为低风险修改制造无实际价值的测试。

简单 UI、样式和低风险胶水代码不强制 TDD。

禁止：

- 删除或跳过测试制造“通过”
- 降低断言强度
- 修改需求适配错误实现
- 伪造测试结果

测试价值优先于覆盖率数字。

---

## 10. Code, Security & Dependencies

遵循项目已有 Formatter、Linter、Type System、命名规范和目录结构。

代码应：

- 职责清晰
- 命名明确
- 优先复用
- 避免重复
- 避免过早抽象
- 不做无关重构

重要流程至少考虑：

```text
Invalid Input
Permission Denied
Missing Data
External Failure
Timeout / Rate Limit
Invalid Response
Partial Failure
```

禁止：

- 静默吞掉异常
- 硬编码 Secret / Token / Password
- 默认信任外部输入
- 绕过认证、授权或审批
- 仅依赖 Prompt 实现权限控制
- 在日志中记录不必要的敏感信息
- 为解决依赖问题关闭 TLS、签名或完整性校验

新增依赖前确认：

- 是否真的需要
- 现有能力能否解决
- 是否仍在维护
- 是否增加明显复杂度或安全风险

中国大陆网络环境下优先使用可信镜像源；不可用、版本滞后或校验失败时回退官方源。镜像配置不得硬编码到业务代码。

---

## 11. Observability & Release

核心流程按需提供：

- Structured Log
- Metric
- Trace
- Error Reporting
- Request / Trace ID

日志应帮助回答：

```text
发生了什么？
在哪里失败？
为什么失败？
如何追踪？
```

AI / Agent 场景按需记录：

```text
model / latency / token / route / node / tool call / final status
```

不得记录不必要的敏感数据。

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

## 12. Acceptance Criteria & Definition of Done

### Acceptance Criteria

回答：

> 产品行为是否符合需求？

至少关注：

- 正常路径
- 核心异常路径
- 权限与边界
- 明确业务结果

### Definition of Done

按项目实际情况执行：

```text
Lint / Type Check / Unit Test / Contract Test
Integration Test / Build / E2E / AI Eval
```

无需机械执行项目不存在或与本次修改无关的检查。

完成前确认：

- [ ] 满足明确需求
- [ ] 未擅自扩大 Scope
- [ ] Acceptance Criteria 已验证
- [ ] 核心测试通过
- [ ] 高风险边界已按需进行对抗性验证
- [ ] 无明显安全或权限问题
- [ ] 无遗留调试代码
- [ ] Breaking Change 已明确说明
- [ ] 相关文档已同步
- [ ] 可以说明实际执行过的验证

不得声称执行了未实际执行的命令、测试或验证。

---

## 13. Documentation Sync

只更新真正受影响的文档：

| 变化 | 文档 |
|---|---|
| 用户使用方式 | `README.md` |
| 需求 / 产品行为 | `SPEC.md` |
| 架构 | Architecture / ADR |
| UI / 交互 | `ui-spec.md` |
| API / Tool | Contract 文档 |
| 部署方式 | Deployment / README |
| 重要版本变化 | `CHANGELOG.md`（若使用） |

README 优先帮助新人快速理解：

1. 解决什么问题
2. 为什么有价值，尽量可量化
3. 核心能力
4. Demo / Screenshot
5. 架构或流程，以及为什么这样实现
6. Quick Start
7. 已知限制

复杂流程优先使用 Mermaid 等可视化表达。

---

## 14. Final Rules

```text
先理解，再编码。
先回到问题本质，再选择方案。
以需求和契约为准。
复杂功能先设计。
优先最小可行改动和 Vertical Slice。
对高风险边界主动找反例。
测试真正重要的部分。
实际验证后再宣布完成。
保持需求、设计、代码、测试和文档一致。
用最简单可靠的方案解决真实问题。
```