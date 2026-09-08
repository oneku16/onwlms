"""Contract coverage for the first-release academic administration surface."""

from datetime import UTC
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import ValidationError

from academics.presentation.router import StudentEnrollmentBody
from academics.presentation.router import StudentEnrollmentResponse
from academics.presentation.router import TermBody
from academics.presentation.router import router as academic_router
from admissions.presentation.router import ApplicationResponse
from admissions.presentation.router import router as admissions_router
from grading.presentation.router import FinalGradeResponse
from grading.presentation.router import FinalGradeRevisionBody
from grading.presentation.router import GpaSummaryResponse
from grading.presentation.router import TranscriptRecordResponse
from grading.presentation.router import router as grading_router
from scheduling.presentation.router import GenerationApplyBody
from scheduling.presentation.router import SessionLockBody
from scheduling.presentation.router import router as scheduling_router


def _application() -> FastAPI:
    app = FastAPI()
    for router in (
        academic_router,
        admissions_router,
        grading_router,
        scheduling_router,
    ):
        app.include_router(router)
    return app


def test_first_release_admin_routes_are_explicit_and_complete() -> None:
    """Keep the supported administrative surface visible in route metadata."""

    paths_and_methods = {
        (route.path, method)
        for router in (
            academic_router,
            admissions_router,
            grading_router,
            scheduling_router,
        )
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in (route.methods or set())
    }
    expected = {
        ("/api/v1/academics/faculties", "POST"),
        ("/api/v1/academics/faculties", "GET"),
        ("/api/v1/academics/departments", "POST"),
        ("/api/v1/academics/programs", "POST"),
        ("/api/v1/academics/academic-years", "POST"),
        ("/api/v1/academics/terms", "POST"),
        ("/api/v1/academics/calendar-events", "POST"),
        ("/api/v1/academics/courses", "POST"),
        ("/api/v1/academics/course-offerings", "POST"),
        ("/api/v1/academics/cohorts", "POST"),
        ("/api/v1/academics/rooms", "POST"),
        ("/api/v1/academics/teacher-assignments", "POST"),
        ("/api/v1/academics/student-enrollments", "POST"),
        ("/api/v1/academics/curricula/{curriculum_id}", "PUT"),
        ("/api/v1/academics/curricula", "GET"),
        (
            "/api/v1/academics/course-selection-policies/{program_id}/{term_id}",
            "PUT",
        ),
        ("/api/v1/admissions/policies/{program_id}/{intake_id}", "PUT"),
        ("/api/v1/admissions/quotas/{quota_id}", "PUT"),
        ("/api/v1/admissions/applications", "GET"),
        ("/api/v1/admissions/applications/{application_id}", "GET"),
        ("/api/v1/admissions/applications/{application_id}/documents", "POST"),
        ("/api/v1/grading/scales", "POST"),
        ("/api/v1/grading/scale-templates", "POST"),
        ("/api/v1/grading/scales", "GET"),
        ("/api/v1/grading/external-evidence/{evidence_id}/accept", "POST"),
        ("/api/v1/grading/external-evidence/{evidence_id}/reject", "POST"),
        ("/api/v1/scheduling/sessions/{session_id}", "GET"),
        ("/api/v1/scheduling/generation/apply", "POST"),
    }
    assert expected.issubset(paths_and_methods)


def test_admin_contracts_fail_closed_and_preserve_concurrency_fields() -> None:
    """Do not expose unaudited closure or omit optimistic version snapshots."""

    assert "is_closed" not in TermBody.model_fields
    assert "status" not in StudentEnrollmentBody.model_fields
    assert "status" in StudentEnrollmentResponse.model_fields
    assert set(SessionLockBody.model_fields) == {"locked", "version"}
    assert "expected_revision_number" in FinalGradeRevisionBody.model_fields
    assert set(GenerationApplyBody.model_fields) == {
        "proposed_sessions",
        "locked_session_ids",
        "expected_versions",
    }


def test_student_enrollment_creation_rejects_client_owned_terminal_status() -> None:
    """Reject terminal creation status until explicit transitions are validated."""

    payload = {
        "student_id": uuid4(),
        "program_id": uuid4(),
        "academic_year_id": uuid4(),
        "enrolled_at": datetime(2026, 8, 7, 10, tzinfo=UTC),
        "status": "withdrawn",
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StudentEnrollmentBody.model_validate(payload)

    request_schema = _application().openapi()["components"]["schemas"][
        "StudentEnrollmentBody"
    ]
    assert request_schema["additionalProperties"] is False
    assert "status" not in request_schema["properties"]


def test_safe_admissions_and_typed_grading_responses_remain_stable() -> None:
    """Keep applicant PII out and retain Decimal types in official results."""

    sensitive = {"given_name", "family_name", "email", "phone"}
    assert sensitive.isdisjoint(ApplicationResponse.model_fields)
    for model, fields in (
        (
            FinalGradeResponse,
            {
                "raw_score",
                "credits_attempted",
                "credits_earned",
                "grade_points",
                "gpa_contribution",
            },
        ),
        (
            TranscriptRecordResponse,
            {
                "credits_attempted",
                "credits_earned",
                "grade_points",
                "gpa_contribution",
            },
        ),
        (
            GpaSummaryResponse,
            {
                "credits_attempted",
                "credits_earned",
                "gpa_credits_attempted",
                "quality_points",
                "gpa",
            },
        ),
    ):
        for field in fields:
            assert Decimal in _annotation_members(model.model_fields[field].annotation)


def test_collection_query_limits_are_bounded_in_openapi() -> None:
    """Keep every exposed administrative page capped by contract."""

    schema = _application().openapi()
    bounded_operations = (
        ("/api/v1/academics/faculties", "get", 100),
        ("/api/v1/admissions/applications", "get", 100),
        ("/api/v1/grading/scales", "get", 100),
        ("/api/v1/scheduling/sessions", "get", 200),
    )
    for path, method, maximum in bounded_operations:
        parameters = schema["paths"][path][method]["parameters"]
        limit = next(value for value in parameters if value["name"] == "limit")
        offset = next(value for value in parameters if value["name"] == "offset")
        assert limit["schema"]["maximum"] == maximum
        assert offset["schema"]["minimum"] == 0


def _annotation_members(annotation: object) -> frozenset[object]:
    """Flatten one optional union enough for stable Decimal assertions."""

    from typing import get_args

    members = get_args(annotation)
    return frozenset(members or (annotation,))
