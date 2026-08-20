import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode, type RefObject } from "react";
import {
  ApiError,
  activateDemoScenario,
  cancelRun,
  confirm,
  createConversation,
  getRun,
  getDemoScenarioStatus,
  getTrace,
  listDemoAccounts,
  login,
  requestHandoff,
  selectAvailableDate,
  selectAppointment,
  selectServiceItem,
  selectSlot,
  sendMessage,
} from "./api";
import { AdminWorkspace, OperatorWorkspace } from "./RoleWorkspaces";
import type { ActorRole, Appointment, AvailableDate, DemoAccount, DemoScenarioId, DemoScenarioStatus, Run, ServiceOption, Slot, SuggestedReply, TraceEvent } from "./types";

type ChatItem = {
  id: string;
  author: "patient" | "agent" | "operator";
  text: string;
};

const initialPrompts = [
  { label: "创建预约", message: "我想创建预约" },
  { label: "查询我未来的预约", message: "查询我未来的预约" },
  { label: "我想取消我的预约", message: "我想取消我的预约" },
];

const labels: Record<string, string> = {
  ACTIVE: "正在处理",
  WAITING_PATIENT: "等待您的操作",
  RECONCILING: "正在确认预约结果",
  WAITING_HUMAN: "已转人工处理",
  COMPLETED: "已完成",
  COMPLETED_WITH_PENDING_SIDE_EFFECTS: "预约已完成，后续处理中",
  FAILED: "未完成",
  CANCELLED_BY_PATIENT: "流程已取消",
  AGENT: "Agent 执行中",
  OPERATOR: "人工客服已接管",
  NOT_STARTED: "尚未执行",
  EXECUTING: "正在执行",
  OUTCOME_UNKNOWN: "结果待确认",
  SUCCEEDED: "已完成",
  FAILED_NEEDS_HUMAN: "需人工处理",
  RETRY_SCHEDULED: "等待重试",
  PENDING: "等待处理",
  NOT_REQUIRED: "无需执行",
  NONE: "无需操作",
  SERVICE_SELECTION: "请选择服务项目",
  DATE_SELECTION: "请选择可约日期",
  SLOT_SELECTION: "请选择预约时段",
  APPOINTMENT_SELECTION: "请选择预约",
  CONFIRMATION: "请确认本次操作",
  HUMAN: "等待人工处理",
  CREATE_APPOINTMENT: "创建预约",
  QUERY_APPOINTMENT: "查询预约",
  CANCEL_APPOINTMENT: "取消预约",
  CANCEL_CURRENT_RUN: "取消当前流程",
  REQUEST_HUMAN: "请求人工客服",
};

const traceLabels: Record<string, string> = {
  run_created: "Run 已创建", patient_context_loaded: "患者上下文已加载", understanding_produced: "Intent Parsed",
  slots_returned: "号源已查询", confirmation_prepared: "患者确认已生成", policy_decision: "Policy 已校验",
  tool_outcome_unknown: "API 响应超时 · UNKNOWN", business_result_found: "Reconciliation 找到业务结果",
  business_result_verified: "业务结果已核验", outbox_persisted: "Outbox 已持久化", human_handoff: "执行权已转人工",
  policy_denied: "Policy BLOCKED", tool_execution: "Tool 已执行", duplicate_request_suppressed: "重复预约已抑制",
};

function label(value: string | null | undefined): string {
  return (value && labels[value]) || value || "未确定";
}

function tone(value: string): string {
  if (value === "SUCCEEDED" || value === "COMPLETED") return "success";
  if (value === "FAILED" || value === "FAILED_NEEDS_HUMAN") return "danger";
  if (
    value.includes("WAITING") ||
    value.includes("RETRY") ||
    value.includes("UNKNOWN") ||
    value.includes("PENDING") ||
    value === "OPERATOR"
  ) {
    return "warning";
  }
  if (value === "ACTIVE" || value === "EXECUTING" || value === "AGENT") return "info";
  return "neutral";
}

function formatDateTime(value?: string | null): string {
  if (!value) return "时间待确认";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`status status--${tone(value)}`}>{label(value)}</span>;
}

