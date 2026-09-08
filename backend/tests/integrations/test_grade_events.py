"""Signed grade-event authentication and payload translation rules."""

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import uuid7

import pytest

from integrations.domain.exceptions import GradeEventRejectedError
from integrations.domain.exceptions import GradeEventSignatureError
from integrations.domain.grade_events import GRADE_EVENT_SOURCE_VERSION
from integrations.domain.grade_events import compute_grade_event_signature
from integrations.domain.grade_events import parse_grade_event_payload
from integrations.domain.grade_events import parse_grade_event_timestamp
from integrations.domain.grade_events import verify_grade_event_signature

SECRET = "tenant-signing-secret-with-at-least-32-characters"
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def test_signature_verifies_only_the_exact_secret_timestamp_and_body() -> None:
    body = b'{"external_event_id": "e-1"}'
    signature = compute_grade_event_signature(
        secret=SECRET,
        timestamp="1788",
        body=body,
    )

    verify_grade_event_signature(
        secret=SECRET,
        timestamp="1788",
        body=body,
        signature=signature,
    )
    assert signature.startswith("v1=")
    for secret, timestamp, candidate_body, candidate in (
        ("other-secret-with-at-least-32-characters!!", "1788", body, signature),
        (SECRET, "1789", body, signature),
        (SECRET, "1788", body + b" ", signature),
        (SECRET, "1788", body, "v1=not-a-digest"),
        (SECRET, "1788", body, ""),
    ):
        with pytest.raises(GradeEventSignatureError):
            verify_grade_event_signature(
                secret=secret,
                timestamp=timestamp,
                body=candidate_body,
                signature=candidate,
            )


def test_timestamp_must_be_unix_seconds_within_the_skew_window() -> None:
    inside = str(int((NOW - timedelta(minutes=4)).timestamp()))
    assert parse_grade_event_timestamp(inside, now=NOW) == datetime.fromtimestamp(
        int(inside), UTC
    )
    for value in (
        "",
        "abc",
        "-5",
        "1" * 13,
        str(int((NOW - timedelta(minutes=6)).timestamp())),
        str(int((NOW + timedelta(minutes=6)).timestamp())),
    ):
        with pytest.raises(GradeEventSignatureError):
            parse_grade_event_timestamp(value, now=NOW)


def _valid_payload() -> dict[str, object]:
    return {
        "external_event_id": "grade:42",
        "course_offering_id": str(uuid7()),
        "student_person_id": str(uuid7()),
        "grade_value": 87.5,
        "observed_at": NOW.isoformat(),
    }


def test_payload_translates_numeric_values_and_defaults_source_version() -> None:
    evidence = parse_grade_event_payload(_valid_payload())

    assert evidence.external_event_id == "grade:42"
    assert evidence.grade_value == "87.5"
    assert evidence.observed_at == NOW
    assert evidence.source_version == GRADE_EVENT_SOURCE_VERSION


@pytest.mark.parametrize(
    "mutation",
    [
        {"surprise": True},
        {"external_event_id": ""},
        {"external_event_id": "x" * 201},
        {"course_offering_id": "not-a-uuid"},
        {"student_person_id": 12},
        {"grade_value": True},
        {"grade_value": ""},
        {"observed_at": "2026-09-08T12:00:00"},
        {"observed_at": "yesterday"},
        {"source_version": ""},
    ],
)
def test_payload_rejects_unsupported_or_malformed_fields(
    mutation: dict[str, object],
) -> None:
    payload = _valid_payload() | mutation

    with pytest.raises(GradeEventRejectedError):
        parse_grade_event_payload(payload)


def test_payload_must_be_an_object() -> None:
    with pytest.raises(GradeEventRejectedError, match="JSON object"):
        parse_grade_event_payload(["grade"])
