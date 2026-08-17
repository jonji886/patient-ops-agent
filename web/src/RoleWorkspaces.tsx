import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ApiError,
  assignManualTask,
  getAdminAudit,
  getAdminDashboard,
  getAdminRun,
  getAdminTrace,
  getManualTaskContext,
  listAdminRuns,
  listManualTasks,
  resolveManualTask,
  returnManualTaskToAgent,
  sendOperatorReply,
} from "./api";
import type { AdminActionItem, AdminAuditEvent, AdminDashboard, AdminMetricBucket, AdminRunSummary, ManualTask, OperatorTaskContext, Run, TraceEvent } from "./types";

const statusLabels: Record<string, string> = {
  ACTIVE: "正在处理", WAITING_PATIENT: "等待患者操作", RECONCILING: "正在对账", WAITING_HUMAN: "等待人工处理",
  COMPLETED: "已完成", COMPLETED_WITH_PENDING_SIDE_EFFECTS: "预约完成，后续处理中", FAILED: "未完成", CANCELLED_BY_PATIENT: "患者已取消",
  OPEN: "待领取", ASSIGNED: "处理中", RESOLVED: "已处理", RETURNED_TO_AGENT: "已交还 Agent", CANCELLED: "已取消",
  AGENT: "自动服务", OPERATOR: "人工客服", NOT_STARTED: "尚未执行", EXECUTING: "正在执行", OUTCOME_UNKNOWN: "结果待确认",
  SUCCEEDED: "已完成", FAILED_NEEDS_HUMAN: "需人工处理", RETRY_SCHEDULED: "等待重试", PENDING: "等待处理", NOT_REQUIRED: "无需执行",
  CREATE_APPOINTMENT: "创建预约", QUERY_APPOINTMENT: "查询预约", CANCEL_APPOINTMENT: "取消预约",
  PATIENT_REQUESTED: "患者请求人工", RETRY_EXHAUSTED: "自动重试已耗尽", IDENTITY_UNVERIFIED: "身份需人工核验",
  STATE_CONFLICT: "状态冲突", POLICY_REQUIRES_HUMAN: "策略要求人工处理", UNKNOWN: "结果待确认",
};

const workflowLabels: Record<string, string> = {
  INIT: "已创建服务请求", LOADING_PATIENT_CONTEXT: "正在加载患者上下文", UNDERSTANDING_REQUEST: "正在识别患者需求",
  COLLECTING_REQUIREMENTS: "等待补充预约信息", SEARCHING_SLOTS: "正在查询可约时段", WAITING_SELECTION: "等待选择预约时段",
  QUERYING_APPOINTMENTS: "正在查询预约", WAITING_APPOINTMENT_SELECTION: "等待选择目标预约", PREPARING_CONFIRMATION: "正在准备确认",
  WAITING_CONFIRMATION: "等待患者确认", VALIDATING_EXECUTION: "正在校验执行条件", EXECUTING_CORE_ACTION: "正在提交预约业务",
  VERIFYING_CORE_RESULT: "正在核验预约结果", RECONCILING_CORE_RESULT: "正在对账业务结果", ENQUEUEING_WRITEBACK: "正在安排运营回写",
  ENQUEUEING_NOTIFICATION: "正在安排患者通知", NEED_HUMAN: "等待人工处理", TERMINAL: "流程已结束",
};

const traceEventLabels: Record<string, string> = {
  run_created: "已创建服务请求", patient_context_loaded: "已加载患者上下文", understanding_produced: "已识别患者需求",
  slots_returned: "已找到可预约时段", alternative_slots_returned: "已找到替代可约时段", confirmation_prepared: "已生成预约确认",
  cancellation_confirmation_prepared: "已生成取消确认", appointments_returned: "已返回预约查询结果", business_result_verified: "已核验业务结果",
  outbox_persisted: "已安排后续服务", notification_suppressed_by_consent: "已按患者授权跳过通知", human_handoff: "已转交人工客服",
  operator_message_recorded: "已记录人工客服回复", operator_reply_sent: "人工客服回复已送达", run_returned_to_agent: "任务已交还自动服务",
  run_cancelled_by_patient: "患者已取消当前流程", policy_denied: "安全策略已拒绝请求", tool_outcome_unknown: "业务结果待对账",
  duplicate_request_suppressed: "已拦截重复请求", patient_message_recorded_for_operator: "已记录患者消息",
};

const toolLabels: Record<string, string> = {
  search_available_slots: "查询可预约时段", get_patient_appointments: "查询患者预约", create_appointment: "创建预约",
  cancel_appointment: "取消预约", get_operation_result: "查询业务执行结果",
};

