"""Shared Pydantic v2 contracts for the Self-Evolving CRM API.

Keep these models aligned with docs/API_CONTRACTS.md.
These are transport/schema models, not database ORM models.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Meta(StrictModel):
    request_id: str


T = TypeVar("T")


class SuccessEnvelope(BaseModel, Generic[T]):
    """Generic success response envelope; compatible with Python 3.10+."""
    data: T
    meta: Meta


class ErrorDetail(StrictModel):
    field: str | None = None
    issue: str


class ErrorBody(StrictModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str


class ErrorEnvelope(StrictModel):
    error: ErrorBody


class GenerateCRMRequest(StrictModel):
    prompt: str = Field(min_length=10, max_length=5000)


FieldType = Literal[
    "text", "textarea", "email", "number", "date", "boolean", "select", "phone"
]
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
RESERVED_FIELDS = {
    "id", "record_id", "crm_id", "owner_id", "created_at", "updated_at",
    "deleted_at", "entity_name", "data", "source"
}


class CRMField(StrictModel):
    name: str
    label: str = Field(min_length=1, max_length=100)
    type: FieldType
    required: bool = False
    options: list[str] | None = None

    @field_validator("name")
    @classmethod
    def valid_field_name(cls, value: str) -> str:
        if not IDENTIFIER.fullmatch(value):
            raise ValueError("Field name must be a lowercase identifier.")
        if value in RESERVED_FIELDS:
            raise ValueError("Field name is reserved by the system.")
        return value

    @field_validator("options")
    @classmethod
    def unique_options(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            cleaned = [item.strip() for item in value]
            if any(not item for item in cleaned):
                raise ValueError("Options cannot be empty.")
            if len(set(cleaned)) != len(cleaned):
                raise ValueError("Options must be unique.")
            return cleaned
        return value

    @model_validator(mode="after")
    def validate_select_options(self) -> "CRMField":
        if self.type == "select" and not self.options:
            raise ValueError("Select fields require at least one option.")
        if self.type != "select" and self.options is not None:
            raise ValueError("Only select fields may define options.")
        return self


class CRMEntity(StrictModel):
    name: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=100)
    fields: list[CRMField] = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def valid_entity_name(cls, value: str) -> str:
        if not IDENTIFIER.fullmatch(value):
            raise ValueError("Entity name must be a lowercase identifier.")
        return value

    @model_validator(mode="after")
    def unique_fields(self) -> "CRMEntity":
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Field names must be unique within an entity.")
        return self


class CRMConfiguration(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    name: str = Field(min_length=1, max_length=120)
    industry: str = Field(min_length=1, max_length=80)
    entities: list[CRMEntity] = Field(min_length=1, max_length=30)
    pipeline_stages: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def unique_entities(self) -> "CRMConfiguration":
        names = [entity.name for entity in self.entities]
        if len(names) != len(set(names)):
            raise ValueError("Entity names must be unique.")
        stages = [stage.strip() for stage in self.pipeline_stages]
        if any(not stage for stage in stages):
            raise ValueError("Pipeline stages cannot be empty.")
        if len(stages) != len(set(stages)):
            raise ValueError("Pipeline stages must be unique.")
        self.pipeline_stages = stages
        return self


class GenerateCRMData(StrictModel):
    configuration: CRMConfiguration
    warnings: list[str] = Field(default_factory=list)


class SaveCRMRequest(StrictModel):
    configuration: CRMConfiguration


class CRMSummary(StrictModel):
    crm_id: UUID
    name: str
    status: Literal["active", "archived"]
    configuration_version: int = Field(ge=1)
    configuration: CRMConfiguration


class CRMListData(StrictModel):
    items: list[CRMSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class CreateRecordRequest(StrictModel):
    data: dict[str, Any]
    source: str | None = Field(default=None, max_length=80)


class UpdateRecordRequest(StrictModel):
    data: dict[str, Any] = Field(min_length=1)


class CRMRecord(StrictModel):
    id: UUID
    crm_id: UUID
    entity_name: str
    data: dict[str, Any]
    source: str | None = None
    created_at: datetime
    updated_at: datetime


class RecordListData(StrictModel):
    items: list[CRMRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class ImportRowError(StrictModel):
    row: int = Field(ge=1)
    code: str
    message: str


class ImportResult(StrictModel):
    created: int = Field(ge=0)
    skipped: int = Field(ge=0)
    errors: list[ImportRowError] = Field(default_factory=list)


# Allowlisted trigger types for workflow automation
WorkflowTriggerType = Literal["record.created", "record.updated", "record.stage_changed"]

# Allowlisted action types for workflow automation
WorkflowActionType = Literal["create_follow_up_task", "notify_owner", "send_email"]


class WorkflowTrigger(StrictModel):
    type: WorkflowTriggerType
    entity: str = Field(min_length=1, max_length=64)

    @field_validator("entity")
    @classmethod
    def valid_entity_name(cls, value: str) -> str:
        if not IDENTIFIER.fullmatch(value):
            raise ValueError("Entity name must be a lowercase identifier.")
        return value


class WorkflowAction(StrictModel):
    type: WorkflowActionType
    delay_hours: int | None = Field(default=None, ge=0, le=8760)

    @model_validator(mode="after")
    def validate_action(self) -> "WorkflowAction":
        if self.type == "create_follow_up_task" and self.delay_hours is None:
            raise ValueError("create_follow_up_task requires delay_hours.")
        return self


class CreateWorkflowRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    trigger: WorkflowTrigger
    actions: list[WorkflowAction] = Field(min_length=1, max_length=10)
    enabled: bool = False


class WorkflowData(StrictModel):
    workflow_id: UUID
    status: Literal["draft", "active", "disabled"]
    name: str
    trigger: WorkflowTrigger
    actions: list[WorkflowAction]


class AnalyticsData(StrictModel):
    total_leads: int = Field(ge=0)
    qualified_leads: int = Field(ge=0)
    won_leads: int = Field(ge=0)
    conversion_rate: float = Field(ge=0, le=1)
    by_source: list[dict[str, Any]] = Field(default_factory=list)
    by_stage: list[dict[str, Any]] = Field(default_factory=list)


class EvolutionObjectiveRequest(StrictModel):
    objective: Literal["improve_follow_up", "improve_conversion", "reduce_manual_work"]


class ProposedChange(StrictModel):
    """Evolution proposal change payload. Structure depends on type.

    workflow.update: workflow_id (required), delay_hours (required)
    workflow.create: name (required), trigger (required), actions (optional)
    """
    type: Literal["workflow.update", "workflow.create"]
    # workflow.update fields
    workflow_id: UUID | None = None
    delay_hours: int | None = Field(default=None, ge=0, le=8760)
    # workflow.create fields
    name: str | None = Field(default=None, min_length=1, max_length=120)
    trigger: WorkflowTrigger | None = None
    actions: list[WorkflowAction] | None = Field(default=None, min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_change_fields(self) -> "ProposedChange":
        if self.type == "workflow.update":
            if self.workflow_id is None:
                raise ValueError("workflow.update requires workflow_id")
            if self.delay_hours is None:
                raise ValueError("workflow.update requires delay_hours")
        elif self.type == "workflow.create":
            if self.name is None:
                raise ValueError("workflow.create requires name")
            if self.trigger is None:
                raise ValueError("workflow.create requires trigger")
        return self


class EvolutionProposalData(StrictModel):
    proposal_id: UUID
    status: Literal["pending", "approved", "applied", "rejected", "stale", "failed"]
    summary: str
    proposed_change: ProposedChange
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    approved_at: datetime | None = None
    approved_by: UUID | None = None
    applied_at: datetime | None = None
    applied_by: UUID | None = None
    rejected_at: datetime | None = None
    rejected_by: UUID | None = None
    rejection_reason: str | None = None
    application_error: str | None = None


class ApproveProposalRequest(StrictModel):
    expected_status: Literal["pending"] = "pending"
    expected_version: int | None = Field(default=None, ge=1)


class RejectProposalRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=1000)


# ─────────────────────────────────────────────────────────────────────────────
# POST-GENERATION CRM EDITING SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class AddFieldRequest(StrictModel):
    """Request to add a new field to a CRM entity."""
    field_name: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=100)
    field_type: FieldType = Field(default="text")
    required: bool = False
    options: list[str] | None = None


class UpdateFieldRequest(StrictModel):
    """Request to update field properties."""
    label: str | None = None
    field_type: FieldType | None = None
    required: bool | None = None
    options: list[str] | None = None


class DeleteFieldRequest(StrictModel):
    """Request to delete a field (may include confirmation flag)."""
    confirm: bool = False


class ReorderFieldsRequest(StrictModel):
    """Request to reorder fields in an entity."""
    field_order: list[str] = Field(min_length=1)


class AddStageRequest(StrictModel):
    """Request to add a new pipeline stage."""
    stage_name: str = Field(min_length=1, max_length=100)
    position: int | None = Field(default=None, ge=0)


class UpdateStageRequest(StrictModel):
    """Request to rename a pipeline stage."""
    new_stage_name: str = Field(min_length=1, max_length=100)


class DeleteStageRequest(StrictModel):
    """Request to delete a pipeline stage."""
    confirm: bool = False


class ReorderStagesRequest(StrictModel):
    """Request to reorder pipeline stages."""
    stage_order: list[str] = Field(min_length=1)
