"""Deterministic, event-oriented appointment workflow."""

import hashlib
import json
import re
from datetime import date, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4

from patient_ops_agent.clock import Clock
from patient_ops_agent.domain.models import (
    AgentRun,
    ConfirmationRecord,
    ConfirmationStatus,
    Conversation,
    ConversationMessage,
    CoreBusinessStatus,
    ManualTask,
    OutboxEvent,
    SideEffectStatus,
    ToolExecution,
    TraceEvent,
)
from patient_ops_agent.domain.store import InMemoryStore
from patient_ops_agent.gateways import ClinicCoreGateway, GatewayError, PatientOpsGateway
from patient_ops_agent.llm import UnderstandingProvider, UnderstandingRequest
from patient_ops_agent.models import AgentRunStatus, ExecutionOwner, Intent, WorkflowStep
from patient_ops_agent.policy import PolicyEngine
from patient_ops_agent.security import ActorContext


class WorkflowError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def parameter_hash(parameters: Dict[str, Any]) -> str:
    value = json.dumps(parameters, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


class AgentWorkflow:
    TERMINAL = {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.COMPLETED_WITH_PENDING_SIDE_EFFECTS,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED_BY_PATIENT,
    }

    def __init__(self, store: InMemoryStore, patient_ops: PatientOpsGateway, clinic: ClinicCoreGateway,
                 understanding: UnderstandingProvider, policy: PolicyEngine, clock: Clock,
                 confirmation_ttl_seconds: int = 300, max_retry_attempts: int = 3) -> None:
        self.store = store
        self.patient_ops = patient_ops
        self.clinic = clinic
        self.understanding = understanding
        self.policy = policy
        self.clock = clock
        self.confirmation_ttl_seconds = confirmation_ttl_seconds
        self.max_retry_attempts = max_retry_attempts
        self._last_audited_state: Dict[str, Dict[str, Any]] = {}

    async def create_conversation(self, actor: ActorContext, channel: str) -> Conversation:
        conversation = Conversation(id=f"CONV-{uuid4().hex[:12]}", channel=channel, actor_id=actor.actor_id,
                                    patient_id=actor.patient_id, created_at=self.clock.now())
        self.store.add_conversation(conversation)
        return conversation

    async def message(self, conversation_id: str, actor: ActorContext, text: str, trace_id: str) -> AgentRun:
        conversation = self._conversation(conversation_id, actor)
        run = self.store.latest_run(conversation_id)
        if run is None or run.run_status in self.TERMINAL:
            run = AgentRun(id=f"RUN-{uuid4().hex[:12]}", conversation_id=conversation.id,
                patient_id=actor.patient_id, actor_id=actor.actor_id,
                verification_level=actor.verification_level, verified_at=actor.verified_at,
                started_at=self.clock.now(), workflow_step=WorkflowStep.LOADING_PATIENT_CONTEXT)
            run = self.store.save_run(run)
            self._trace(run, trace_id, "run_created", "INIT")
        run.suggested_replies = []
        run = self._record_conversation_message(run, "PATIENT", text, trace_id)
        if run.execution_owner is ExecutionOwner.OPERATOR:
            return run
        await self._load_context(run, trace_id)
        if run.workflow_step is WorkflowStep.WAITING_APPOINTMENT_SELECTION:
            selected = next((item for item in run.candidate_appointments if item["id"] in text), None)
            if selected:
                return self._prepare_cancel_confirmation(run, selected, trace_id)
            run.current_reply = "请回复候选列表中的预约编号。"
            return self._save(run)
        result = await self.understanding.understand(UnderstandingRequest(message=text, current_fields={
            "intent": run.intent, "service_item_id": run.service_item_id, "requested_date": run.requested_date}))
        self._trace(run, trace_id, "understanding_produced", "UNDERSTANDING_REQUEST",
                    details={"intent": result.intent.value, "confidence": result.confidence,
                             "proposed_action": result.proposed_action.value})
        intent = result.intent
        if run.intent == Intent.CREATE_APPOINTMENT.value and intent is Intent.UNKNOWN:
            intent = Intent.CREATE_APPOINTMENT
        if intent is Intent.REQUEST_HUMAN:
            return self.handoff(run.id, actor, "PATIENT_REQUESTED", trace_id)
        if intent is Intent.CANCEL_CURRENT_RUN:
            return self.cancel_run(run.id, actor, run.state_version, trace_id)
        if intent is Intent.QUERY_SLOT_AVAILABILITY:
            return await self._search_alternative_slots(run, trace_id)
        if intent is Intent.CREATE_APPOINTMENT:
            run.intent = intent.value
            return await self._handle_create_message(run, result, text, trace_id)
        if intent is Intent.QUERY_APPOINTMENT:
            run.intent = intent.value
            return await self._query_appointments(run, False, trace_id)
        if intent is Intent.CANCEL_APPOINTMENT:
            run.intent = intent.value
            requested_patient = re.search(r"P\d+", text, re.I)
            if requested_patient and requested_patient.group(0).upper() != actor.patient_id:
                run.last_error_code = "FORBIDDEN"; run.current_reply = "不能访问或取消其他患者的预约。"
                run.run_status = AgentRunStatus.FAILED; run.workflow_step = WorkflowStep.TERMINAL
                run.completed_at = self.clock.now(); run = self._save(run)
                self._trace(run, trace_id, "policy_denied", "VALIDATING_EXECUTION", status="FORBIDDEN",
                            details={"security_event": "cross_patient_resource_request"})
                return run
            return await self._query_appointments(run, True, trace_id)
        if intent is Intent.FOLLOW_UP:
            run.intent = intent.value
            return await self._handle_follow_up(run, trace_id)
        run.intent = intent.value
        run.workflow_step = WorkflowStep.COLLECTING_REQUIREMENTS
        run.run_status = AgentRunStatus.WAITING_PATIENT
        run.current_reply = "我可以帮你创建、查询或取消预约，也可以转接人工客服。"
        return self._save(run)

    async def _load_context(self, run: AgentRun, trace_id: str) -> None:
        if run.workflow_step is not WorkflowStep.LOADING_PATIENT_CONTEXT:
            return
        try:
            context = await self.patient_ops.context(run.patient_id)
        except GatewayError as exc:
            raise WorkflowError(exc.code, exc.message, 404) from exc
        if context.get("status") != "ACTIVE":
            raise WorkflowError("FORBIDDEN", "patient is inactive", 403)
        run.workflow_step = WorkflowStep.UNDERSTANDING_REQUEST
        self._save(run)
        self._trace(run, trace_id, "patient_context_loaded", "LOADING_PATIENT_CONTEXT")

    async def _handle_create_message(self, run: AgentRun, result: Any, text: str, trace_id: str) -> AgentRun:
        changed = False
        if result.requested_date and str(result.requested_date) != run.requested_date:
            run.requested_date = str(result.requested_date); changed = True
        if result.requested_period and result.requested_period.value != run.requested_period:
            run.requested_period = result.requested_period.value; changed = True
        if result.service_item_text:
            services = await self.clinic.service_items()
            service = next((item for item in services if item["name"] == result.service_item_text), None)
            if service:
                if service["id"] != run.service_item_id:
                    run.service_item_id = service["id"]; changed = True
                run.service_item_name = service["name"]
        clinics = await self.clinic.clinics()
        if result.clinic_text:
            clinic = next((item for item in clinics if result.clinic_text in item["name"]), None)
            if clinic and clinic["id"] != run.clinic_id: run.clinic_id = clinic["id"]; changed = True
        elif len(clinics) == 1:
            run.clinic_id = clinics[0]["id"]
        if result.doctor_text:
            doctors = await self.clinic.doctors(run.clinic_id)
            doctor = next((item for item in doctors if item["name"] == result.doctor_text), None)
            if doctor and doctor["id"] != run.doctor_id: run.doctor_id = doctor["id"]; changed = True
        if changed and run.confirmation_id:
            confirmation = self.store.get_confirmation(run.confirmation_id)
            if confirmation:
                confirmation.status = ConfirmationStatus.INVALIDATED; self.store.save_confirmation(confirmation)
            run.confirmation_id = None
            self._trace(run, trace_id, "confirmation_invalidated", "UNDERSTANDING_REQUEST")
        if not run.service_item_id:
            return await self._present_service_selection(run, trace_id)
        if not run.requested_date:
            return await self._present_available_dates(run, trace_id)
        existing = await self.clinic.patient_appointments(run.patient_id)
        duplicate = next((item for item in existing if item.service_item_id == run.service_item_id
                          and item.start_at and str(item.start_at.date()) == run.requested_date), None)
        if duplicate:
            run.appointment_id = duplicate.id
            run.core_business_status = CoreBusinessStatus.SUCCEEDED
            run.writeback_status = SideEffectStatus.NOT_REQUIRED
            run.notification_status = SideEffectStatus.NOT_REQUIRED
            run.run_status = AgentRunStatus.COMPLETED
            run.workflow_step = WorkflowStep.TERMINAL
            run.completed_at = self.clock.now()
            run.current_reply = f"已存在匹配的预约 {duplicate.id}，未重复创建。"
            run.action_required = "NONE"
            saved = self._save(run)
            self._trace(saved, trace_id, "duplicate_request_suppressed", "UNDERSTANDING_REQUEST",
                        status="EXISTING_APPOINTMENT_FOUND", details={"appointment_id": duplicate.id})
            return saved
        return await self._search_slots(run, trace_id)

    async def _handle_follow_up(self, run: AgentRun, trace_id: str) -> AgentRun:
        """Follow-up / recall slice: recommend a cleaning review from patient facts.

        读取 Patient Ops 的患者事实（last_cleaning_date），若距上次洗牙超过 5 个月则
        预填洗牙服务并引导到既有日期选择管线；若未到期或缺少事实，则给出确定性
        降级回复，不擅自发起任何预约写操作。
        """
        facts = await self.patient_ops.facts(run.patient_id)
        cleaning_fact = next((item for item in facts if item.get("fact_type") == "last_cleaning_date"), None)
        if not cleaning_fact or not cleaning_fact.get("value"):
            run.workflow_step = WorkflowStep.COLLECTING_REQUIREMENTS
            run.run_status = AgentRunStatus.WAITING_PATIENT
            run.action_required = "NONE"
            run.current_reply = "暂时没有找到适合您的复查建议。您可以告诉我需要预约的服务和日期，我来帮您安排。"
            saved = self._save(run)
            self._trace(saved, trace_id, "follow_up_no_applicable_fact", "UNDERSTANDING_REQUEST",
                        status="NO_APPLICABLE_FACT", details={"patient_id": run.patient_id})
            return saved
        try:
            last_date = date.fromisoformat(str(cleaning_fact["value"]))
        except (TypeError, ValueError):
            run.current_reply = "暂时没有找到适合您的复查建议。您可以告诉我需要预约的服务和日期，我来帮您安排。"
            saved = self._save(run)
            self._trace(saved, trace_id, "follow_up_invalid_fact", "UNDERSTANDING_REQUEST",
                        status="NO_APPLICABLE_FACT", details={"patient_id": run.patient_id})
            return saved
        today = self.clock.now().date()
        months_ago = (today.year - last_date.year) * 12 + (today.month - last_date.month)
        if today.day < last_date.day:
            months_ago -= 1
        if months_ago < 5:
            run.workflow_step = WorkflowStep.COLLECTING_REQUIREMENTS
            run.run_status = AgentRunStatus.WAITING_PATIENT
            run.action_required = "NONE"
            run.current_reply = f"您上次洗牙是 {last_date.isoformat()}，距今约 {months_ago} 个月，暂未到常规复查周期。"
            saved = self._save(run)
            self._trace(saved, trace_id, "follow_up_not_yet_due", "UNDERSTANDING_REQUEST",
                        status="NOT_YET_DUE", details={"last_cleaning_date": last_date.isoformat()})
            return saved
        run.service_item_id = "SV-CLEANING"
        run.service_item_name = "洗牙"
        clinics = await self.clinic.clinics()
        if len(clinics) == 1:
            run.clinic_id = clinics[0]["id"]
        self._trace(run, trace_id, "follow_up_recommendation_made", "UNDERSTANDING_REQUEST",
                    status="RECOMMENDED", details={
                        "service_item_id": "SV-CLEANING",
                        "last_cleaning_date": last_date.isoformat(),
                        "months_ago": months_ago,
                    })
        return await self._present_available_dates(
            run, trace_id,
            reply_override=f"您上次洗牙是 {last_date.isoformat()}，距今约 {months_ago} 个月，建议安排一次复查。请选择可约日期：",
        )

    async def _present_service_selection(self, run: AgentRun, trace_id: str, reply_override: Optional[str] = None) -> AgentRun:
        """Project active Clinic Core services when the booking service is still unknown."""

        services = await self.clinic.service_items()
        run.candidate_service_items = [
            {"id": item["id"], "name": item["name"], "duration_minutes": item["duration_minutes"]}
            for item in services
        ]
        run.candidate_dates = []
        run.candidate_slots = []
        run.candidate_slot_ids = []
        run.workflow_step = WorkflowStep.COLLECTING_REQUIREMENTS
        run.run_status = AgentRunStatus.WAITING_PATIENT
        run.action_required = "SERVICE_SELECTION"
        run.current_reply = reply_override or (
            f"已记录您希望预约 {run.requested_date}，请选择服务项目。"
            if run.requested_date else "想预约哪项服务？请先选择服务项目。"
        )
        saved = self._save(run)
        self._trace(saved, trace_id, "service_items_presented", "COLLECTING_REQUIREMENTS",
                    tool_name="get_service_items", status="SUCCEEDED",
                    details={"service_item_ids": [item["id"] for item in saved.candidate_service_items]})
        return saved

    async def _present_available_dates(self, run: AgentRun, trace_id: str,
                                       reply_override: Optional[str] = None) -> AgentRun:
        """Project only dates with real available slots for the selected service.

        当所选服务项目未来 7 天内没有任何可约日期时，不停留在死胡同，而是清空已选
        服务项目并退回服务项目选择步骤，让患者可以直接换一个服务项目继续，而不必
        依赖自由文本二次表达。
        """

        start_date = self.clock.now().date()
        end_date = start_date + timedelta(days=6)
        service_name = await self._service_name(run.service_item_id)
        slots = await self.clinic.search_slots(
            service_item_id=run.service_item_id,
            clinic_id=run.clinic_id,
            doctor_id=run.doctor_id,
            start_date=start_date,
            end_date=end_date,
        )
        counts: Dict[str, int] = {}
        for slot in slots:
            value = slot.start_at.date().isoformat()
            counts[value] = counts.get(value, 0) + 1
        candidate_dates = [
            {"date": value, "available_slot_count": count}
            for value, count in sorted(counts.items())
        ]
        if not candidate_dates:
            run.service_item_id = None
            run.service_item_name = None
            saved = await self._present_service_selection(
                run, trace_id, reply_override=f"{service_name}在未来 7 天暂时没有可约时段，请换一个服务项目。"
            )
            self._trace(saved, trace_id, "available_dates_empty_restarts_service_selection", "SEARCHING_SLOTS",
                        tool_name="search_available_slots", status="NO_RESULT",
                        details={"start_date": str(start_date), "end_date": str(end_date)})
            return saved
        run.candidate_dates = candidate_dates
        run.candidate_service_items = []
        run.candidate_slots = []
        run.candidate_slot_ids = []
        run.workflow_step = WorkflowStep.COLLECTING_REQUIREMENTS
        run.run_status = AgentRunStatus.WAITING_PATIENT
        run.action_required = "DATE_SELECTION"
        run.current_reply = reply_override or f"已选择{service_name}，请选择可约日期。"
        saved = self._save(run)
        self._trace(saved, trace_id, "available_dates_presented", "SEARCHING_SLOTS",
                    tool_name="search_available_slots", status="SUCCEEDED",
                    details={"start_date": str(start_date), "end_date": str(end_date),
                             "candidate_dates": saved.candidate_dates})
        return saved

    async def select_service_item(self, run_id: str, actor: ActorContext, service_item_id: str,
                                  state_version: Optional[int], trace_id: str) -> AgentRun:
        run = self._owned_run(run_id, actor, state_version)
        if run.execution_owner is not ExecutionOwner.AGENT:
            raise WorkflowError("FORBIDDEN", "run is not under agent control", 403)
        if run.action_required != "SERVICE_SELECTION":
            raise WorkflowError("INVALID_REQUEST", "service is not awaiting selection")
        selected = next((item for item in run.candidate_service_items if item["id"] == service_item_id), None)
        if selected is None:
            raise WorkflowError("INVALID_REQUEST", "service is not an active candidate")
        run.service_item_id = selected["id"]
        run.service_item_name = selected["name"]
        run.candidate_service_items = []
        run.candidate_dates = []
        run.candidate_slots = []
        run.candidate_slot_ids = []
        self._trace(run, trace_id, "service_item_selected", "COLLECTING_REQUIREMENTS",
                    details={"service_item_id": selected["id"]})
        if run.requested_date:
            return await self._search_slots(run, trace_id)
        return await self._present_available_dates(run, trace_id)

    async def select_available_date(self, run_id: str, actor: ActorContext, selected_date: str,
                                    state_version: Optional[int], trace_id: str) -> AgentRun:
        run = self._owned_run(run_id, actor, state_version)
        if run.execution_owner is not ExecutionOwner.AGENT:
            raise WorkflowError("FORBIDDEN", "run is not under agent control", 403)
        if run.action_required != "DATE_SELECTION":
            raise WorkflowError("INVALID_REQUEST", "date is not awaiting selection")
        if selected_date not in {item["date"] for item in run.candidate_dates}:
            raise WorkflowError("INVALID_REQUEST", "date is not an active candidate")
        run.requested_date = selected_date
        run.requested_period = None
        run.candidate_dates = []
        self._trace(run, trace_id, "available_date_selected", "COLLECTING_REQUIREMENTS",
                    details={"requested_date": selected_date})
        return await self._search_slots(run, trace_id)

    async def _service_name(self, service_item_id: Optional[str]) -> str:
        services = await self.clinic.service_items()
        service = next((item for item in services if item["id"] == service_item_id), None)
        return service["name"] if service else (service_item_id or "该服务")

    async def _search_slots(self, run: AgentRun, trace_id: str) -> AgentRun:
        run.workflow_step = WorkflowStep.SEARCHING_SLOTS
        run.candidate_service_items = []
        run.candidate_dates = []
        slots = await self.clinic.search_slots(service_item_id=run.service_item_id,
            clinic_id=run.clinic_id, doctor_id=run.doctor_id, start_date=run.requested_date,
            end_date=run.requested_date, period=run.requested_period)
        run.candidate_slots = [slot.model_dump(mode="json") for slot in slots]
        run.candidate_slot_ids = [slot.id for slot in slots]
        if not slots:
            run.workflow_step = WorkflowStep.COLLECTING_REQUIREMENTS
            run.run_status = AgentRunStatus.WAITING_PATIENT
            period = {"MORNING": "上午", "AFTERNOON": "下午", "EVENING": "晚上"}.get(run.requested_period, "")
            run.current_reply = (
                f"{run.requested_date}{period}暂时没有可用号源。"
                "您可以查看未来 7 天可约时段（回复“有哪些日期可约”），"
                "或告诉我更方便的日期、时段或医生。"
            )
            run.suggested_replies = [{
                "id": "view_next_7_days",
                "label": "查看未来 7 天可约时段",
                "message": "有哪些日期可约",
                "mode": "FILL_COMPOSER",
            }]
            run.action_required = "NONE"
        else:
            run.workflow_step = WorkflowStep.WAITING_SELECTION
            run.run_status = AgentRunStatus.WAITING_PATIENT
            run.current_reply = f"找到 {len(slots)} 个可用号源，请选择。"
            run.action_required = "SLOT_SELECTION"
        saved = self._save(run)
        self._trace(saved, trace_id, "slots_returned", "SEARCHING_SLOTS", tool_name="search_available_slots",
                    status="SUCCEEDED", details={"candidate_slot_ids": saved.candidate_slot_ids})
        return saved

    async def _search_alternative_slots(self, run: AgentRun, trace_id: str) -> AgentRun:
        """Return read-only alternatives after a patient explicitly asks for them."""

        if run.intent != Intent.CREATE_APPOINTMENT.value or not run.service_item_id or not run.requested_date:
            run.workflow_step = WorkflowStep.COLLECTING_REQUIREMENTS
            run.run_status = AgentRunStatus.WAITING_PATIENT
            run.action_required = "NONE"
            run.current_reply = "请先告诉我需要预约的服务项目和日期，我再为您查看可约时段。"
            return self._save(run)

        start_date = date.fromisoformat(run.requested_date)
        end_date = start_date + timedelta(days=6)
        run.workflow_step = WorkflowStep.SEARCHING_SLOTS
        run.candidate_service_items = []
        run.candidate_dates = []
        slots = await self.clinic.search_slots(
            service_item_id=run.service_item_id,
            clinic_id=run.clinic_id,
            doctor_id=run.doctor_id,
            start_date=start_date,
            end_date=end_date,
        )
        run.candidate_slots = [slot.model_dump(mode="json") for slot in slots]
        run.candidate_slot_ids = [slot.id for slot in slots]
        if slots:
            run.workflow_step = WorkflowStep.WAITING_SELECTION
            run.run_status = AgentRunStatus.WAITING_PATIENT
            run.action_required = "SLOT_SELECTION"
            run.current_reply = f"从 {start_date} 起未来 7 天找到 {len(slots)} 个可约时段，请选择。"
        else:
            run.workflow_step = WorkflowStep.COLLECTING_REQUIREMENTS
            run.run_status = AgentRunStatus.WAITING_PATIENT
            run.action_required = "NONE"
            run.current_reply = f"从 {start_date} 起未来 7 天暂时没有可用号源，请换一个日期、服务项目或医生。"
        saved = self._save(run)
        self._trace(
            saved,
            trace_id,
            "alternative_slots_returned",
            "SEARCHING_SLOTS",
            tool_name="search_available_slots",
            status="SUCCEEDED",
            details={"start_date": str(start_date), "end_date": str(end_date),
                     "candidate_slot_ids": saved.candidate_slot_ids},
        )
        return saved

    async def select_slot(self, run_id: str, actor: ActorContext, slot_id: str, slot_version: int,
                          state_version: Optional[int], trace_id: str) -> AgentRun:
        run = self._owned_run(run_id, actor, state_version)
        if run.workflow_step is not WorkflowStep.WAITING_SELECTION or slot_id not in run.candidate_slot_ids:
            raise WorkflowError("INVALID_REQUEST", "slot is not an active candidate")
        slot = next(item for item in run.candidate_slots if item["id"] == slot_id)
        if slot["version"] != slot_version:
            raise WorkflowError("STATE_VERSION_CONFLICT", "candidate slot version mismatch")
        run.selected_slot_id = slot_id; run.selected_slot_version = slot_version
        run.clinic_id = slot["clinic_id"]; run.doctor_id = slot["doctor_id"]; run.service_item_id = slot["service_item_id"]
        run.service_item_name = await self._service_name(run.service_item_id)
        parameters = {"action_type": "CREATE_APPOINTMENT", "patient_id": run.patient_id,
            "clinic_id": run.clinic_id, "service_item_id": run.service_item_id, "doctor_id": run.doctor_id,
            "slot_id": slot_id, "slot_version": slot_version, "start_at": slot["start_at"]}
        confirmation = self._new_confirmation(run, "CREATE_APPOINTMENT", slot_id, slot_version, parameters)
        run.confirmation_id = confirmation.id; run.workflow_step = WorkflowStep.WAITING_CONFIRMATION
        run.run_status = AgentRunStatus.WAITING_PATIENT; run.action_required = "CONFIRMATION"
        run.current_reply = (f"请确认预约：诊所 {run.clinic_id}，服务 {run.service_item_id}，医生 {run.doctor_id}，"
                             f"时间 {slot['start_at']}。")
        saved = self._save(run)
        self._trace(saved, trace_id, "confirmation_prepared", "PREPARING_CONFIRMATION",
                    details={"confirmation_id": confirmation.id, "parameter_hash": confirmation.parameter_hash})
        return saved

    async def select_appointment(self, run_id: str, actor: ActorContext, appointment_id: str,
                                 appointment_version: int, state_version: Optional[int], trace_id: str) -> AgentRun:
        run = self._owned_run(run_id, actor, state_version)
        if run.workflow_step is not WorkflowStep.WAITING_APPOINTMENT_SELECTION:
            raise WorkflowError("INVALID_REQUEST", "appointment is not awaiting selection")
        appointment = next((item for item in run.candidate_appointments if item["id"] == appointment_id), None)
        if appointment is None:
            raise WorkflowError("INVALID_REQUEST", "appointment is not an active candidate")
        if appointment["version"] != appointment_version:
            raise WorkflowError("STATE_VERSION_CONFLICT", "candidate appointment version mismatch")
        self._trace(run, trace_id, "appointment_selected", "WAITING_APPOINTMENT_SELECTION",
                    details={"appointment_id": appointment_id, "appointment_version": appointment_version})
        return self._prepare_cancel_confirmation(run, appointment, trace_id)

    async def _query_appointments(self, run: AgentRun, for_cancel: bool, trace_id: str) -> AgentRun:
        run.workflow_step = WorkflowStep.QUERYING_APPOINTMENTS
        appointments = await self.clinic.patient_appointments(run.patient_id)
        run.candidate_appointments = [item.model_dump(mode="json") for item in appointments]
        self._trace(run, trace_id, "appointments_returned", "QUERYING_APPOINTMENTS",
                    tool_name="get_patient_appointments", status="SUCCEEDED", details={"count": len(appointments)})
        if not for_cancel:
            run.run_status = AgentRunStatus.COMPLETED; run.workflow_step = WorkflowStep.TERMINAL
            run.completed_at = self.clock.now(); run.core_business_status = CoreBusinessStatus.SUCCEEDED
            run.current_reply = "暂无未来预约。" if not appointments else f"为您查询到 {len(appointments)} 个未来预约，详细信息如下。"
            return self._save(run)
        if not appointments:
            run.run_status = AgentRunStatus.COMPLETED; run.workflow_step = WorkflowStep.TERMINAL
            run.completed_at = self.clock.now(); run.current_reply = "没有可取消的未来预约。"
            return self._save(run)
        run.workflow_step = WorkflowStep.WAITING_APPOINTMENT_SELECTION
        run.run_status = AgentRunStatus.WAITING_PATIENT; run.action_required = "APPOINTMENT_SELECTION"
        run.current_reply = "请选择要取消的预约；选择后还需要确认。"
        return self._save(run)

    def _prepare_cancel_confirmation(self, run: AgentRun, appointment: Dict[str, Any], trace_id: str) -> AgentRun:
        run.appointment_id = appointment["id"]; run.appointment_version = appointment["version"]
        parameters = {"action_type": "CANCEL_APPOINTMENT", "patient_id": run.patient_id,
            "appointment_id": appointment["id"], "appointment_version": appointment["version"]}
        confirmation = self._new_confirmation(run, "CANCEL_APPOINTMENT", appointment["id"],
                                              appointment["version"], parameters)
        run.confirmation_id = confirmation.id; run.workflow_step = WorkflowStep.WAITING_CONFIRMATION
        run.run_status = AgentRunStatus.WAITING_PATIENT; run.action_required = "CONFIRMATION"
        run.current_reply = f"请确认取消预约 {appointment['id']}（时间 {appointment.get('start_at', '未知')}）。"
        saved = self._save(run)
        self._trace(saved, trace_id, "cancellation_confirmation_prepared", "PREPARING_CONFIRMATION")
        return saved

    def _new_confirmation(self, run: AgentRun, action: str, target: str, version: int,
                          parameters: Dict[str, Any]) -> ConfirmationRecord:
        confirmation = ConfirmationRecord(id=f"CONF-{uuid4().hex[:12]}", run_id=run.id, patient_id=run.patient_id,
            action_type=action, target_id=target, parameters=parameters, parameter_hash=parameter_hash(parameters),
            resource_version=version, expires_at=self.clock.now() + timedelta(seconds=self.confirmation_ttl_seconds))
        self.store.add_confirmation(confirmation)
        return confirmation

    async def confirm(self, run_id: str, actor: ActorContext, confirmation_id: str,
                      state_version: Optional[int], trace_id: str) -> AgentRun:
        run = self._owned_run(run_id, actor, state_version)
        confirmation = self.store.get_confirmation(confirmation_id)
        if not confirmation or run.confirmation_id != confirmation_id:
            raise WorkflowError("INVALID_REQUEST", "confirmation is not bound to this run")
        if confirmation.expires_at <= self.clock.now():
            confirmation.status = ConfirmationStatus.EXPIRED; self.store.save_confirmation(confirmation)
            raise WorkflowError("INVALID_REQUEST", "confirmation expired")
        confirmation.status = ConfirmationStatus.CONFIRMED; confirmation.confirmed_at = self.clock.now()
        self.store.save_confirmation(confirmation)
        decision = self.policy.authorize_high_risk(run, confirmation, actor.patient_id,
            parameter_hash(confirmation.parameters), run.patient_id, self.clock.now())
        self._trace(run, trace_id, "policy_decision", "VALIDATING_EXECUTION", status=decision.code,
                    details={"allowed": decision.allowed})
        if not decision.allowed:
            raise WorkflowError("FORBIDDEN", decision.code, 403)
        run.operation_id = run.operation_id or f"OP-{uuid4().hex[:16]}"
        confirmation.status = ConfirmationStatus.CONSUMED; self.store.save_confirmation(confirmation)
        run.workflow_step = WorkflowStep.EXECUTING_CORE_ACTION
        run.core_business_status = CoreBusinessStatus.EXECUTING; run.action_required = "NONE"
        run = self._save(run)
        return await self._execute_core(run, confirmation, trace_id)

    async def _execute_core(self, run: AgentRun, confirmation: ConfirmationRecord, trace_id: str) -> AgentRun:
        payload = dict(confirmation.parameters)
        payload.pop("action_type", None); payload.pop("start_at", None)
        if confirmation.action_type == "CREATE_APPOINTMENT":
            payload["operation_id"] = run.operation_id
            payload["expected_slot_version"] = payload.pop("slot_version")
            tool = "create_appointment"
        else:
            payload = {"operation_id": run.operation_id, "patient_id": run.patient_id,
                       "expected_appointment_version": payload["appointment_version"]}
            tool = "cancel_appointment"
        for attempt in range(1, self.max_retry_attempts + 1):
            run.attempt_count = attempt
            started = self.clock.now()
            try:
                if tool == "create_appointment":
                    response = await self.clinic.create_appointment(payload, run.operation_id)
                else:
                    response = await self.clinic.cancel_appointment(run.appointment_id, payload, run.operation_id)
                self._tool(run, tool, attempt, payload, response, "SUCCEEDED", None, started)
                return await self._verify_core(run, confirmation, response, trace_id)
            except GatewayError as exc:
                self._tool(run, tool, attempt, payload, {}, "FAILED", exc.code, started)
                run.last_error_code = exc.code; run.last_error_message = exc.message
                if exc.outcome == "UNKNOWN":
                    run.core_business_status = CoreBusinessStatus.OUTCOME_UNKNOWN
                    run.run_status = AgentRunStatus.RECONCILING
                    run.workflow_step = WorkflowStep.RECONCILING_CORE_RESULT
                    run = self._save(run)
                    self._trace(run, trace_id, "tool_outcome_unknown", "EXECUTING_CORE_ACTION", tool_name=tool,
                                status=exc.code)
                    return await self.reconcile(run.id, trace_id)
                if exc.code in ("SLOT_VERSION_CONFLICT", "SLOT_OCCUPIED"):
                    confirmation.status = ConfirmationStatus.INVALIDATED; self.store.save_confirmation(confirmation)
                    run.confirmation_id = None; run.selected_slot_id = None; run.selected_slot_version = None
                    run.core_business_status = CoreBusinessStatus.NOT_STARTED
                    return await self._search_slots(run, trace_id)
                if not exc.retryable:
                    run.core_business_status = CoreBusinessStatus.FAILED; run.run_status = AgentRunStatus.FAILED
                    run.workflow_step = WorkflowStep.TERMINAL; run.completed_at = self.clock.now()
                    return self._save(run)
        return self.handoff(run.id, ActorContext(actor_id=run.actor_id, patient_id=run.patient_id,
            verification_level="CHANNEL_AUTHENTICATED", verified_at=run.verified_at), "RETRY_EXHAUSTED", trace_id)

    async def reconcile(self, run_id: str, trace_id: str) -> AgentRun:
        run = self._run(run_id)
        try:
            result = await self.clinic.operation(run.operation_id)
        except GatewayError:
            return self.handoff(run.id, ActorContext(actor_id=run.actor_id, patient_id=run.patient_id,
                verification_level="CHANNEL_AUTHENTICATED", verified_at=run.verified_at), "RETRY_EXHAUSTED", trace_id)
        if result.outcome.value != "EXECUTED" or not result.response_snapshot:
            return self.handoff(run.id, ActorContext(actor_id=run.actor_id, patient_id=run.patient_id,
                verification_level="CHANNEL_AUTHENTICATED", verified_at=run.verified_at), "UNKNOWN", trace_id)
        confirmation = self.store.get_confirmation(run.confirmation_id)
        self._trace(run, trace_id, "business_result_found", "RECONCILING_CORE_RESULT",
                    tool_name="get_operation_result", status="SUCCEEDED")
        return await self._verify_core(run, confirmation, result.response_snapshot, trace_id)

    async def _verify_core(self, run: AgentRun, confirmation: ConfirmationRecord,
                           response: Dict[str, Any], trace_id: str) -> AgentRun:
        appointment_id = response["appointment_id"]
        appointment = await self.clinic.appointment(appointment_id)
        expected_status = "CONFIRMED" if confirmation.action_type == "CREATE_APPOINTMENT" else "CANCELLED"
        if appointment.patient_id != run.patient_id or appointment.status.value != expected_status:
            run.core_business_status = CoreBusinessStatus.FAILED; run.run_status = AgentRunStatus.FAILED
            run.workflow_step = WorkflowStep.TERMINAL; run.last_error_code = "RESULT_VERIFICATION_FAILED"
            return self._save(run)
        if confirmation.action_type == "CREATE_APPOINTMENT":
            expected = confirmation.parameters
            if any(getattr(appointment, field) != expected[field] for field in
                   ("clinic_id", "service_item_id", "doctor_id", "slot_id")):
                raise WorkflowError("INTERNAL_ERROR", "verified appointment differs from confirmation", 500)
        run.appointment_id = appointment.id; run.appointment_version = appointment.version
        run.core_business_status = CoreBusinessStatus.SUCCEEDED
        self._trace(run, trace_id, "business_result_verified", "VERIFYING_CORE_RESULT", status="SUCCEEDED",
                    details={"appointment_id": appointment.id, "status": appointment.status.value})
        return await self._enqueue_side_effects(run, confirmation.action_type, trace_id)

    async def _enqueue_side_effects(self, run: AgentRun, task_type: str, trace_id: str) -> AgentRun:
        now = self.clock.now()
        base = {"run_id": run.id, "operation_id": run.operation_id, "patient_id": run.patient_id,
                "task_type": task_type, "task_status": "SUCCEEDED", "business_id": run.appointment_id,
                "occurred_at": now.isoformat()}
        events = [OutboxEvent(id=f"OUT-{uuid4().hex[:12]}", run_id=run.id,
            operation_id=run.operation_id, event_type="WRITEBACK", payload=base, next_attempt_at=now, created_at=now)]
        consent = await self.patient_ops.consent(run.patient_id, "web_simulator")
        if consent.get("allowed"):
            events.append(OutboxEvent(id=f"OUT-{uuid4().hex[:12]}", run_id=run.id,
                operation_id=run.operation_id, event_type="NOTIFICATION",
                payload={"patient_id": run.patient_id, "appointment_id": run.appointment_id,
                         "message": "预约业务已处理完成"}, next_attempt_at=now, created_at=now))
            run.notification_status = SideEffectStatus.PENDING
        else:
            run.notification_status = SideEffectStatus.NOT_REQUIRED
            self._trace(run, trace_id, "notification_suppressed_by_consent", "ENQUEUEING_NOTIFICATION",
                        status="NOT_REQUIRED")
        run.writeback_status = SideEffectStatus.PENDING
        run.run_status = AgentRunStatus.COMPLETED_WITH_PENDING_SIDE_EFFECTS
        run.workflow_step = WorkflowStep.TERMINAL; run.completed_at = now
        run.current_reply = f"业务已完成，预约编号 {run.appointment_id}；外围通知正在处理。"
        saved = self.store.save_run_with_outbox(run, events)
        self._trace(saved, trace_id, "outbox_persisted", "ENQUEUEING_NOTIFICATION", status="PENDING")
        return saved

    def cancel_run(self, run_id: str, actor: ActorContext, state_version: Optional[int], trace_id: str) -> AgentRun:
        run = self._owned_run(run_id, actor, state_version)
        if run.core_business_status is CoreBusinessStatus.SUCCEEDED:
            raise WorkflowError("INVALID_REQUEST", "completed business action cannot be cancelled")
        if run.confirmation_id:
            confirmation = self.store.get_confirmation(run.confirmation_id)
            if confirmation: confirmation.status = ConfirmationStatus.INVALIDATED; self.store.save_confirmation(confirmation)
        run.run_status = AgentRunStatus.CANCELLED_BY_PATIENT; run.workflow_step = WorkflowStep.TERMINAL
        run.completed_at = self.clock.now(); run.action_required = "NONE"; run.current_reply = "当前流程已取消。"
        saved = self._save(run); self._trace(saved, trace_id, "run_cancelled_by_patient", "TERMINAL")
        return saved

    def handoff(self, run_id: str, actor: ActorContext, reason_code: str, trace_id: str) -> AgentRun:
        run = self._owned_run(run_id, actor, None)
        if run.manual_task_id:
            return run
        if run.confirmation_id:
            confirmation = self.store.get_confirmation(run.confirmation_id)
            if confirmation: confirmation.status = ConfirmationStatus.INVALIDATED; self.store.save_confirmation(confirmation)
        task = ManualTask(id=f"TASK-{uuid4().hex[:12]}", run_id=run.id, patient_id=run.patient_id,
                          reason_code=reason_code, created_at=self.clock.now())
        run.manual_task_id = task.id; run.execution_owner = ExecutionOwner.OPERATOR
        run.run_status = AgentRunStatus.WAITING_HUMAN; run.workflow_step = WorkflowStep.NEED_HUMAN
        run.action_required = "HUMAN"; run.current_reply = "已转接人工客服，Agent 将暂停自动写入。"
        saved = self.store.save_handoff(run, task); self._trace(saved, trace_id, "human_handoff", "NEED_HUMAN",
                                               details={"manual_task_id": task.id, "reason_code": reason_code})
        return saved

    def return_to_agent(self, task_id: str, operator_id: str, trace_id: str) -> AgentRun:
        task = self.store.get_manual_task(task_id)
        if not task or task.status.value != "RESOLVED" or not task.resolution:
            raise WorkflowError("INVALID_REQUEST", "resolved task with resolution is required")
        task.status = task.status.__class__.RETURNED_TO_AGENT
        run = self._run(task.run_id); run.execution_owner = ExecutionOwner.AGENT
        run.run_status = AgentRunStatus.WAITING_PATIENT; run.workflow_step = WorkflowStep.UNDERSTANDING_REQUEST
        run.confirmation_id = None; run.action_required = "NONE"
        run.current_reply = "人工已处理并交还 Agent，请重新确认下一步。"
        run.current_reply_author = "AGENT"
        saved = self.store.save_return_to_agent(run, task); self._trace(saved, trace_id, "run_returned_to_agent", "UNDERSTANDING_REQUEST")
        return saved

    def operator_reply(self, task_id: str, operator_id: str, text: str, trace_id: str) -> AgentRun:
        task = self.store.get_manual_task(task_id)
        if not task: raise WorkflowError("INVALID_REQUEST", "manual task not found", 404)
        if task.status.value != "ASSIGNED" or task.assigned_operator_id != operator_id:
            raise WorkflowError("FORBIDDEN", "assigned operator is required to reply", 403)
        run = self._run(task.run_id)
        if run.execution_owner is not ExecutionOwner.OPERATOR:
            raise WorkflowError("INVALID_REQUEST", "run is not under operator control")
        run = self._record_conversation_message(run, "OPERATOR", text, trace_id)
        run.current_reply = text
        run.current_reply_author = "OPERATOR"
        saved = self._save(run)
        self._trace(saved, trace_id, "operator_reply_sent", "NEED_HUMAN", details={"manual_task_id": task.id})
        return saved

    def _conversation(self, conversation_id: str, actor: ActorContext) -> Conversation:
        item = self.store.get_conversation(conversation_id)
        if not item: raise WorkflowError("INVALID_REQUEST", "conversation not found", 404)
        if item.patient_id != actor.patient_id or item.actor_id != actor.actor_id:
            raise WorkflowError("FORBIDDEN", "conversation does not belong to actor", 403)
        return item

    def _run(self, run_id: str) -> AgentRun:
        run = self.store.get_run(run_id)
        if not run: raise WorkflowError("INVALID_REQUEST", "run not found", 404)
        return run

    def _owned_run(self, run_id: str, actor: ActorContext, state_version: Optional[int]) -> AgentRun:
        run = self._run(run_id)
        if run.patient_id != actor.patient_id or run.actor_id != actor.actor_id:
            raise WorkflowError("FORBIDDEN", "run does not belong to actor", 403)
        if state_version is not None and run.state_version != state_version:
            raise WorkflowError("STATE_VERSION_CONFLICT", "stale state version")
        return run

    def _save(self, run: AgentRun) -> AgentRun:
        return self.store.save_run(run, expected_version=run.state_version)

    def _record_conversation_message(self, run: AgentRun, author: str, text: str, trace_id: str) -> AgentRun:
        run.conversation_messages.append(ConversationMessage(author=author, text=text, created_at=self.clock.now()))
        saved = self._save(run)
        self._trace(saved, trace_id, "patient_message_recorded_for_operator" if author == "PATIENT" else "operator_message_recorded",
                    saved.workflow_step.value)
        return saved

    def _trace(self, run: AgentRun, trace_id: str, event: str, node: str, tool_name: Optional[str] = None,
               status: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        after = {"run_status": run.run_status.value, "workflow_step": run.workflow_step.value,
                 "execution_owner": run.execution_owner.value, "state_version": run.state_version}
        merged = dict(details or {})
        merged.setdefault("state_before", self._last_audited_state.get(run.id))
        merged["state_after"] = after
        self._last_audited_state[run.id] = after
        self.store.add_trace(run.id, TraceEvent(timestamp=self.clock.now(), trace_id=trace_id, event=event,
            node=node, tool_name=tool_name, status=status, details=merged))

    def _tool(self, run: AgentRun, tool: str, attempt: int, payload: Dict[str, Any], output: Dict[str, Any],
              status: str, error_code: Optional[str], started: Any) -> None:
        masked = {k: ("P***" if k == "patient_id" else v) for k, v in payload.items()}
        self.store.add_tool_execution(ToolExecution(id=f"TOOL-{uuid4().hex[:12]}", run_id=run.id,
            operation_id=run.operation_id, attempt_no=attempt, tool_name=tool, masked_input=masked,
            masked_output=output, status=status, error_code=error_code, started_at=started,
            completed_at=self.clock.now()))
