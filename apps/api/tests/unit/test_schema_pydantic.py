"""Unit tests: Pydantic schema round-trips and validation (no DB required)."""
import sys
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../packages"))

from shared.schema import (  # noqa: E402
    ArchetypeSchema,
    AttemptSchema,
    ConceptEdgeSchema,
    ConceptGraphVersionSchema,
    ConceptSchema,
    DebriefSchema,
    EventSchema,
    LlmCallSchema,
    MasterySchema,
    MasterySnapshotSchema,
    MockCalibrationSchema,
    MockPaperSchema,
    MockSchema,
    MockStateSchema,
    OpenLoopSchema,
    PlanBlockSchema,
    PlanSchema,
    QuestionConceptSchema,
    QuestionGroupSchema,
    QuestionSchema,
    ReviewCardSchema,
    SessionSchema,
    TutorTurnSchema,
    UserSchema,
)

NOW = datetime.now(timezone.utc).isoformat()
UID = str(uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid4())


# ---------------------------------------------------------------------------
# Parametrized round-trip: one minimal valid instance per schema
# ---------------------------------------------------------------------------

MINIMAL_INSTANCES = [
    (
        UserSchema,
        {
            "id": _uid(), "clerk_id": "clerk_abc", "email": "a@b.com",
            "created_at": NOW, "updated_at": NOW,
        },
    ),
    (
        ConceptGraphVersionSchema,
        {"version": 1, "created_at": NOW},
    ),
    (
        ConceptSchema,
        {
            "id": _uid(), "graph_version": 1, "slug": "arithmetic", "name": "Arithmetic",
            "section": "QA", "depth": 0, "created_at": NOW,
        },
    ),
    (
        ConceptEdgeSchema,
        {"graph_version": 1, "parent_id": _uid(), "child_id": _uid(), "kind": "prereq"},
    ),
    (
        ArchetypeSchema,
        {"id": _uid(), "slug": "tsd_relative", "name": "TSD Relative Motion", "section": "QA"},
    ),
    (
        QuestionGroupSchema,
        {"id": _uid(), "kind": "standalone", "source": "CAT_2019_S1"},
    ),
    (
        QuestionSchema,
        {
            "id": _uid(), "source": "CAT_2019_S1", "section": "QA",
            "stem": "If x+y=5...", "answer_key": {"answer": "A"},
            "created_at": NOW,
        },
    ),
    (
        QuestionConceptSchema,
        {"question_id": _uid(), "concept_id": _uid()},
    ),
    (
        MasterySchema,
        {
            "user_id": _uid(), "concept_id": _uid(), "graph_version": 1,
            "p_known": "0.5", "alpha": "1.0", "beta": "1.0", "decayed_at": NOW,
        },
    ),
    (
        MasterySnapshotSchema,
        {"id": _uid(), "user_id": _uid(), "snapshot_at": NOW, "snapshot": {}, "created_at": NOW},
    ),
    (
        SessionSchema,
        {"id": _uid(), "user_id": _uid(), "kind": "study", "started_at": NOW},
    ),
    (
        AttemptSchema,
        {
            "id": _uid(), "user_id": _uid(), "question_id": _uid(),
            "response": {"answer": "A"}, "created_at": NOW,
        },
    ),
    (
        PlanSchema,
        {
            "id": _uid(), "user_id": _uid(), "generated_by": "planner_v1_heur",
            "horizon_days": 7, "rationale": {}, "created_at": NOW,
        },
    ),
    (
        PlanBlockSchema,
        {
            "id": _uid(), "plan_id": _uid(), "day": "2026-05-10", "ord": 1,
            "goal": "Practice arithmetic", "block_kind": "tutor",
            "target_concept_ids": [], "duration_min": 60,
        },
    ),
    (
        MockPaperSchema,
        {"id": _uid(), "source": "CAT_2024_S1", "question_layout": []},
    ),
    (
        MockSchema,
        {"id": _uid(), "user_id": _uid(), "paper_id": _uid(), "status": "active"},
    ),
    (
        MockStateSchema,
        {"mock_id": _uid(), "user_id": _uid(), "state_blob": {}, "updated_at": NOW},
    ),
    (
        MockCalibrationSchema,
        {
            "id": _uid(), "source": "CAT_2024_S1", "section": "QA",
            "raw_score": 50, "percentile": "75.0", "year": 2024,
        },
    ),
    (
        OpenLoopSchema,
        {"id": _uid(), "user_id": _uid(), "created_at": NOW},
    ),
    (
        DebriefSchema,
        {
            "id": _uid(), "user_id": _uid(), "summary_md": "# Debrief",
            "mastery_delta": {}, "created_at": NOW,
        },
    ),
    (
        ReviewCardSchema,
        {
            "id": _uid(), "user_id": _uid(), "scope": "concept",
            "ref_id": _uid(), "state": "new", "due_at": NOW,
        },
    ),
    (
        EventSchema,
        {
            "id": _uid(), "kind": "attempt.created", "schema_version": 1,
            "payload": {}, "created_at": NOW,
        },
    ),
    (
        LlmCallSchema,
        {
            "id": _uid(), "agent": "tutor", "prompt_version": "v1",
            "model": "claude-sonnet-4-6", "created_at": NOW,
        },
    ),
    (
        TutorTurnSchema,
        {
            "id": _uid(), "session_id": _uid(), "user_id": _uid(),
            "turn_index": 0, "move": "EXPLAIN", "created_at": NOW,
        },
    ),
]