function label(value: string | null | undefined): string { return (value && statusLabels[value]) || value || "未确定"; }
function workflowLabel(value: string | null | undefined): string { return (value && workflowLabels[value]) || "系统处理中"; }
function traceLabel(value: string): string { return traceEventLabels[value] || "系统运行事件"; }
function toolLabel(value: string): string { return toolLabels[value] || "业务系统调用"; }

function tone(value: string): string {
  if (value === "COMPLETED" || value === "SUCCEEDED" || value === "RESOLVED" || value === "RETURNED_TO_AGENT") return "success";
  if (value === "FAILED" || value === "FAILED_NEEDS_HUMAN") return "danger";
  if (value.includes("WAITING") || value.includes("PENDING") || value === "OPEN" || value === "ASSIGNED" || value === "OPERATOR") return "warning";
  if (value === "ACTIVE" || value === "EXECUTING" || value === "AGENT") return "info";
  return "neutral";
}

function StatusBadge({ value }: { value: string }) { return <span className={`status status--${tone(value)}`}>{label(value)}</span>; }

function ErrorNotice({ message }: { message: string | null }) {
  return message ? <div className="notice notice--error" role="alert">{message}</div> : null;
}

function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value: string | null | undefined): string {
  const date = parseDate(value);
  return date ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Shanghai" }).format(date) : "时间未知";
}

function formatTimeOfDay(value: string | null | undefined): string | null {
  const date = parseDate(value);
  return date ? new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Shanghai" }).format(date) : null;
}

