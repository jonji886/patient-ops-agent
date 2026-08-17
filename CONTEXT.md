# Patient Ops Agent

Patient Ops Agent 使用统一语言描述患者运营、诊所预约与 Agent 执行三个相邻领域。本文只定义领域概念，不记录实现方式。

## 患者运营

**Patient（患者）**：
接受诊所服务、在患者运营平台中拥有稳定身份的人。
_Avoid_：User、Customer、Account

**Patient Fact（患者事实）**：
患者运营平台提供的、带来源与发生时间的患者业务事实。
_Avoid_：Memory、Profile Field

**Contact Consent（触达许可）**：
患者是否允许通过某一渠道接收运营消息的有效授权状态。
_Avoid_：Channel Preference

**Next Best Action（后续行动计划）**：
患者运营平台基于患者事实建议的下一项运营动作；它不是执行授权。
_Avoid_：Command、Permission

**Writeback（结果回写）**：
将 Agent 的业务执行结果记录回患者运营平台。
_Avoid_：Log、Notification

## 诊所预约

**Clinic（诊所）**：
提供口腔医疗服务的线下门诊。
_Avoid_：Hospital、Tenant

**Service Item（服务项目）**：
患者可以预约的服务项目，例如洗牙。
_Avoid_：Department、Treatment Plan

**Doctor（医生）**：
在指定诊所提供一个或多个服务项目的专业人员。
_Avoid_：Provider、Operator

**Slot（号源）**：
诊所核心系统发布的、可用于一次预约的时间资源。
_Avoid_：Schedule、Appointment Time

**Appointment（预约）**：
患者对某个号源和服务项目形成的业务记录。
_Avoid_：Booking Request、Agent Run

## Agent 执行

**Conversation（会话）**：
患者与系统在一个渠道中的连续交互容器；一个会话可包含多个 Agent Run。
_Avoid_：Run、Task

**Agent Run（Agent 运行）**：
为完成一个明确业务目标而执行的一次工作流实例。
_Avoid_：Conversation、Appointment

**Operation（业务操作）**：
一次具有稳定身份的外部业务写入意图；同一 Operation 可包含多次执行尝试。
_Avoid_：Attempt、Tool Call

**Attempt（执行尝试）**：
为完成同一个 Operation 发起的一次具体外部调用。
_Avoid_：Operation、Retry Task

**Patient Confirmation（患者确认）**：
患者对具体业务动作及其参数快照作出的明确确认。
_Avoid_：Human Approval、Handoff

**Operator Approval（人工审批）**：
人工客服允许一项受限动作继续执行的决定；它不替代患者确认。
_Avoid_：Patient Confirmation、Handoff

**Human Handoff（人工接管）**：
Agent 将某个 Run 的执行权转交人工客服。
_Avoid_：Alert、Manual Task、Operator Approval

**Manual Task（人工任务）**：
人工接管后用于跟踪处理责任和结果的工作项。
_Avoid_：Handoff、Agent Run

**Reconciliation（结果对账）**：
外部写操作结果不确定时，依据业务系统事实确认其真实结果。
_Avoid_：Blind Retry、Compensation
