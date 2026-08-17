"""Patient and operator command API."""

from collections import Counter, defaultdict
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from patient_ops_agent.clock import Clock
from patient_ops_agent.domain.models import ManualTaskStatus
from patient_ops_agent.domain.store import InMemoryStore
from patient_ops_agent.security import ActorContext, DemoAuthenticator, issue_actor_token, verify_actor_token
from patient_ops_agent.workflow import AgentWorkflow, WorkflowError


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: str = "web_simulator"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class DemoAccountView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    display_name: str
    actor_role: str


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)


class SlotSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_id: str
    slot_version: int = Field(ge=1)


class ServiceSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_item_id: str = Field(min_length=1, max_length=128)


class DateSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class AppointmentSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appointment_id: str
    appointment_version: int = Field(ge=1)


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_id: str


class HandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason_code: str
    note: Optional[str] = Field(default=None, max_length=1000)


class ResolveTaskRequest(BaseModel):
    resolution: str = Field(min_length=1, max_length=4000)


class OperatorReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)


def create_agent_app(
    workflow: AgentWorkflow,
    store: InMemoryStore,
    clock: Clock,
    token_secret: str,
    lifespan: Optional[Any] = None,
    demo_authenticator: Optional[DemoAuthenticator] = None,
) -> FastAPI:
    app = FastAPI(title="Patient Ops Agent API", version="0.1.0", lifespan=lifespan)
    app.state.workflow = workflow
    app.state.store = store
    authenticator = demo_authenticator or DemoAuthenticator()

    @app.exception_handler(WorkflowError)
    async def workflow_error(_: Request, exc: WorkflowError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code,
            "message": exc.message, "retryable": False, "outcome": "NOT_EXECUTED", "correlation_id": None}})

    async def signed_actor(authorization: Optional[str] = Header(None)) -> ActorContext:
        if not authorization or not authorization.startswith("Bearer "):
            raise WorkflowError("UNAUTHENTICATED", "Bearer actor token is required", 401)
        try:
            return verify_actor_token(authorization[7:], token_secret, clock.now())
        except ValueError as exc:
            raise WorkflowError("UNAUTHENTICATED", str(exc), 401) from exc

    async def actor(current: ActorContext = Depends(signed_actor)) -> ActorContext:
        if current.role != "PATIENT" or not current.patient_id:
            raise WorkflowError("FORBIDDEN", "patient role is required", 403)
        return current

    async def operator(current: ActorContext = Depends(signed_actor)) -> str:
        if current.role != "OPERATOR":
            raise WorkflowError("FORBIDDEN", "operator role is required", 403)
        return current.actor_id

    async def admin(current: ActorContext = Depends(signed_actor)) -> ActorContext:
        if current.role != "ADMIN":
            raise WorkflowError("FORBIDDEN", "admin role is required", 403)
        return current

    @app.get("/health")
    async def health(): return {"status": "ok"}

    @app.get("/api/v1/auth/demo-accounts")
    async def demo_accounts() -> list[DemoAccountView]:
        return [DemoAccountView.model_validate(account) for account in authenticator.list_demo_accounts()]

    @app.post("/api/v1/auth/login")
    async def login(body: LoginRequest):
        current = authenticator.authenticate(body.username, body.password, clock.now())
        if current is None:
            raise WorkflowError("UNAUTHENTICATED", "用户名或密码错误", 401)
        return {
            "access_token": issue_actor_token(current, token_secret),
            "token_type": "bearer",
            "expires_in_seconds": 86400,
            "display_name": current.display_name or current.actor_id,
            "actor_role": current.role,
        }

    @app.post("/api/v1/conversations", status_code=201)
    async def create_conversation(body: CreateConversationRequest, current: ActorContext = Depends(actor),
                                  x_request_id: str = Header(...)):
        key = f"conversation:{current.actor_id}:{x_request_id}"
        prior = store.get_command_result(key)
        if prior is not None: return prior
        conversation = await workflow.create_conversation(current, body.channel)
        result = conversation.model_dump(mode="json", include={"id", "channel", "created_at"})
        result["conversation_id"] = result.pop("id")
        store.save_command_result(key, result)
        return result

    @app.post("/api/v1/conversations/{conversation_id}/messages", status_code=202)
    async def message(conversation_id: str, body: MessageRequest, current: ActorContext = Depends(actor),
                      x_request_id: str = Header(...), x_trace_id: Optional[str] = Header(None)):
        key = f"message:{conversation_id}:{current.actor_id}:{x_request_id}"
        prior = store.get_command_result(key)
        if prior is not None: return prior
        run = await workflow.message(conversation_id, current, body.message, x_trace_id or f"TRACE-{uuid4().hex[:12]}")
        result = {"run_id": run.id, "accepted": True, "run": _run_view(run)}
        store.save_command_result(key, result)
        return result

    @app.post("/api/v1/runs/{run_id}/slot-selection")
    async def slot_selection(run_id: str, body: SlotSelectionRequest, current: ActorContext = Depends(actor),
                             x_request_id: str = Header(...), x_state_version: Optional[int] = Header(None),
                             x_trace_id: Optional[str] = Header(None)):
        run = await workflow.select_slot(run_id, current, body.slot_id, body.slot_version, x_state_version,
                                         x_trace_id or f"TRACE-{uuid4().hex[:12]}")
        return _run_view(run)

    @app.post("/api/v1/runs/{run_id}/service-selection")
    async def service_selection(run_id: str, body: ServiceSelectionRequest, current: ActorContext = Depends(actor),
                                x_request_id: str = Header(...), x_state_version: Optional[int] = Header(None),
                                x_trace_id: Optional[str] = Header(None)):
        run = await workflow.select_service_item(run_id, current, body.service_item_id, x_state_version,
                                                 x_trace_id or f"TRACE-{uuid4().hex[:12]}")
        return _run_view(run)

    @app.post("/api/v1/runs/{run_id}/date-selection")
    async def date_selection(run_id: str, body: DateSelectionRequest, current: ActorContext = Depends(actor),
                             x_request_id: str = Header(...), x_state_version: Optional[int] = Header(None),
                             x_trace_id: Optional[str] = Header(None)):
        run = await workflow.select_available_date(run_id, current, body.date, x_state_version,
                                                   x_trace_id or f"TRACE-{uuid4().hex[:12]}")
        return _run_view(run)

    @app.post("/api/v1/runs/{run_id}/appointment-selection")
    async def appointment_selection(run_id: str, body: AppointmentSelectionRequest, current: ActorContext = Depends(actor),
                                    x_request_id: str = Header(...), x_state_version: Optional[int] = Header(None),
                                    x_trace_id: Optional[str] = Header(None)):
        run = await workflow.select_appointment(run_id, current, body.appointment_id, body.appointment_version,
                                                x_state_version, x_trace_id or f"TRACE-{uuid4().hex[:12]}")
        return _run_view(run)

    @app.post("/api/v1/runs/{run_id}/confirmations", status_code=202)
    async def confirmation(run_id: str, body: ConfirmationRequest, current: ActorContext = Depends(actor),
                           x_request_id: str = Header(...), x_state_version: Optional[int] = Header(None),
                           x_trace_id: Optional[str] = Header(None)):
        key = f"confirm:{run_id}:{current.actor_id}:{x_request_id}"
        prior = store.get_command_result(key)
        if prior is not None: return prior
        run = await workflow.confirm(run_id, current, body.confirmation_id, x_state_version,
                                     x_trace_id or f"TRACE-{uuid4().hex[:12]}")
        result = _run_view(run); store.save_command_result(key, result)
        return result

    @app.post("/api/v1/runs/{run_id}/cancel")
    async def cancel(run_id: str, current: ActorContext = Depends(actor), x_request_id: str = Header(...),
                     x_state_version: Optional[int] = Header(None), x_trace_id: Optional[str] = Header(None)):
        return _run_view(workflow.cancel_run(run_id, current, x_state_version,
                                             x_trace_id or f"TRACE-{uuid4().hex[:12]}"))

    @app.post("/api/v1/runs/{run_id}/handoff", status_code=202)
    async def handoff(run_id: str, body: HandoffRequest, current: ActorContext = Depends(actor),
                      x_request_id: str = Header(...), x_trace_id: Optional[str] = Header(None)):
        return _run_view(workflow.handoff(run_id, current, body.reason_code,
                                          x_trace_id or f"TRACE-{uuid4().hex[:12]}"))

    @app.get("/api/v1/runs/{run_id}")
    async def get_run(run_id: str, current: ActorContext = Depends(actor)):
        run = store.get_run(run_id)
        if not run: raise WorkflowError("INVALID_REQUEST", "run not found", 404)
        if run.patient_id != current.patient_id: raise WorkflowError("FORBIDDEN", "run does not belong to actor", 403)
        return _run_view(run)

    @app.get("/api/v1/runs/{run_id}/trace")
    async def trace(run_id: str, current: ActorContext = Depends(actor)):
        run = store.get_run(run_id)
        if not run: raise WorkflowError("INVALID_REQUEST", "run not found", 404)
        if run.patient_id != current.patient_id: raise WorkflowError("FORBIDDEN", "run does not belong to actor", 403)
        return [event.model_dump(mode="json") for event in store.get_trace(run_id)]

    @app.get("/api/v1/manual-tasks")
    async def manual_tasks(status: Optional[str] = None, operator_id: str = Depends(operator)):
        return [_task_view(item, store.get_run(item.run_id)) for item in store.list_manual_tasks(status)]

    @app.get("/api/v1/manual-tasks/{task_id}/context")
    async def manual_task_context(task_id: str, operator_id: str = Depends(operator)):
        task = store.get_manual_task(task_id)
        if not task: raise WorkflowError("INVALID_REQUEST", "manual task not found", 404)
        run = store.get_run(task.run_id)
        if not run: raise WorkflowError("INVALID_REQUEST", "run not found", 404)
        return {"task": _task_view(task, run), "run": _run_view(run),
                "messages": [item.model_dump(mode="json") for item in run.conversation_messages],
                "trace": [event.model_dump(mode="json") for event in store.get_trace(run.id)]}

    @app.post("/api/v1/manual-tasks/{task_id}/assign")
    async def assign(task_id: str, operator_id: str = Depends(operator), x_request_id: str = Header(...)):
        task = store.get_manual_task(task_id)
        if not task: raise WorkflowError("INVALID_REQUEST", "manual task not found", 404)
        if task.status is not ManualTaskStatus.OPEN: raise WorkflowError("INVALID_REQUEST", "task is not open")
        task.status = ManualTaskStatus.ASSIGNED; task.assigned_operator_id = operator_id
        store.save_manual_task(task); return _task_view(task, store.get_run(task.run_id))

    @app.post("/api/v1/manual-tasks/{task_id}/resolve")
    async def resolve(task_id: str, body: ResolveTaskRequest, operator_id: str = Depends(operator),
                      x_request_id: str = Header(...)):
        task = store.get_manual_task(task_id)
        if not task: raise WorkflowError("INVALID_REQUEST", "manual task not found", 404)
        if task.assigned_operator_id not in (None, operator_id): raise WorkflowError("FORBIDDEN", "task assigned to another operator", 403)
        task.status = ManualTaskStatus.RESOLVED; task.assigned_operator_id = operator_id
        task.resolution = body.resolution; task.completed_at = clock.now(); store.save_manual_task(task)
        return _task_view(task, store.get_run(task.run_id))

    @app.post("/api/v1/manual-tasks/{task_id}/messages")
    async def operator_reply(task_id: str, body: OperatorReplyRequest, operator_id: str = Depends(operator),
                             x_request_id: str = Header(...), x_trace_id: Optional[str] = Header(None)):
        key = f"operator-reply:{task_id}:{operator_id}:{x_request_id}"
        prior = store.get_command_result(key)
        if prior is not None: return prior
        run = workflow.operator_reply(task_id, operator_id, body.message,
                                      x_trace_id or f"TRACE-{uuid4().hex[:12]}")
        result = _run_view(run)
        store.save_command_result(key, result)
        return result

    @app.post("/api/v1/manual-tasks/{task_id}/return-to-agent", status_code=202)
    async def return_to_agent(task_id: str, operator_id: str = Depends(operator), x_request_id: str = Header(...),
                              x_trace_id: Optional[str] = Header(None)):
        return _run_view(workflow.return_to_agent(task_id, operator_id,
                                                  x_trace_id or f"TRACE-{uuid4().hex[:12]}"))

    @app.get("/api/v1/admin/runs")
    async def admin_runs(_: ActorContext = Depends(admin)):
        return [_admin_run_summary(run) for run in store.list_runs()]

    @app.get("/api/v1/admin/dashboard")
    async def admin_dashboard(_: ActorContext = Depends(admin)):
        return _admin_dashboard(store, clock)

    @app.get("/api/v1/admin/runs/{run_id}")
    async def admin_run(run_id: str, _: ActorContext = Depends(admin)):
        run = store.get_run(run_id)
        if not run: raise WorkflowError("INVALID_REQUEST", "run not found", 404)
        return _run_view(run)

    @app.get("/api/v1/admin/runs/{run_id}/trace")
    async def admin_trace(run_id: str, _: ActorContext = Depends(admin)):
        run = store.get_run(run_id)
        if not run: raise WorkflowError("INVALID_REQUEST", "run not found", 404)
        return [event.model_dump(mode="json") for event in store.get_trace(run_id)]

    @app.get("/api/v1/admin/audit")
    async def admin_audit(_: ActorContext = Depends(admin)):
        events = []
        for run in store.list_runs():
            for event in store.get_trace(run.id):
                events.append({"run_id": run.id, "masked_patient_id": _mask_patient_id(run.patient_id),
                               **event.model_dump(mode="json")})
        return sorted(events, key=lambda item: item["timestamp"], reverse=True)

    return app