@pytest.mark.parametrize("schema_cls, data", MINIMAL_INSTANCES)
def test_round_trip(schema_cls, data):
    """Every schema round-trips: model_validate → model_dump → model_validate."""
    instance = schema_cls.model_validate(data)
    rehydrated = schema_cls.model_validate(instance.model_dump())
    assert rehydrated == instance


# ---------------------------------------------------------------------------
# Specific validation tests
# ---------------------------------------------------------------------------

def test_mastery_p_known_above_one_raises():
    with pytest.raises(ValidationError) as exc_info:
        MasterySchema.model_validate({
            "user_id": _uid(), "concept_id": _uid(), "graph_version": 1,
            "p_known": "1.5", "alpha": "1.0", "beta": "1.0", "decayed_at": NOW,
        })
    assert "p_known" in str(exc_info.value)


def test_mastery_p_known_below_zero_raises():
    with pytest.raises(ValidationError) as exc_info:
        MasterySchema.model_validate({
            "user_id": _uid(), "concept_id": _uid(), "graph_version": 1,
            "p_known": "-0.1", "alpha": "1.0", "beta": "1.0", "decayed_at": NOW,
        })
    assert "p_known" in str(exc_info.value)


def test_attempt_unknown_error_type_raises():
    with pytest.raises(ValidationError) as exc_info:
        AttemptSchema.model_validate({
            "id": _uid(), "user_id": _uid(), "question_id": _uid(),
            "response": {"answer": "A"}, "error_type": "guessed", "created_at": NOW,
        })
    assert "error_type" in str(exc_info.value)


def test_attempt_optional_fields_default_none():
    a = AttemptSchema.model_validate({
        "id": _uid(), "user_id": _uid(), "question_id": _uid(),
        "response": {"answer": "A"}, "created_at": NOW,
    })
    assert a.is_correct is None
    assert a.error_type is None
    assert a.near_miss is False


def test_concept_invalid_section_raises():
    with pytest.raises(ValidationError):
        ConceptSchema.model_validate({
            "id": _uid(), "graph_version": 1, "slug": "x", "name": "X",
            "section": "MATH", "depth": 0,
        })


def test_user_invalid_locale_raises():
    with pytest.raises(ValidationError):
        UserSchema.model_validate({
            "id": _uid(), "clerk_id": "c1", "email": "x@y.com",
            "locale": "fr-FR", "created_at": NOW, "updated_at": NOW,
        })