function Notice({ children, kind = "info" }: { children: ReactNode; kind?: "info" | "error" }) {
  return <div className={`notice notice--${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}

function ConversationEmptyState({ onChoosePrompt }: { onChoosePrompt: (prompt: string) => void }) {
  return (
    <section className="conversation-empty-state" aria-labelledby="empty-state-title">
      <p className="eyebrow">从这里开始</p>
      <h3 id="empty-state-title">我可以帮您处理本人的预约</h3>
      <p>创建预约会依次引导您选择服务项目、可约日期和具体时段，并在提交前请您确认；取消预约会先列出您现有的预约供选择并二次确认；查询预约将直接返回您的预约详情。</p>
      <div className="prompt-list" aria-label="示例预约需求">
        {initialPrompts.map((prompt) => (
          <button key={prompt.label} className="prompt-button" type="button" onClick={() => onChoosePrompt(prompt.message)}>{prompt.label}</button>
        ))}
      </div>
    </section>
  );
}

function roleLabel(role: ActorRole): string {
  return ({ PATIENT: "患者", OPERATOR: "人工客服", ADMIN: "管理员" })[role];
}

function LoginScreen({ accounts, loadingAccounts, loadError, onAuthenticate }: { accounts: DemoAccount[]; loadingAccounts: boolean; loadError: string | null; onAuthenticate: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!username && accounts[0]) setUsername(accounts[0].username);
  }, [accounts, username]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onAuthenticate(username, password);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <p className="eyebrow">PATIENT OPS AGENT</p>
        <h1 id="login-title">患者预约交付工作台</h1>
        <p className="login-copy">使用虚构演示账号进入模拟渠道。系统不会展示或持久化你的访问凭据。</p>
        <form onSubmit={submit} className="login-form">
          <label>
            演示身份
            <select aria-label="演示身份" value={username} onChange={(event) => { setUsername(event.target.value); setPassword(""); }} disabled={loadingAccounts || !accounts.length}>
              {accounts.map((account) => <option key={account.username} value={account.username}>{account.display_name}（{roleLabel(account.actor_role)}）</option>)}
            </select>
          </label>
          <label>
            密码
            <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required />
          </label>
          {(error || loadError) && <Notice kind="error">{error ?? loadError}</Notice>}
          <button type="submit" className="button button--primary" disabled={busy || loadingAccounts || !username}>
            {busy ? "正在进入…" : loadingAccounts ? "正在加载身份…" : "进入工作台"}
          </button>
        </form>
        <p className="help-text">仅使用仓库内的合成数据；系统根据服务端签发的角色进入对应工作台。</p>
      </section>
    </main>
  );
}

function AccountMenu({ displayName, actorRole, onSwitch, onLogout, triggerRef }: { displayName: string; actorRole: ActorRole; onSwitch: () => void; onLogout: () => void; triggerRef: RefObject<HTMLButtonElement | null> }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); triggerRef.current?.focus(); }
    };
    document.addEventListener("mousedown", closeOnOutside);
    window.addEventListener("keydown", closeOnEscape);
    return () => { document.removeEventListener("mousedown", closeOnOutside); window.removeEventListener("keydown", closeOnEscape); };
  }, [open, triggerRef]);

  return <div className="account-menu" ref={menuRef}>
    <button ref={triggerRef} type="button" className="account-menu__trigger" aria-expanded={open} aria-controls="account-actions" onClick={() => setOpen((visible) => !visible)}>
      <span className="account-menu__name">{displayName}</span><span className="account-menu__role">{roleLabel(actorRole)}</span><span aria-hidden="true">⌄</span>
    </button>
    {open && <div id="account-actions" className="account-menu__popover" aria-label="账号操作">
      <p className="account-menu__identity">当前为 {roleLabel(actorRole)}身份</p>
      <button type="button" onClick={() => { setOpen(false); onSwitch(); }}>切换演示身份</button>
      <button type="button" className="account-menu__logout" onClick={() => { setOpen(false); onLogout(); }}>退出登录</button>
    </div>}
  </div>;
}

function AccountSwitchDialog({ accounts, currentRole, onClose, onAuthenticate }: { accounts: DemoAccount[]; currentRole: ActorRole; onClose: () => void; onAuthenticate: (username: string, password: string) => Promise<void> }) {
  const switchableAccounts = accounts.filter((account) => account.actor_role !== currentRole);
  const initialAccount = switchableAccounts[0];
  const [username, setUsername] = useState(initialAccount?.username ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const selectRef = useRef<HTMLSelectElement>(null);

  useEffect(() => { selectRef.current?.focus(); }, []);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) { event.preventDefault(); onClose(); }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("button:not(:disabled), select:not(:disabled), input:not(:disabled)"));
      if (!focusable.length) return;
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onClose]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null);
    try { await onAuthenticate(username, password); onClose(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "身份切换失败，请重试。"); }
    finally { setBusy(false); }
  }

  return <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section ref={dialogRef} className="dialog account-switch-dialog" role="dialog" aria-modal="true" aria-labelledby="switch-account-title" aria-describedby="switch-account-description">
      <p className="eyebrow">演示身份</p><h2 id="switch-account-title">切换演示身份</h2>
      <p id="switch-account-description">切换会退出当前浏览器会话并进入新身份的工作台；不会取消或修改原身份的预约和处理流程。</p>
      <form className="login-form" onSubmit={submit}>
        <label>切换到<select ref={selectRef} aria-label="切换到演示身份" value={username} onChange={(event) => { setUsername(event.target.value); setPassword(""); }} disabled={busy}>{switchableAccounts.map((account) => <option key={account.username} value={account.username}>{account.display_name}（{roleLabel(account.actor_role)}）</option>)}</select></label>
        <label>密码<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required disabled={busy} /></label>
        {error && <Notice kind="error">{error}</Notice>}
        <div className="dialog-actions"><button type="button" className="button button--secondary" onClick={onClose} disabled={busy}>取消</button><button type="submit" className="button button--primary" disabled={busy || !username || !password}>{busy ? "正在切换…" : "确认切换"}</button></div>
      </form>
    </section>
  </div>;
}

function SlotOptions({ run, onSelect, busy }: { run: Run; onSelect: (slot: Slot) => void; busy: boolean }) {
  return (
    <section className="action-card" aria-labelledby="slot-title">
      <div className="card-heading">
        <div>
          <p className="eyebrow">下一步</p>
          <h3 id="slot-title">请选择预约时段</h3>
        </div>
        <StatusBadge value="WAITING_PATIENT" />
      </div>
      <div className="option-list" role="list">
        {run.candidate_slots.map((slot) => (
          <button
            key={slot.id}
            className="option-row"
            type="button"
            onClick={() => onSelect(slot)}
            disabled={busy || run.execution_owner !== "AGENT"}
          >
            <span>
              <strong>{formatDateTime(slot.start_at)}</strong>
              <span className="option-meta">诊所 {slot.clinic_id} · 服务项目 {slot.service_item_id} · 医生 {slot.doctor_id}</span>
            </span>
            <span aria-hidden="true">选择</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function BookingProgress({ run }: { run: Run }) {
  if (run.intent !== "CREATE_APPOINTMENT") return null;
  // action_required 未落在四个引导态之一时（例如 NONE、HUMAN），不能默认视为“全部完成”，
  // 需要根据已确定的字段推断真实进度，避免把未选的步骤误标成已完成。
  const active = run.action_required === "SERVICE_SELECTION" ? 1
    : run.action_required === "DATE_SELECTION" ? 2
    : run.action_required === "SLOT_SELECTION" ? 3
    : run.action_required === "CONFIRMATION" ? 4
    : run.selected_slot_id || run.core_business_status === "SUCCEEDED" ? 4
    : run.requested_date ? 3
    : run.service_item_name ? 2
    : 1;
  const steps = [
    { title: "服务项目", detail: run.service_item_name ?? (active === 1 ? "待选择" : "已选择") },
    { title: "可约日期", detail: run.requested_date ?? (active === 2 ? "待选择" : "待选择") },
    { title: "具体时段", detail: run.selected_slot_id ? "已选择" : active === 3 ? "待选择" : "待选择" },
    { title: "确认预约", detail: run.action_required === "CONFIRMATION" ? "请确认" : "待进行" },
  ];
  return <section className="booking-progress" aria-label="预约进度"><ol>{steps.map((step, index) => <li key={step.title} className={index + 1 < active ? "booking-progress__step--done" : index + 1 === active ? "booking-progress__step--active" : ""}><span>{index + 1}</span><div><strong>{step.title}</strong><small>{step.detail}</small></div></li>)}</ol></section>;
}

function ServiceOptions({ run, onSelect, busy }: { run: Run; onSelect: (service: ServiceOption) => void; busy: boolean }) {
  return <section className="action-card" aria-labelledby="service-title">
    <div className="card-heading"><div><p className="eyebrow">预约引导 · 第 1 步</p><h3 id="service-title">请选择服务项目</h3></div><StatusBadge value="WAITING_PATIENT" /></div>
    <p className="help-text">服务项目和时长由门诊服务端提供；选择后再查看真实可约日期。</p>
    <div className="service-option-list" role="list">{run.candidate_service_items.map((service) => <button key={service.id} type="button" className="service-option" onClick={() => onSelect(service)} disabled={busy || run.execution_owner !== "AGENT"}><strong>{service.name}</strong><span>预计 {service.duration_minutes} 分钟</span><em>选择</em></button>)}</div>
  </section>;
}

function formatAvailableDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "short", timeZone: "Asia/Shanghai" }).format(new Date(`${value}T00:00:00+08:00`));
}

function AvailableDateOptions({ run, onSelect, busy }: { run: Run; onSelect: (date: AvailableDate) => void; busy: boolean }) {
  return <section className="action-card" aria-labelledby="date-title">
    <div className="card-heading"><div><p className="eyebrow">预约引导 · 第 2 步</p><h3 id="date-title">请选择可约日期</h3></div><StatusBadge value="WAITING_PATIENT" /></div>
    <p className="help-text">以下日期均有可预约时段。选择日期后再查看具体时间和医生。</p>
    <div className="date-option-list" role="list">{run.candidate_dates.map((item) => <button key={item.date} type="button" className="date-option" onClick={() => onSelect(item)} disabled={busy || run.execution_owner !== "AGENT"}><strong>{formatAvailableDate(item.date)}</strong><span>{item.available_slot_count} 个可约时段</span><em>查看当天时段</em></button>)}</div>
  </section>;
}

function AppointmentOptions({ run, busy, onSelect }: { run: Run; busy: boolean; onSelect: (appointment: Appointment) => void }) {
  return (
    <section className="action-card" aria-labelledby="appointment-title">
      <div className="card-heading">
        <div>
          <p className="eyebrow">下一步</p>
          <h3 id="appointment-title">请选择要处理的预约</h3>
        </div>
        <StatusBadge value="WAITING_PATIENT" />
      </div>
      <div className="option-list" role="list">
        {run.candidate_appointments.map((appointment) => (
          <article key={appointment.id} className="option-row appointment-option" role="listitem">
            <span>
              <strong>{appointment.status === "CONFIRMED" ? "已确认预约" : appointment.status}</strong>
              <span className="option-meta">{formatDateTime(appointment.start_at)} · 诊所 {appointment.clinic_name ?? appointment.clinic_id} · 服务项目 {appointment.service_item_name ?? appointment.service_item_id} · 医生 {appointment.doctor_name ?? appointment.doctor_id}</span>
            </span>
            <button type="button" className="button button--danger appointment-option__action" onClick={() => onSelect(appointment)} disabled={busy || run.execution_owner !== "AGENT"}>取消此预约</button>
          </article>
        ))}
      </div>
      <p className="help-text">选择后会展示取消确认信息；此操作不会立即取消预约。</p>
    </section>
  );
}

function AppointmentDetailsCard({ run }: { run: Run }) {
  if (run.intent !== "QUERY_APPOINTMENT" || run.candidate_appointments.length === 0) return null;
  return (
    <section className="appointment-details-card" aria-labelledby="future-appointments-title">
      <div className="card-heading"><div><p className="eyebrow">未来预约</p><h3 id="future-appointments-title">您的预约详情</h3></div><StatusBadge value="SUCCEEDED" /></div>
      <div className="appointment-details-list" role="list">
        {run.candidate_appointments.map((appointment) => <article className="appointment-detail" key={appointment.id} role="listitem">
          <div><strong>{appointment.status === "CONFIRMED" ? "已确认预约" : label(appointment.status)}</strong><span>{formatDateTime(appointment.start_at)}{appointment.end_at ? ` 至 ${formatDateTime(appointment.end_at)}` : ""}</span></div>
          <dl><div><dt>服务项目</dt><dd>{appointment.service_item_name ?? appointment.service_item_id}</dd></div><div><dt>诊所</dt><dd>{appointment.clinic_name ?? appointment.clinic_id}</dd></div><div><dt>医生</dt><dd>{appointment.doctor_name ?? appointment.doctor_id}</dd></div><div><dt>预约状态</dt><dd>{appointment.status === "CONFIRMED" ? "已确认" : label(appointment.status)}</dd></div></dl>
        </article>)}
      </div>
      <p className="help-text">以上为您本人未来预约的服务端查询结果。</p>
    </section>
  );
}

function ConfirmationCard({ run, onConfirm, busy }: { run: Run; onConfirm: () => void; busy: boolean }) {
  const slot = run.candidate_slots.find((item) => item.id === run.selected_slot_id);
  const appointment = run.candidate_appointments.find((item) => item.id === run.appointment_id);
  const action = run.intent === "CANCEL_APPOINTMENT" ? "取消预约" : "预约";
  return (
    <section className="confirmation-card" aria-labelledby="confirmation-title">
      <div className="card-heading">
        <div>
          <p className="eyebrow">患者确认</p>
          <h3 id="confirmation-title">请确认以下{action}信息</h3>
        </div>
        <StatusBadge value="PENDING" />
      </div>
      <dl className="summary-grid">
        <div><dt>诊所</dt><dd>{slot?.clinic_id ?? appointment?.clinic_name ?? appointment?.clinic_id ?? "以当前预约为准"}</dd></div>
        <div><dt>服务项目</dt><dd>{slot?.service_item_id ?? appointment?.service_item_name ?? appointment?.service_item_id ?? "以当前预约为准"}</dd></div>
        <div><dt>医生</dt><dd>{slot?.doctor_id ?? appointment?.doctor_name ?? appointment?.doctor_id ?? "以当前预约为准"}</dd></div>
        <div><dt>日期与时间</dt><dd>{formatDateTime(slot?.start_at ?? appointment?.start_at)}</dd></div>
      </dl>
      <Notice>确认后，系统会重新校验身份、资源版本、执行权和确认有效性，再提交本次操作。</Notice>
      <div className="card-actions">
        <button type="button" className="button button--primary" onClick={onConfirm} disabled={busy || run.execution_owner !== "AGENT"}>
          {busy ? "正在校验并提交…" : `确认${action}`}
        </button>
      </div>
    </section>
  );
}

function BusinessResult({ run }: { run: Run }) {
  if (run.intent === "QUERY_APPOINTMENT") return null;
  if (run.core_business_status === "OUTCOME_UNKNOWN" || run.run_status === "RECONCILING") {
    return <Notice>正在确认预约结果。请勿重复提交；系统会依据本次操作记录核对实际结果。</Notice>;
  }
  if (run.core_business_status !== "SUCCEEDED") return null;
  const isCancellation = run.intent === "CANCEL_APPOINTMENT";
  return (
    <section className="result-card" aria-label="业务结果">
      <div className="result-card__title">
        <span className="result-mark" aria-hidden="true">✓</span>
        <div>
          <p className="eyebrow">核心业务结果</p>
          <h3>{isCancellation ? "预约已取消" : "预约已成功"}</h3>
        </div>
      </div>
      <p>{isCancellation ? "系统已核验该预约的取消状态。" : "系统已核验本次预约结果。"}</p>
      <SideEffects run={run} />
    </section>
  );
}

function RunStateNotice({ run, busy }: { run: Run | null; busy: boolean }) {
  if (busy && !run) return <section className="loading-message" aria-label="正在处理消息"><span className="skeleton skeleton--short" /><span className="skeleton" /></section>;
  if (!run) return null;
  if (run.run_status === "RECONCILING" || run.core_business_status === "OUTCOME_UNKNOWN") {
    return <section className="recovery-card" aria-label="正在确认预约结果"><p className="eyebrow">结果对账</p><h3>正在确认预约结果</h3><p>本次操作未收到明确结果，系统正在依据相同的操作记录确认实际状态。请勿重复提交。</p><ol><li>写操作响应不确定</li><li>查询本次 Operation 结果</li><li>核验后更新业务结果或转人工</li></ol></section>;
  }
  if (run.run_status === "FAILED") return <Notice kind="error">当前 Run 未完成。{run.last_error_code ? `原因：${run.last_error_code}。` : ""}请根据提示重新查询、重新认证或请求人工客服。</Notice>;
  if (run.run_status === "ACTIVE" && run.attempt_count > 1) return <Notice>正在按原操作重试（第 {run.attempt_count} 次）。请勿重复确认。</Notice>;
  return null;
}

function SideEffects({ run }: { run: Run }) {
  return (
    <div className="side-effects" aria-label="后续处理状态">
      <p className="eyebrow">后续处理</p>
      <div><span>运营回写</span><StatusBadge value={run.writeback_status} /></div>
      <div><span>患者通知</span><StatusBadge value={run.notification_status} /></div>
      {run.run_status === "COMPLETED_WITH_PENDING_SIDE_EFFECTS" && <p className="help-text">后续处理重试不影响已核验的预约结果。</p>}
    </div>
  );
}

function HandoffBanner({ run }: { run: Run }) {
  if (run.execution_owner !== "OPERATOR") return null;
  return <section className="handoff-banner" role="status"><div><p className="eyebrow">执行权已切换</p><strong>当前已由人工客服接管</strong><p>Agent 自动执行已暂停。{run.manual_task_id ? "人工任务已创建，人工客服会根据当前 Run 和已记录的执行上下文继续处理。" : "人工客服会根据当前 Run 和已记录的执行上下文继续处理。"}</p></div><StatusBadge value="OPERATOR" /></section>;
}

function DemoScenarioPanel({ status, busy, onActivate }: { status: DemoScenarioStatus; busy: boolean; onActivate: (scenario: DemoScenarioId) => void }) {
  return (
    <section className="demo-scenario-panel" aria-labelledby="demo-scenario-title">
      <div className="card-heading">
        <div><p className="eyebrow">INTERVIEW DEMO</p><h3 id="demo-scenario-title">Demo Scenarios</h3></div>
        <StatusBadge value={status.active_scenario === "NONE" ? "NONE" : status.active_scenario} />
      </div>
      <p className="help-text">故障只影响下一次对应的 Mock Adapter 调用，消费后自动恢复 NONE；默认不会启用任何故障。</p>
      <div className="demo-scenario-list" role="list">
        {status.scenarios.map((scenario) => (
          <button key={scenario.id} type="button" className={`demo-scenario${status.active_scenario === scenario.id ? " demo-scenario--active" : ""}`} onClick={() => onActivate(scenario.id)} disabled={busy || (status.active_scenario !== "NONE" && scenario.id !== "NONE")}>
            <span><strong>{scenario.name}</strong><small>{scenario.description}</small><em>{scenario.observation}</em></span>
            <i>{scenario.id === "NONE" ? "基线" : status.active_scenario === scenario.id ? "已启用" : "启用"}</i>
          </button>
        ))}
      </div>
      {status.active_scenario !== "NONE" && <p className="demo-scenario-hint">请按正常预约流程继续；场景将在下一次匹配的外部调用中消费。</p>}
    </section>
  );
}

function TraceTimeline({ events }: { events: TraceEvent[] }) {
  if (!events.length) return null;
  return (
    <section className="trace-timeline" aria-labelledby="trace-timeline-title">
      <div className="card-heading"><div><p className="eyebrow">EXECUTION TRACE</p><h3 id="trace-timeline-title">运行时间线</h3></div><span className="help-text">{events.length} 个事件</span></div>
      <ol>
        {events.map((event, index) => <li key={`${event.trace_id}-${index}`}><span className={`trace-timeline__dot trace-timeline__dot--${tone(event.status ?? "NEUTRAL")}`} /><div><strong>{traceLabels[event.event] ?? event.event}</strong><time>{formatDateTime(event.timestamp)}</time>{event.status && <small>{event.status}</small>}</div></li>)}
      </ol>
    </section>
  );
}

export function App() {
  const [token, setToken] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [actorRole, setActorRole] = useState<ActorRole | null>(null);
  const [demoAccounts, setDemoAccounts] = useState<DemoAccount[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [accountLoadError, setAccountLoadError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [demoScenario, setDemoScenario] = useState<DemoScenarioStatus | null>(null);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<ChatItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [accountSwitchOpen, setAccountSwitchOpen] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const messageInputRef = useRef<HTMLTextAreaElement>(null);
  const conversationFeedRef = useRef<HTMLDivElement>(null);
  const accountMenuTriggerRef = useRef<HTMLButtonElement>(null);
  const lastRenderedReplyKeyRef = useRef<string | null>(null);

  const handoff = run?.execution_owner === "OPERATOR";
  const suggestedReplies = run?.suggested_replies ?? [];
  const shouldPoll = Boolean(run && token && (run.run_status === "ACTIVE" || run.run_status === "RECONCILING" || run.run_status === "COMPLETED_WITH_PENDING_SIDE_EFFECTS" || run.run_status === "WAITING_HUMAN"));
  const isInitialView = !run && !busy;

  useEffect(() => {
    void listDemoAccounts().then(setDemoAccounts).catch((reason: unknown) => {
      setAccountLoadError(reason instanceof Error ? reason.message : "加载演示身份失败，请刷新后重试。");
    }).finally(() => setLoadingAccounts(false));
  }, []);

  useEffect(() => {
    if (!token || actorRole !== "PATIENT") {
      setDemoScenario(null);
      return;
    }
    void getDemoScenarioStatus(token).then(setDemoScenario).catch((reason: unknown) => {
      // A 404 means the server is running with ENABLE_DEMO_SCENARIOS=false.
      if (!(reason instanceof ApiError) || reason.code !== "DEMO_SCENARIOS_DISABLED") setDemoScenario(null);
    });
  }, [actorRole, token]);

  useEffect(() => {
    if (!cancelDialogOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) setCancelDialogOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [busy, cancelDialogOpen]);

  useEffect(() => {
    if (!shouldPoll || !run || !token) return;
    const id = window.setInterval(() => {
      void Promise.all([getRun(token, run.run_id), getTrace(token, run.run_id)]).then(([nextRun, nextTrace]) => { updateRun(nextRun); setTrace(nextTrace); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "状态刷新失败。"));
    }, 1500);
    return () => window.clearInterval(id);
  }, [run?.run_id, run?.state_version, shouldPoll, token]);

  useEffect(() => {
    if (!run || !token) {
      setTrace([]);
      return;
    }
    void getTrace(token, run.run_id).then(setTrace).catch(() => setTrace([]));
    if (demoScenario) void getDemoScenarioStatus(token).then(setDemoScenario).catch(() => undefined);
  }, [demoScenario !== null, run?.run_id, run?.state_version, token]);

  useEffect(() => {
    const feed = conversationFeedRef.current;
    if (feed) feed.scrollTop = feed.scrollHeight;
  }, [messages.length, run?.run_id, run?.state_version, trace.length]);

  const composerDisabled = busy || run?.action_required === "SLOT_SELECTION" || run?.action_required === "CONFIRMATION";
  const canShowSuggestedReplies = !handoff && !composerDisabled && run?.action_required !== "APPOINTMENT_SELECTION";
  const canCancel = Boolean(run && ["ACTIVE", "WAITING_PATIENT"].includes(run.run_status) && run.core_business_status === "NOT_STARTED" && !handoff);

  const currentTitle = useMemo(() => run ? label(run.intent) : "新的患者会话", [run]);

  function updateRun(next: Run) {
    setRun(next);
    if (next.current_reply) {
      const author = next.current_reply_author === "OPERATOR" ? "operator" : "agent";
      // 用 state_version 而非文案内容去重：state_version 在每次真实状态迁移时都会递增，
      // 即使两次迁移碰巧产生完全相同的回复文案（例如连续两次选中同一个零号源服务项目），
      // 也必须各自渲染成一条新气泡；文案去重只会让第二次操作在界面上“看起来没反应”。
      // 轮询同一未变化的 Run 时 state_version 不变，仍然保持不重复追加。
      const replyKey = `${next.run_id}:${author}:${next.state_version}`;
      if (lastRenderedReplyKeyRef.current !== replyKey) {
        setMessages((current) => [...current, { id: crypto.randomUUID(), author, text: next.current_reply! }]);
        lastRenderedReplyKeyRef.current = replyKey;
      }
    }
  }

  async function execute(action: () => Promise<Run | { run: Run }>) {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      updateRun("run" in result ? result.run : result);
    } catch (reason) {
      const apiError = reason instanceof ApiError ? reason : null;
      setError(apiError?.code === "STATE_VERSION_CONFLICT" ? "信息已更新，请刷新后继续。" : reason instanceof Error ? reason.message : "操作未能完成，请重试。");
      if (apiError?.code === "STATE_VERSION_CONFLICT" && run && token) {
        void getRun(token, run.run_id).then(setRun);
      }
    } finally {
      setBusy(false);
    }
  }

  async function submitPatientMessage(text: string) {
    if (!token || !conversationId) return;
    setMessages((current) => [...current, { id: crypto.randomUUID(), author: "patient", text }]);
    await execute(() => sendMessage(token, conversationId, text));
  }

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = message.trim();
    if (!text) return;
    setMessage("");
    await submitPatientMessage(text);
  }

  function chooseInitialPrompt(prompt: string) {
    // 顶层意图入口文案固定且无歧义，点击即直接发起该消息；与会话中段服务端下发的
    // suggested_replies（仅填入 Composer，需患者再主动发送）是两类不同交互。
    void submitPatientMessage(prompt);
  }

  function chooseSuggestedReply(reply: SuggestedReply) {
    if (reply.mode !== "FILL_COMPOSER") return;
    setMessage(reply.message);
    messageInputRef.current?.focus();
  }

  function clearBrowserSession() {
    setToken(null); setDisplayName(""); setActorRole(null); setConversationId(null); setRun(null); setTrace([]); setDemoScenario(null); setMessage("");
    setMessages([]); setError(null); setBusy(false); setCancelDialogOpen(false); setAccountSwitchOpen(false); setNavCollapsed(false);
    lastRenderedReplyKeyRef.current = null;
  }

  async function authenticate(username: string, password: string) {
    const account = await login(username, password);
    const conversation = account.actor_role === "PATIENT" ? await createConversation(account.access_token) : undefined;
    setRun(null); setTrace([]); setDemoScenario(null); setMessage(""); setMessages(account.actor_role === "PATIENT" ? [{ id: crypto.randomUUID(), author: "agent", text: "你好，我可以协助你创建、查询或取消本人的预约。" }] : []);
    lastRenderedReplyKeyRef.current = null;
    setError(null); setBusy(false); setCancelDialogOpen(false); setNavCollapsed(false);
    setToken(account.access_token); setDisplayName(account.display_name); setActorRole(account.actor_role); setConversationId(conversation?.conversation_id ?? null);
  }

  function closeAccountSwitch() {
    setAccountSwitchOpen(false);
    window.requestAnimationFrame(() => accountMenuTriggerRef.current?.focus());
  }

  async function triggerDemoScenario(scenario: DemoScenarioId) {
    if (!token || !demoScenario) return;
    setBusy(true);
    setError(null);
    try {
      const next = await activateDemoScenario(token, scenario);
      setDemoScenario(next);
      if (next.trigger_message) setMessage(next.trigger_message);
      else if (scenario !== "NONE") setMessage("我想预约明天下午洗牙");
      else setMessage("我想预约明天下午洗牙");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Demo Scenario 启用失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  const accountActions = actorRole ? <AccountMenu displayName={displayName} actorRole={actorRole} onSwitch={() => setAccountSwitchOpen(true)} onLogout={clearBrowserSession} triggerRef={accountMenuTriggerRef} /> : null;

  if (!token || !actorRole || (actorRole === "PATIENT" && !conversationId)) {
    return <LoginScreen accounts={demoAccounts} loadingAccounts={loadingAccounts} loadError={accountLoadError} onAuthenticate={authenticate} />;
  }

  if (actorRole === "OPERATOR") return <><OperatorWorkspace token={token} headerActions={accountActions} />{accountSwitchOpen && <AccountSwitchDialog accounts={demoAccounts} currentRole={actorRole} onClose={closeAccountSwitch} onAuthenticate={authenticate} />}</>;
  if (actorRole === "ADMIN") return <><AdminWorkspace token={token} headerActions={accountActions} />{accountSwitchOpen && <AccountSwitchDialog accounts={demoAccounts} currentRole={actorRole} onClose={closeAccountSwitch} onAuthenticate={authenticate} />}</>;

  return (
    <div className="app-shell">
      <header className="app-header"><div><p className="eyebrow">PATIENT OPS AGENT</p><h1>患者预约交付工作台</h1></div><div className="header-meta">{accountActions}<span className="connection"><i aria-hidden="true" />渠道已连接</span></div></header>
      <div className={`workspace workspace--patient${navCollapsed ? " workspace--nav-collapsed" : ""}${isInitialView ? " workspace--initial" : ""}`}>
        <nav className="run-nav" aria-label="会话导航">
          <div className="run-nav__header"><p className="eyebrow run-nav__label">会话</p><button type="button" className="icon-button run-nav__toggle" onClick={() => setNavCollapsed((collapsed) => !collapsed)} aria-label={navCollapsed ? "展开会话导航" : "收起会话导航"} aria-expanded={!navCollapsed} title={navCollapsed ? "展开会话导航" : "收起会话导航"}>{navCollapsed ? "›" : "‹"}</button></div>
          <button type="button" className="run-nav__item run-nav__item--active" title={`当前会话：${currentTitle}`}><span className="run-nav__compact-mark" aria-hidden="true">会</span><span className="run-nav__title">当前会话</span><span className="run-nav__name">{currentTitle}</span>{run && <StatusBadge value={run.run_status} />}</button>
          <p className="nav-hint">此演示会话中的业务状态由服务端 Run 驱动。</p>
        </nav>
        <main className={`conversation${isInitialView ? " conversation--initial" : ""}`} aria-label="患者会话">
          <header className="conversation-header"><div><p className="eyebrow">PATIENT CONVERSATION</p><h2>{currentTitle}</h2></div>{run && <StatusBadge value={run.run_status} />}</header>
          {run && <HandoffBanner run={run} />}
          {error && <Notice kind="error">{error}</Notice>}
          <div ref={conversationFeedRef} className="conversation-feed" aria-live="polite">
            <div className="conversation-content">
              {demoScenario && <DemoScenarioPanel status={demoScenario} busy={busy} onActivate={(scenario) => { void triggerDemoScenario(scenario); }} />}
              {messages.map((item) => <article key={item.id} className={`message message--${item.author}`}><span className="message__author">{item.author === "patient" ? "患者" : item.author === "operator" ? "人工客服" : "Agent"}</span><p>{item.text}</p></article>)}
              {!run && !busy && <ConversationEmptyState onChoosePrompt={chooseInitialPrompt} />}
              {run && <BookingProgress run={run} />}
              {run?.action_required === "SERVICE_SELECTION" && <ServiceOptions run={run} busy={busy} onSelect={(service) => execute(() => selectServiceItem(token, run, service.id))} />}
              {run?.action_required === "DATE_SELECTION" && <AvailableDateOptions run={run} busy={busy} onSelect={(date) => execute(() => selectAvailableDate(token, run, date.date))} />}
              {run?.action_required === "SLOT_SELECTION" && <SlotOptions run={run} busy={busy} onSelect={(slot) => execute(() => selectSlot(token, run, slot.id, slot.version))} />}
              {run?.action_required === "APPOINTMENT_SELECTION" && <AppointmentOptions run={run} busy={busy} onSelect={(appointment) => execute(() => selectAppointment(token, run, appointment.id, appointment.version))} />}
              {run?.action_required === "CONFIRMATION" && <ConfirmationCard run={run} busy={busy} onConfirm={() => execute(() => confirm(token, run))} />}
              <TraceTimeline events={trace} />
              {run && <AppointmentDetailsCard run={run} />}
              {run && <BusinessResult run={run} />}
              <RunStateNotice run={run} busy={busy} />
            </div>
          </div>
          {(canCancel || (run && !handoff && run.run_status !== "COMPLETED")) && <div className="conversation-actions">
            {canCancel && <button type="button" className="text-button" onClick={() => setCancelDialogOpen(true)} disabled={busy}>取消当前流程</button>}
            {run && !handoff && run.run_status !== "COMPLETED" && <button type="button" className="text-button" onClick={() => execute(() => requestHandoff(token, run))} disabled={busy}>请求人工客服</button>}
          </div>}
          <form className="composer" onSubmit={submitMessage}>
            <div className="composer__content">
              <div className="composer__input">
                <label className="sr-only" htmlFor="message">输入预约需求</label>
                <textarea ref={messageInputRef} id="message" value={message} onChange={(event) => setMessage(event.target.value)} placeholder={handoff ? "补充信息给人工客服" : "例如：我想预约明天下午洗牙"} disabled={composerDisabled} rows={2} aria-describedby={handoff ? "handoff-composer-help" : undefined} />
                {!!suggestedReplies.length && canShowSuggestedReplies && <div className="composer__suggestions" role="group" aria-label="快捷回复"><span>快捷回复</span><div>{suggestedReplies.map((reply) => <button key={reply.id} type="button" className="quick-reply" onClick={() => chooseSuggestedReply(reply)}>{reply.label}</button>)}</div></div>}
              </div>
              <button type="submit" className="button button--primary" disabled={composerDisabled || !message.trim()}>{busy ? "处理中…" : "发送"}</button>
            </div>
          </form>
          {handoff && <p id="handoff-composer-help" className="help-text">人工接管期间，Agent 自动执行与业务推进已暂停；你仍可发送补充信息，人工客服会在同一会话中回复。</p>}
        </main>
      </div>
      {cancelDialogOpen && <div className="dialog-backdrop" role="presentation"><section className="dialog" role="dialog" aria-modal="true" aria-labelledby="cancel-title"><h2 id="cancel-title">取消当前流程？</h2><p>这会停止尚未完成的 Agent Run，并使未使用的确认失效；不会取消已经成功的预约。</p><div className="dialog-actions"><button type="button" className="button button--secondary" onClick={() => setCancelDialogOpen(false)} disabled={busy}>继续当前流程</button><button type="button" className="button button--danger" onClick={() => { setCancelDialogOpen(false); void execute(() => cancelRun(token, run!)); }} disabled={busy}>确认取消流程</button></div></section></div>}
      {accountSwitchOpen && <AccountSwitchDialog accounts={demoAccounts} currentRole={actorRole} onClose={closeAccountSwitch} onAuthenticate={authenticate} />}
    </div>
  );
}