def _run_view(run):
    return {"run_id": run.id, "conversation_id": run.conversation_id, "operation_id": run.operation_id,
        "masked_patient_id": _mask_patient_id(run.patient_id),
        "intent": run.intent, "run_status": run.run_status.value, "workflow_step": run.workflow_step.value,
        "execution_owner": run.execution_owner.value, "state_version": run.state_version,
        "current_reply": run.current_reply, "current_reply_author": run.current_reply_author,
        "service_item_name": run.service_item_name,
        "requested_date": run.requested_date,
        "suggested_replies": run.suggested_replies,
        "candidate_service_items": run.candidate_service_items,
        "candidate_dates": run.candidate_dates,
        "action_required": run.action_required,
        "selected_slot_id": run.selected_slot_id, "appointment_id": run.appointment_id,
        "confirmation_id": run.confirmation_id, "core_business_status": run.core_business_status.value,
        "writeback_status": run.writeback_status.value, "notification_status": run.notification_status.value,
        "manual_task_id": run.manual_task_id, "candidate_slots": run.candidate_slots,
        "candidate_appointments": run.candidate_appointments, "attempt_count": run.attempt_count,
        "last_error_code": run.last_error_code,
        "recall_status": run.recall_status, "next_best_action": run.next_best_action}


def _task_view(task, run=None):
    return {"task_id": task.id, "run_id": task.run_id, "reason_code": task.reason_code,
            "status": task.status.value, "assigned_operator_id": task.assigned_operator_id,
            "resolution": task.resolution, "created_at": task.created_at,
            "masked_patient_id": _mask_patient_id(task.patient_id),
            "intent": run.intent if run is not None else None}