function waitingText(since: string | null | undefined): string | null {
  const date = parseDate(since);
  if (!date) return null;
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  if (minutes < 1) return "不足 1 分钟";
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} 小时 ${rest} 分钟` : `${hours} 小时`;
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return <button type="button" className="copy-button" onClick={() => {
    void navigator.clipboard?.writeText(value).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }).catch(() => setCopied(false));
  }}>{copied ? "已复制" : "复制"}</button>;
}

type TraceCategory = "WORKFLOW" | "POLICY" | "TOOL" | "RECOVERY" | "SIDE_EFFECT";

const traceCategoryLabels: Record<TraceCategory | "ALL", string> = {
  ALL: "全部", WORKFLOW: "流程", POLICY: "策略", TOOL: "业务调用", RECOVERY: "恢复与接管", SIDE_EFFECT: "后续服务",
};

const traceCategoryMap: Record<string, TraceCategory> = {
  policy_denied: "POLICY", duplicate_request_suppressed: "POLICY",
  human_handoff: "RECOVERY", run_returned_to_agent: "RECOVERY", tool_outcome_unknown: "RECOVERY",
  outbox_persisted: "SIDE_EFFECT", notification_suppressed_by_consent: "SIDE_EFFECT",
};

function traceCategory(event: TraceEvent): TraceCategory {
  return traceCategoryMap[event.event] ?? (event.tool_name ? "TOOL" : "WORKFLOW");
}

const defaultExpandedEvents = new Set(["human_handoff", "policy_denied", "tool_outcome_unknown"]);

function TraceList({ events }: { events: TraceEvent[] }) {
  const [filter, setFilter] = useState<TraceCategory | "ALL">("ALL");
  if (!events.length) return <p className="panel-copy">暂无可展示的执行记录。</p>;
  const visible = filter === "ALL" ? events : events.filter((event) => traceCategory(event) === filter);
  return <>
    <div className="trace-filters" role="group" aria-label="执行记录筛选">
      {(Object.keys(traceCategoryLabels) as Array<TraceCategory | "ALL">).map((key) => <button key={key} type="button" className={`trace-filter${filter === key ? " trace-filter--active" : ""}`} onClick={() => setFilter(key)}>{traceCategoryLabels[key]}</button>)}
    </div>
    {visible.length === 0 ? <p className="panel-copy">该分类下暂无执行记录。</p> : <ol className="role-trace-list">
      {visible.map((event, index) => <li key={`${event.trace_id}-${index}`}>
        <span className={`role-trace-dot role-trace-dot--${tone(event.status ?? "NEUTRAL")}`} aria-hidden="true" />
        <div>
          <strong>{traceLabel(event.event)}</strong>
          <p>{workflowLabel(event.node)}{event.tool_name ? ` · ${toolLabel(event.tool_name)}` : ""}{event.duration_ms != null ? ` · ${event.duration_ms}ms` : ""}</p>
          <time>{formatDateTime(event.timestamp)}</time>
          <details className="role-trace-details" open={defaultExpandedEvents.has(event.event) || undefined}>
            <summary>技术详情</summary>
            <dl className="trace-details">
              {event.node ? <div><dt>工作流节点</dt><dd>{event.node}</dd></div> : null}
              {event.tool_name ? <div><dt>Tool</dt><dd>{event.tool_name}</dd></div> : null}
              {event.status ? <div><dt>结果</dt><dd>{event.status}</dd></div> : null}
              <div><dt>Trace ID</dt><dd>{event.trace_id} <CopyButton value={event.trace_id} /></dd></div>
              {Object.entries(event.details ?? {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === "string" ? value : JSON.stringify(value)}</dd></div>)}
            </dl>
          </details>
        </div>
      </li>)}
    </ol>}
  </>;
}

const caseSteps = ["领取任务", "回复与处理", "记录处理完成", "交还 Agent"];

function caseStepIndex(status: ManualTask["status"]): number {
  if (status === "OPEN") return 0;
  if (status === "ASSIGNED") return 1;
  if (status === "RESOLVED") return 2;
  if (status === "RETURNED_TO_AGENT") return 3;
  return -1;
}

function CaseProgress({ status }: { status: ManualTask["status"] }) {
  if (status === "CANCELLED") return <p className="panel-copy">任务已取消，无需继续处理。</p>;
  const current = caseStepIndex(status);
  return <nav className="case-steps" aria-label="处理进度"><ol>
    {caseSteps.map((step, index) => <li key={step} className={`case-steps__step${index < current ? " case-steps__step--done" : index === current ? " case-steps__step--active" : ""}`} aria-current={index === current ? "step" : undefined}>
      <span aria-hidden="true">{index < current ? "✓" : index + 1}</span><strong>{step}</strong>
    </li>)}
  </ol></nav>;
}

function TaskQueue({ tasks, selectedTaskId, onSelect }: { tasks: ManualTask[]; selectedTaskId: string | null; onSelect: (taskId: string) => void }) {
  return <aside className="task-queue" aria-label="人工任务队列">
    <div className="workspace-panel-heading"><div><p className="eyebrow">MANUAL TASKS</p><h2>待处理任务</h2></div><span className="queue-count">{tasks.length}</span></div>
    {tasks.length === 0 ? <p className="panel-copy">当前没有等待人工的请求。出现新的人工任务时，会自动显示在这里。</p> : <div className="task-list" role="list">
      {tasks.map((task) => <button key={task.task_id} type="button" role="listitem" className={`task-list__item${task.task_id === selectedTaskId ? " task-list__item--selected" : ""}`} onClick={() => onSelect(task.task_id)}>
        <span className="task-list__top"><strong>{label(task.reason_code)}</strong><StatusBadge value={task.status} /></span>
        <span className="task-list__meta">患者 {task.masked_patient_id ?? "已脱敏"} · {task.intent ? label(task.intent) : "意图尚未解析"}</span>
        <span className="task-list__meta">{task.assigned_operator_id ? `已分配给 ${task.assigned_operator_id}` : "尚未分配"}{formatTimeOfDay(task.created_at) ? ` · ${formatTimeOfDay(task.created_at)} 创建` : ""}{waitingText(task.created_at) && (task.status === "OPEN" || task.status === "ASSIGNED") ? ` · 已等待 ${waitingText(task.created_at)}` : ""}</span>
      </button>)}
    </div>}
  </aside>;
}

function OperatorCase({ context, hasTasks, busy, onAssign, onReply, onResolve, onReturn }: { context: OperatorTaskContext | null; hasTasks: boolean; busy: boolean; onAssign: () => void; onReply: (message: string) => void; onResolve: (resolution: string) => void; onReturn: () => void }) {
  const [resolution, setResolution] = useState("");
  const [reply, setReply] = useState("");
  const [returnConfirmation, setReturnConfirmation] = useState(false);
  useEffect(() => { setResolution(context?.task.resolution ?? ""); setReply(""); setReturnConfirmation(false); }, [context?.task.task_id, context?.task.status, context?.task.resolution]);
  if (!context) return <main className="operator-case operator-case--empty"><p className="eyebrow">CASE WORKSPACE</p><h1>{hasTasks ? "选择一个人工任务" : "暂无待处理任务"}</h1><p>{hasTasks ? "在任务队列中选择任务后，可查看经过授权的脱敏上下文和执行记录。" : "当前没有需要人工处理的请求。出现新任务时，左侧队列会自动更新。"}</p></main>;
  const { task, run, trace } = context;
  const isPending = task.status === "OPEN" || task.status === "ASSIGNED";
  return <main className="operator-case" aria-label="人工任务处理工作区">
    <header className="case-header"><div><p className="eyebrow">CASE WORKSPACE</p><h1>{label(task.reason_code)}</h1><p>患者 {run.masked_patient_id ?? "已脱敏"} · {run.intent ? label(run.intent) : "意图尚未解析"}</p></div><StatusBadge value={task.status} /></header>
    <CaseProgress status={task.status} />
    <section className="case-conversation" aria-labelledby="case-conversation-title"><div><p className="eyebrow">CONVERSATION</p><h2 id="case-conversation-title">患者说了什么</h2><p>仅显示此人工任务关联的会话内容。</p></div><div className="case-conversation__messages">{context.messages.length === 0 ? <p className="panel-copy">尚无可展示的患者消息。</p> : context.messages.map((message, index) => <article className={`case-message case-message--${message.author.toLowerCase()}`} key={`${message.created_at}-${index}`}><span>{message.author === "PATIENT" ? "患者" : "人工客服"}</span><p>{message.text}</p><time>{formatDateTime(message.created_at)}</time></article>)}{run.current_reply && (run.current_reply_author === "AGENT" || context.messages.at(-1)?.text !== run.current_reply) && <article className={`case-message case-message--${run.current_reply_author.toLowerCase()}`}><span>{run.current_reply_author === "OPERATOR" ? "人工客服" : "Agent"}</span><p>{run.current_reply}</p><time>当前回复</time></article>}</div></section>
    <section className="case-summary" aria-label="当前任务摘要"><div><span>当前业务状态</span><StatusBadge value={run.run_status} /></div><div><span>执行归属</span><StatusBadge value={run.execution_owner} /></div><div><span>任务创建</span><strong>{formatDateTime(task.created_at)}</strong>{isPending && waitingText(task.created_at) ? <small>已等待 {waitingText(task.created_at)}</small> : null}</div></section>
    <section className="case-actions" aria-labelledby="case-actions-title"><div><p className="eyebrow">处理操作</p><h2 id="case-actions-title">记录并完成任务</h2></div>
      {task.status === "OPEN" && <><p className="panel-copy">可先查看上方的患者上下文与执行记录；领取任务后才能回复患者或完成处理。</p><button type="button" className="button button--primary" onClick={onAssign} disabled={busy}>领取任务</button></>}
      {task.status === "ASSIGNED" && <><p className="panel-copy">任务当前由 {task.assigned_operator_id ?? "你"} 负责；只有领取人可以回复患者或记录处理。</p><label className="resolution-field">向患者回复<textarea aria-label="向患者回复" value={reply} onChange={(event) => setReply(event.target.value)} placeholder="输入将发送给患者的人工回复" rows={3} disabled={busy} /></label><button type="button" className="button button--secondary" onClick={() => onReply(reply.trim())} disabled={busy || !reply.trim()}>发送给患者</button><label className="resolution-field">处理说明<textarea value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="记录已核实的事实和处理结果" rows={3} disabled={busy} /></label><p className="case-actions__hint">“发送给患者”只把回复写入患者会话；“记录处理完成”仅登记处理结论，不会通知患者，也不会自动交还 Agent。</p><button type="button" className="button button--primary" onClick={() => onResolve(resolution.trim())} disabled={busy || !resolution.trim()}>记录处理完成</button></>}
      {task.status === "RESOLVED" && !returnConfirmation && <button type="button" className="button button--secondary" onClick={() => setReturnConfirmation(true)} disabled={busy}>交还 Agent</button>}
      {task.status === "RESOLVED" && returnConfirmation && <div className="return-confirmation" role="status"><p>交还后，旧患者确认会失效；Agent 将从服务端事实重新开始判断，后续高风险操作仍需患者重新确认。</p><div><button type="button" className="button button--secondary" onClick={() => setReturnConfirmation(false)} disabled={busy}>暂不交还</button><button type="button" className="button button--primary" onClick={onReturn} disabled={busy}>确认交还 Agent</button></div></div>}
      {task.status === "RETURNED_TO_AGENT" && <p className="panel-copy">任务已交还 Agent，当前页面不会乐观推断后续业务结果。</p>}
    </section>
    <section className="role-trace-section" aria-labelledby="operator-trace-title"><p className="eyebrow">EXECUTION HISTORY</p><h2 id="operator-trace-title">执行记录</h2><TraceList events={trace} /></section>
  </main>;
}

export function OperatorWorkspace({ token, headerActions }: { token: string; headerActions: ReactNode }) {
  const [tasks, setTasks] = useState<ManualTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [context, setContext] = useState<OperatorTaskContext | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newTaskCount, setNewTaskCount] = useState(0);
  const seenTaskIds = useRef<Set<string>>(new Set());

  function rememberTasks(list: ManualTask[]) {
    list.forEach((item) => seenTaskIds.current.add(item.task_id));
  }

  async function refresh(selectTaskId = selectedTaskId) {
    const next = await listManualTasks(token);
    rememberTasks(next);
    setTasks(next);
    const availableId = selectTaskId && next.some((item) => item.task_id === selectTaskId) ? selectTaskId : next[0]?.task_id ?? null;
    setSelectedTaskId(availableId);
    if (availableId) setContext(await getManualTaskContext(token, availableId)); else setContext(null);
  }
  useEffect(() => { void refresh(null).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "加载人工任务失败。")); }, [token]);
  useEffect(() => { if (selectedTaskId) void getManualTaskContext(token, selectedTaskId).then(setContext).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "加载任务上下文失败。")); }, [selectedTaskId, token]);
  useEffect(() => {
    if (!selectedTaskId) return;
    const id = window.setInterval(() => {
      if (busy) return;
      void getManualTaskContext(token, selectedTaskId).then(setContext).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "刷新任务上下文失败。"));
    }, 1500);
    return () => window.clearInterval(id);
  }, [busy, selectedTaskId, token]);
  useEffect(() => {
    const id = window.setInterval(() => {
      if (busy) return;
      void listManualTasks(token).then((next) => {
        const fresh = next.filter((item) => !seenTaskIds.current.has(item.task_id));
        rememberTasks(next);
        if (fresh.length) setNewTaskCount((count) => count + fresh.length);
        setTasks(next);
      }).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(id);
  }, [busy, token]);
  async function execute(action: () => Promise<unknown>) { setBusy(true); setError(null); try { await action(); await refresh(); } catch (reason) { setError(reason instanceof ApiError ? reason.message : "操作未能完成，请重试。"); } finally { setBusy(false); } }

  return <div className="role-shell role-shell--operator"><header className="role-header"><div><p className="eyebrow">PATIENT OPS AGENT · OPERATOR</p><h1>人工客服工作台</h1></div><div>{headerActions}<span className="connection"><i aria-hidden="true" />任务服务已连接</span></div></header><ErrorNotice message={error} />{newTaskCount > 0 ? <div className="notice" role="status"><span>队列新增 {newTaskCount} 个人工任务。</span><button type="button" className="text-button" onClick={() => setNewTaskCount(0)}>知道了</button></div> : null}<div className="operator-workspace"><TaskQueue tasks={tasks} selectedTaskId={selectedTaskId} onSelect={setSelectedTaskId} /><OperatorCase context={context} hasTasks={tasks.length > 0} busy={busy} onAssign={() => context && execute(() => assignManualTask(token, context.task.task_id))} onReply={(message) => context && execute(() => sendOperatorReply(token, context.task.task_id, message))} onResolve={(resolution) => context && execute(() => resolveManualTask(token, context.task.task_id, resolution))} onReturn={() => context && execute(() => returnManualTaskToAgent(token, context.task.task_id))} /><aside className="operator-context" aria-label="任务上下文"><p className="eyebrow">TASK CONTEXT</p>{context ? <><dl className="runtime-list"><div><dt>处理责任</dt><dd>{context.task.assigned_operator_id ?? "待领取"}</dd></div><div><dt>任务创建</dt><dd>{formatDateTime(context.task.created_at)}</dd></div></dl><details className="technical-details"><summary>技术详情</summary><dl className="runtime-list runtime-list--technical"><div><dt>任务 ID</dt><dd>{context.task.task_id} <CopyButton value={context.task.task_id} /></dd></div><div><dt>Run ID</dt><dd>{context.task.run_id} <CopyButton value={context.task.run_id} /></dd></div></dl></details></> : <p className="panel-copy">选择任务后显示经授权的上下文。</p>}</aside></div></div>;
}

function AdminRunList({ runs, selectedRunId, onSelect }: { runs: AdminRunSummary[]; selectedRunId: string | null; onSelect: (runId: string) => void }) {
  return <aside className="admin-run-list" aria-label="运行列表"><div className="workspace-panel-heading"><div><p className="eyebrow">运行记录</p><h2>运行记录</h2></div><span className="queue-count">{runs.length}</span></div><p className="panel-copy">选择一条记录查看已脱敏的运行过程。</p>{runs.length === 0 ? <p className="panel-copy">暂无可观察的运行。</p> : <div className="task-list" role="list">{runs.map((run) => <button key={run.run_id} type="button" role="listitem" className={`task-list__item${run.run_id === selectedRunId ? " task-list__item--selected" : ""}`} onClick={() => onSelect(run.run_id)}><span className="task-list__top"><strong>{label(run.intent)}</strong><StatusBadge value={run.run_status} /></span><span className="task-list__meta">患者 {run.masked_patient_id} · {formatDateTime(run.started_at)}</span></button>)}</div>}</aside>;
}

function AdminDetail({ run, trace }: { run: Run | null; trace: TraceEvent[] }) {
  if (!run) return <main className="admin-detail admin-detail--empty"><p className="eyebrow">运行详情</p><h1>选择一条运行记录</h1><p>管理员可查看已脱敏的运行事实、策略和业务系统调用记录；此工作台不提供患者业务写入操作。</p></main>;
  return <main className="admin-detail" aria-label="运行诊断详情"><header className="case-header"><div><p className="eyebrow">运行详情</p><h1>{label(run.intent)}</h1><p>患者 {run.masked_patient_id ?? "已脱敏"} · {workflowLabel(run.workflow_step)}</p></div><StatusBadge value={run.run_status} /></header><section className="admin-summary"><div><span>当前处理方</span><StatusBadge value={run.execution_owner} /></div><div><span>核心业务结果</span><StatusBadge value={run.core_business_status} /></div><div><span>最近错误</span><strong>{run.last_error_code ?? "无"}</strong></div><div><span>业务操作编号</span><strong>{run.operation_id ?? "尚未创建"}</strong></div></section><section className="role-trace-section" aria-labelledby="admin-trace-title"><p className="eyebrow">运行过程</p><h2 id="admin-trace-title">运行时间线</h2><TraceList events={trace} /></section></main>;
}

function AuditFeed({ events }: { events: AdminAuditEvent[] }) {
  return <aside className="audit-feed" aria-label="审计记录"><p className="eyebrow">审计记录</p><h2>最近运行事件</h2><p className="panel-copy">仅显示已脱敏的只读审计信息。</p>{events.length === 0 ? <p className="panel-copy">暂无运行审计事件。</p> : <ol>{events.slice(0, 12).map((event, index) => <li key={`${event.run_id}-${event.trace_id}-${index}`}><strong>{traceLabel(event.event)}</strong><span>患者 {event.masked_patient_id}</span><time>{formatDateTime(event.timestamp)}</time></li>)}</ol>}</aside>;
}

const funnelLabels: Record<string, string> = {
  CREATE_REQUESTED: "发起创建预约", SLOT_FOUND: "找到可约时段", CONFIRMATION_PREPARED: "已生成患者确认", APPOINTMENT_SUCCEEDED: "预约业务成功",
};

const actionCopy: Record<AdminActionItem["kind"], { title: string; description: (count: number) => string; action: string }> = {
  HUMAN_HANDOFF: { title: "人工服务请求待处理", description: (count) => `当前有 ${count} 个请求正在等待人工客服处理。`, action: "查看相关运行" },
  FAILED_RUN: { title: "存在未完成的服务请求", description: (count) => `当前有 ${count} 个请求未能完成，请先确认失败原因。`, action: "查看相关运行" },
  PENDING_SIDE_EFFECT: { title: "预约已完成，后续服务待处理", description: (count) => `已有 ${count} 个预约完成核心业务，但运营回写或患者通知仍在处理。`, action: "查看相关运行" },
  SECURITY_INCIDENT: { title: "发现安全策略拒绝记录", description: (count) => `有 ${count} 个请求被安全策略拒绝，应由管理员复核其运行过程。`, action: "查看相关运行" },
  SYSTEM_HEALTHY: { title: "当前没有需立即关注的运行", description: () => "未发现等待人工、失败、后续服务待处理或安全策略拒绝的运行。", action: "查看运行诊断" },
};

function formatPercent(value: number | null): string { return value === null ? "暂无已结束样本" : `${value}%`; }

function KpiCard({ title, value, description, advice, tone = "neutral" }: { title: string; value: string | number; description: string; advice: string; tone?: "neutral" | "success" | "warning" | "danger" }) {
  return <article className={`admin-kpi admin-kpi--${tone}`}><p>{title}</p><strong>{value}</strong><span>{description}</span><small>建议：{advice}</small></article>;
}

function DistributionChart({ title, description, items, itemLabel }: { title: string; description: string; items: AdminMetricBucket[]; itemLabel: (key: string) => string }) {
  const maximum = Math.max(1, ...items.map((item) => item.count));
  return <section className="admin-chart-card" aria-label={title}><div className="admin-chart-card__heading"><div><h2>{title}</h2><p>{description}</p></div></div>{items.length === 0 ? <p className="panel-copy">当前没有可展示的数据。</p> : <ul className="distribution-bars">{items.map((item) => <li key={item.key}><span>{itemLabel(item.key)}</span><div aria-hidden="true"><i style={{ width: `${item.count / maximum * 100}%` }} /></div><strong>{item.count}</strong></li>)}</ul>}</section>;
}

function FunnelChart({ items }: { items: AdminMetricBucket[] }) {
  const maximum = Math.max(1, ...items.map((item) => item.count));
  return <section className="admin-chart-card" aria-label="创建预约转化流程"><div className="admin-chart-card__heading"><div><h2>创建预约转化流程</h2><p>展示创建预约从发起到业务成功的真实运行数量。</p></div></div><ol className="admin-funnel">{items.map((item) => <li key={item.key}><span>{funnelLabels[item.key] ?? "流程阶段"}</span><div><i style={{ width: `${item.count / maximum * 100}%` }} /></div><strong>{item.count}</strong></li>)}</ol></section>;
}

function TrendChart({ dashboard }: { dashboard: AdminDashboard }) {
  const maximum = Math.max(1, ...dashboard.daily_trend.map((item) => item.total_runs));
  return <section className="admin-chart-card" aria-label="每日服务请求趋势"><div className="admin-chart-card__heading"><div><h2>每日服务请求趋势</h2><p>蓝色代表服务请求，绿色代表预约业务成功。</p></div></div>{dashboard.daily_trend.length === 0 ? <p className="panel-copy">当前没有可展示的数据。</p> : <div className="admin-trend" role="list">{dashboard.daily_trend.map((item) => <div key={item.date} role="listitem"><div className="admin-trend__bars" aria-label={`${item.date}：${item.total_runs} 个服务请求，${item.successful_appointments} 个预约业务成功`}><i className="admin-trend__total" style={{ height: `${Math.max(8, item.total_runs / maximum * 100)}%` }} /><i className="admin-trend__success" style={{ height: `${Math.max(item.successful_appointments ? 8 : 0, item.successful_appointments / maximum * 100)}%` }} /></div><strong>{item.date.slice(5)}</strong><span>{item.total_runs} 个请求</span></div>)}</div>}</section>;
}

function AdminOverview({ dashboard, onInspect }: { dashboard: AdminDashboard; onInspect: (runIds: string[]) => void }) {
  const { metrics } = dashboard;
  return <main className="admin-overview" aria-label="运营总览"><header className="admin-overview__header"><div><p className="eyebrow">运营总览</p><h1>预约服务运行概览</h1><p>基于当前管理员权限范围内、已脱敏的真实运行数据生成。</p></div><time>更新于 {formatDateTime(dashboard.generated_at)}</time></header><section className="admin-kpi-grid" aria-label="关键指标"><KpiCard title="服务请求总数" value={metrics.total_runs} description="当前演示数据中的全部服务请求。" advice="结合请求类型和趋势判断当前服务量。" /><KpiCard title="成功预约" value={metrics.successful_appointments} description="核心预约业务已核验成功的创建请求。" advice="关注其变化，并结合漏斗定位转化阻塞。" tone="success" /><KpiCard title="预约完成率" value={formatPercent(metrics.appointment_completion_rate)} description="仅统计已结束的创建预约请求。" advice="如低于运营目标，请查看创建预约转化流程。" tone={metrics.appointment_completion_rate !== null && metrics.appointment_completion_rate < 100 ? "warning" : "success"} /><KpiCard title="等待患者操作" value={metrics.waiting_patient} description="等待患者补充信息、选择时段或确认。" advice="这是患者侧待办，不应与人工客服积压混淆。" /><KpiCard title="等待人工处理" value={metrics.waiting_human} description="已转交人工客服且尚未交还的请求。" advice={metrics.waiting_human ? "优先协调人工客服处理相关请求。" : "当前没有人工服务积压。"} tone={metrics.waiting_human ? "warning" : "success"} /><KpiCard title="后续服务待处理" value={metrics.pending_side_effects} description="核心预约已完成，运营回写或通知仍在处理。" advice={metrics.pending_side_effects ? "查看相关运行，确认后续服务是否恢复。" : "当前没有后续服务待处理。"} tone={metrics.pending_side_effects ? "warning" : "success"} /><KpiCard title="未完成请求" value={metrics.failed_runs} description="因校验、上游或其他原因未完成的请求。" advice={metrics.failed_runs ? "先查看失败原因，再决定系统或流程处置。" : "当前没有未完成请求。"} tone={metrics.failed_runs ? "danger" : "success"} /><KpiCard title="安全策略拒绝" value={metrics.security_incidents} description="被服务端安全策略明确拒绝的请求。" advice={metrics.security_incidents ? "立即复核运行过程并按安全流程处置。" : "当前未发现安全策略拒绝。"} tone={metrics.security_incidents ? "danger" : "success"} /></section><section className="admin-insights"><div className="admin-priority"><div className="admin-section-heading"><div><p className="eyebrow">优先事项</p><h2>现在需要关注什么</h2></div><p>建议由服务端根据真实运行状态生成。</p></div><ol>{dashboard.action_items.map((item) => { const copy = actionCopy[item.kind]; return <li key={item.kind} className={`admin-action admin-action--${item.severity}`}><div><strong>{copy.title}</strong><p>{copy.description(item.count)}</p></div><button type="button" className="button button--secondary" onClick={() => onInspect(item.run_ids)}>{copy.action}</button></li>; })}</ol></div><TrendChart dashboard={dashboard} /></section><section className="admin-chart-grid"><FunnelChart items={dashboard.funnel} /><DistributionChart title="运行状态分布" description="帮助区分已完成、等待患者、等待人工和未完成的请求。" items={dashboard.status_distribution} itemLabel={label} /><DistributionChart title="请求类型分布" description="了解创建、查询与取消预约的服务需求构成。" items={dashboard.intent_distribution} itemLabel={label} /><DistributionChart title="未完成原因" description="仅统计带有服务端错误码的运行。" items={dashboard.error_distribution} itemLabel={(key) => `错误：${label(key)}`} /></section></main>;
}

export function AdminWorkspace({ token, headerActions }: { token: string; headerActions: ReactNode }) {
  const [runs, setRuns] = useState<AdminRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [audit, setAudit] = useState<AdminAuditEvent[]>([]);
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null);
  const [view, setView] = useState<"overview" | "diagnostics">("overview");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { void Promise.all([listAdminRuns(token), getAdminAudit(token), getAdminDashboard(token)]).then(([nextRuns, nextAudit, nextDashboard]) => { setRuns(nextRuns); setAudit(nextAudit); setDashboard(nextDashboard); setSelectedRunId(nextRuns[0]?.run_id ?? null); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "加载管理数据失败。")); }, [token]);
  useEffect(() => { if (!selectedRunId) { setRun(null); setTrace([]); return; } void Promise.all([getAdminRun(token, selectedRunId), getAdminTrace(token, selectedRunId)]).then(([nextRun, nextTrace]) => { setRun(nextRun); setTrace(nextTrace); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "加载运行详情失败。")); }, [selectedRunId, token]);
  function inspect(runIds: string[]) { setSelectedRunId(runIds[0] ?? runs[0]?.run_id ?? null); setView("diagnostics"); }
  return <div className="role-shell role-shell--admin"><header className="role-header"><div><p className="eyebrow">患者预约服务 · 管理员</p><h1>运营管理工作台</h1></div><div>{headerActions}<span className="connection"><i aria-hidden="true" />观测服务已连接</span></div></header><ErrorNotice message={error} /><nav className="admin-tabs" aria-label="管理员视图"><button type="button" className={view === "overview" ? "admin-tabs__item admin-tabs__item--active" : "admin-tabs__item"} aria-current={view === "overview" ? "page" : undefined} onClick={() => setView("overview")}>运营总览</button><button type="button" className={view === "diagnostics" ? "admin-tabs__item admin-tabs__item--active" : "admin-tabs__item"} aria-current={view === "diagnostics" ? "page" : undefined} onClick={() => setView("diagnostics")}>运行诊断</button></nav>{view === "overview" ? dashboard ? <AdminOverview dashboard={dashboard} onInspect={inspect} /> : <main className="admin-overview admin-overview--loading" aria-busy="true">正在加载运营数据…</main> : <div className="admin-workspace"><AdminRunList runs={runs} selectedRunId={selectedRunId} onSelect={setSelectedRunId} /><AdminDetail run={run} trace={trace} /><AuditFeed events={audit} /></div>}</div>;
}
