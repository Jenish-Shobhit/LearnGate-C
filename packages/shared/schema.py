from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class UserSchema(BaseModel):
    id: UUID
    clerk_id: str
    email: str

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()
    display_name: Optional[str] = None
    exam_date: Optional[date] = None
    target_pct: Optional[Decimal] = None
    hours_per_day: Optional[Decimal] = None
    timezone: str = "Asia/Kolkata"
    locale: Literal["en-IN", "hi-IN", "hi-en"] = "en-IN"
    graph_version: int = 1
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class ConceptGraphVersionSchema(BaseModel):
    version: int
    notes: Optional[str] = None
    created_at: datetime


class ConceptSchema(BaseModel):
    id: UUID
    graph_version: int
    slug: str
    name: str
    section: Literal["QA", "VARC", "DILR"]
    parent_id: Optional[UUID] = None
    depth: int
    weight_in_exam: Decimal = Decimal("0.0")
    half_life_days: Decimal = Decimal("14")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConceptEdgeSchema(BaseModel):
    graph_version: int
    parent_id: UUID
    child_id: UUID
    kind: Literal["prereq", "related"]
    weight: Decimal = Decimal("1.0")


class ArchetypeSchema(BaseModel):
    id: UUID
    slug: str
    name: str
    section: Literal["QA", "VARC", "DILR"]
    description: Optional[str] = None


class QuestionGroupSchema(BaseModel):
    id: UUID
    kind: Literal["rc_passage", "dilr_set", "lr_set", "standalone"]
    shared_text: Optional[str] = None
    shared_assets: list[Any] = Field(default_factory=list)
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuestionSchema(BaseModel):
    id: UUID
    group_id: Optional[UUID] = None
    group_position: Optional[int] = None
    source: str
    source_license: str = "public"
    year: Optional[int] = None
    slot: Optional[int] = None
    section: Literal["QA", "VARC", "DILR"]
    stem: str
    options: Optional[list[Any]] = None
    answer_key: Any
    official_solution: Optional[str] = None
    archetype_id: Optional[UUID] = None
    difficulty_b: Optional[Decimal] = None
    difficulty_a: Decimal = Decimal("1.0")
    attempts_n: int = 0
    attempts_correct: int = 0
    embedding_id: Optional[UUID] = None
    quality_flag: Optional[Literal["ok", "disputed", "errata"]] = None
    created_at: datetime


class QuestionConceptSchema(BaseModel):
    question_id: UUID
    concept_id: UUID
    weight: Decimal = Decimal("1.0")


class MasterySchema(BaseModel):
    user_id: UUID
    concept_id: UUID
    graph_version: int
    p_known: Decimal = Field(ge=0, le=1)
    alpha: Decimal
    beta: Decimal
    ci_low: Optional[Decimal] = None
    ci_high: Optional[Decimal] = None
    last_practiced_at: Optional[datetime] = None
    decayed_at: datetime


class MasterySnapshotSchema(BaseModel):
    id: UUID
    user_id: UUID
    snapshot_at: datetime
    snapshot: dict[str, Any]
    created_at: datetime


class SessionSchema(BaseModel):
    id: UUID
    user_id: UUID
    kind: Literal["study", "drill", "pyq", "mock", "diagnostic", "review"]
    plan_block_id: Optional[UUID] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: Literal["active", "completed", "abandoned", "crashed"] = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttemptSchema(BaseModel):
    id: UUID
    user_id: UUID
    session_id: Optional[UUID] = None
    question_id: UUID
    response: dict[str, Any]
    is_correct: Optional[bool] = None
    time_ms: Optional[int] = None
    confidence: Optional[int] = Field(default=None, ge=1, le=5)
    error_type: Optional[Literal["conceptual", "procedural", "careless", "time", "misread", "none"]] = None
    process_grade: Optional[dict[str, Any]] = None
    near_miss: bool = False
    graded_at: Optional[datetime] = None
    idem_key: Optional[str] = None
    created_at: datetime


class PlanSchema(BaseModel):
    id: UUID
    user_id: UUID
    generated_by: str
    prompt_version: Optional[str] = None
    horizon_days: int
    rationale: dict[str, Any]
    predicted_pct_band: Optional[dict[str, Any]] = None
    created_at: datetime
    superseded_at: Optional[datetime] = None


class PlanBlockSchema(BaseModel):
    id: UUID
    plan_id: UUID
    day: date
    ord: int
    goal: str
    block_kind: Literal["tutor", "drill", "pyq", "review", "mock"]
    target_concept_ids: list[UUID]
    duration_min: int
    status: Literal["pending", "done", "skipped", "rescheduled"] = "pending"
    rescheduled_to: Optional[date] = None


class MockPaperSchema(BaseModel):
    id: UUID
    source: str
    generated: bool = False
    question_layout: Any


class MockSchema(BaseModel):
    id: UUID
    user_id: UUID
    paper_id: UUID
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: Literal["active", "completed", "abandoned"]
    scaled_score: Optional[dict[str, Any]] = None
    predicted_pct_band: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MockStateSchema(BaseModel):
    mock_id: UUID
    user_id: UUID
    state_blob: dict[str, Any]
    updated_at: datetime


class MockCalibrationSchema(BaseModel):
    id: UUID
    source: str
    section: Literal["QA", "VARC", "DILR", "total"]
    raw_score: int
    percentile: Decimal
    year: int


class OpenLoopSchema(BaseModel):
    id: UUID
    user_id: UUID
    question_id: Optional[UUID] = None
    concept_id: Optional[UUID] = None
    note: Optional[str] = None
    status: Literal["open", "resolved"] = "open"
    created_at: datetime
    resolved_at: Optional[datetime] = None


class DebriefSchema(BaseModel):
    id: UUID
    session_id: Optional[UUID] = None
    user_id: UUID
    summary_md: str
    mastery_delta: dict[str, Any]
    created_at: datetime


class ReviewCardSchema(BaseModel):
    id: UUID
    user_id: UUID
    scope: Literal["concept", "question"]
    ref_id: UUID
    state: Literal["new", "learning", "review", "relearning"]
    stability: Optional[Decimal] = None
    difficulty: Optional[Decimal] = None
    due_at: datetime
    last_reviewed_at: Optional[datetime] = None


class EventSchema(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    kind: str
    schema_version: int
    payload: dict[str, Any]
    cause_event_id: Optional[UUID] = None
    created_at: datetime


class LlmCallSchema(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    agent: str
    prompt_version: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    cost_usd: Optional[Decimal] = None
    request: Optional[dict[str, Any]] = None
    response: Optional[dict[str, Any]] = None
    trace_id: Optional[str] = None
    cause_event_id: Optional[UUID] = None
    created_at: datetime


class TutorTurnSchema(BaseModel):
    id: UUID
    session_id: UUID
    user_id: UUID
    turn_index: int
    move: str
    prompt_version: Optional[str] = None
    model: Optional[str] = None
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    cached_tokens: Optional[int] = None
    cost_usd: Optional[Decimal] = None
    latency_ms: Optional[int] = None
    llm_call_id: Optional[UUID] = None
    created_at: datetime