def _admin_run_summary(run):
    return {"run_id": run.id, "masked_patient_id": _mask_patient_id(run.patient_id), "intent": run.intent,
            "run_status": run.run_status.value, "workflow_step": run.workflow_step.value,
            "execution_owner": run.execution_owner.value, "manual_task_id": run.manual_task_id,
            "last_error_code": run.last_error_code, "started_at": run.started_at}


def _admin_dashboard(store: InMemoryStore, clock: Clock) -> dict[str, Any]:
    """Return a read-only, server-derived operating overview for Admin users."""
    runs = store.list_runs()
    statuses = Counter(run.run_status.value for run in runs)
    intents = Counter(run.intent or "UNKNOWN" for run in runs)
    create_runs = [run for run in runs if run.intent == "CREATE_APPOINTMENT"]
    terminal_statuses = {"COMPLETED", "COMPLETED_WITH_PENDING_SIDE_EFFECTS", "FAILED", "CANCELLED_BY_PATIENT"}
    terminal_create_runs = [run for run in create_runs if run.run_status.value in terminal_statuses]
    successful_appointments = [run for run in create_runs if run.core_business_status.value == "SUCCEEDED"]
    traces_by_run = {run.id: store.get_trace(run.id) for run in runs}
    slot_found_runs = [run for run in create_runs if any(event.event in {"slots_returned", "alternative_slots_returned"}
                       for event in traces_by_run[run.id])]
    confirmation_runs = [run for run in create_runs if any(event.event == "confirmation_prepared"
                         for event in traces_by_run[run.id])]
    waiting_human_runs = [run for run in runs if run.run_status.value == "WAITING_HUMAN"]
    failed_runs = [run for run in runs if run.run_status.value == "FAILED"]
    pending_side_effect_runs = [run for run in runs if run.run_status.value == "COMPLETED_WITH_PENDING_SIDE_EFFECTS"]
    security_run_ids = [run.id for run in runs if any(event.event == "policy_denied" for event in traces_by_run[run.id])]
    error_counts = Counter(run.last_error_code for run in runs if run.last_error_code)
    daily = defaultdict(lambda: {"total_runs": 0, "successful_appointments": 0, "waiting_human": 0})
    for run in runs:
        day = run.started_at.date().isoformat()
        daily[day]["total_runs"] += 1
        if run in successful_appointments:
            daily[day]["successful_appointments"] += 1
        if run.run_status.value == "WAITING_HUMAN":
            daily[day]["waiting_human"] += 1

    action_items = []
    if waiting_human_runs:
        action_items.append({"kind": "HUMAN_HANDOFF", "severity": "warning", "count": len(waiting_human_runs),
                             "run_ids": [run.id for run in waiting_human_runs]})
    if failed_runs:
        action_items.append({"kind": "FAILED_RUN", "severity": "danger", "count": len(failed_runs),
                             "run_ids": [run.id for run in failed_runs]})
    if pending_side_effect_runs:
        action_items.append({"kind": "PENDING_SIDE_EFFECT", "severity": "warning", "count": len(pending_side_effect_runs),
                             "run_ids": [run.id for run in pending_side_effect_runs]})
    if security_run_ids:
        action_items.append({"kind": "SECURITY_INCIDENT", "severity": "danger", "count": len(security_run_ids),
                             "run_ids": security_run_ids})
    if not action_items:
        action_items.append({"kind": "SYSTEM_HEALTHY", "severity": "success", "count": 0, "run_ids": []})

    completion_rate = round(len(successful_appointments) * 100 / len(terminal_create_runs), 1) if terminal_create_runs else None
    return {
        "generated_at": clock.now().isoformat(),
        "metrics": {
            "total_runs": len(runs),
            "successful_appointments": len(successful_appointments),
            "appointment_completion_rate": completion_rate,
            "waiting_patient": statuses["WAITING_PATIENT"],
            "waiting_human": len(waiting_human_runs),
            "pending_side_effects": len(pending_side_effect_runs),
            "failed_runs": len(failed_runs),
            "security_incidents": len(security_run_ids),
        },
        "status_distribution": [{"key": key, "count": count} for key, count in sorted(statuses.items())],
        "intent_distribution": [{"key": key, "count": count} for key, count in sorted(intents.items())],
        "funnel": [
            {"key": "CREATE_REQUESTED", "count": len(create_runs)},
            {"key": "SLOT_FOUND", "count": len(slot_found_runs)},
            {"key": "CONFIRMATION_PREPARED", "count": len(confirmation_runs)},
            {"key": "APPOINTMENT_SUCCEEDED", "count": len(successful_appointments)},
        ],
        "daily_trend": [{"date": date, **values} for date, values in sorted(daily.items())],
        "error_distribution": [{"key": key, "count": count} for key, count in error_counts.most_common()],
        "action_items": action_items,
    }


def _mask_patient_id(patient_id: str) -> str:
    return patient_id[:1] + "•••" + patient_id[-1:] if patient_id else "—"
