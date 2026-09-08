"""Signed Moodle grade-event authentication and payload translation.

A tenant shares one high-entropy signing secret with its Moodle-side event
sender. Every event carries a unix timestamp and an HMAC-SHA256 signature over
the version, the timestamp, and the raw body, so OwnSIS can authenticate the
sender, bound replay to a short clock-skew window, and still rely on the
tenant-scoped external event key for exact duplicate suppression.
"""

import hashlib
import hmac
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from uuid import UUID

from integrations.domain.exceptions import GradeEventRejectedError
from integrations.domain.exceptions import GradeEventSignatureError
from integrations.domain.moodle import MoodleFinalGradeEvidence

GRADE_EVENT_SIGNATURE_HEADER = "X-OwnSIS-Signature"
GRADE_EVENT_TIMESTAMP_HEADER = "X-OwnSIS-Timestamp"
GRADE_EVENT_SIGNATURE_VERSION = "v1"
GRADE_EVENT_SOURCE_VERSION = "moodle-grade-event-v1"
MAX_GRADE_EVENT_CLOCK_SKEW = timedelta(minutes=5)
MAX_GRADE_EVENT_BODY_BYTES = 16_384
MIN_GRADE_EVENT_SECRET_LENGTH = 32
_MAX_EVENT_ID_LENGTH = 200
_MAX_GRADE_VALUE_LENGTH = 80
_MAX_SOURCE_VERSION_LENGTH = 80
_ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "external_event_id",
        "course_offering_id",
        "student_person_id",
        "grade_value",
        "observed_at",
        "source_version",
    }
)


def compute_grade_event_signature(
    *,
    secret: str,
    timestamp: str,
    body: bytes,
) -> str:
    """Return the versioned HMAC-SHA256 signature expected for one event."""

    message = f"{GRADE_EVENT_SIGNATURE_VERSION}:{timestamp}:".encode() + body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"{GRADE_EVENT_SIGNATURE_VERSION}={digest}"


def verify_grade_event_signature(
    *,
    secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
) -> None:
    """Fail closed unless the presented signature matches in constant time."""

    expected = compute_grade_event_signature(
        secret=secret,
        timestamp=timestamp,
        body=body,
    )
    try:
        matches = hmac.compare_digest(expected, signature)
    except TypeError, ValueError:
        matches = False
    if not matches:
        raise GradeEventSignatureError("Grade event signature is invalid")


def parse_grade_event_timestamp(
    value: str,
    *,
    now: datetime,
) -> datetime:
    """Parse a unix-second timestamp and reject values outside the skew window."""

    if not value.isdigit() or len(value) > 12:
        raise GradeEventSignatureError("Grade event timestamp is invalid")
    try:
        presented = datetime.fromtimestamp(int(value), UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise GradeEventSignatureError("Grade event timestamp is invalid") from exc
    if abs(now - presented) > MAX_GRADE_EVENT_CLOCK_SKEW:
        raise GradeEventSignatureError("Grade event timestamp is outside the window")
    return presented


def parse_grade_event_payload(
    payload: object,
) -> MoodleFinalGradeEvidence:
    """Translate an authenticated JSON payload into non-authoritative evidence."""

    if not isinstance(payload, dict):
        raise GradeEventRejectedError("Grade event payload must be a JSON object")
    unknown = set(payload) - _ALLOWED_PAYLOAD_KEYS
    if unknown:
        raise GradeEventRejectedError("Grade event payload contains unsupported keys")
    external_event_id = _required_text(
        payload,
        "external_event_id",
        maximum_length=_MAX_EVENT_ID_LENGTH,
    )
    grade_value = payload.get("grade_value")
    if isinstance(grade_value, bool) or not isinstance(grade_value, str | int | float):
        raise GradeEventRejectedError("Grade event grade_value is required")
    normalized_grade = str(grade_value).strip()
    if not normalized_grade or len(normalized_grade) > _MAX_GRADE_VALUE_LENGTH:
        raise GradeEventRejectedError("Grade event grade_value is invalid")
    source_version = payload.get("source_version", GRADE_EVENT_SOURCE_VERSION)
    if (
        not isinstance(source_version, str)
        or not source_version.strip()
        or len(source_version) > _MAX_SOURCE_VERSION_LENGTH
    ):
        raise GradeEventRejectedError("Grade event source_version is invalid")
    return MoodleFinalGradeEvidence(
        external_event_id=external_event_id,
        course_offering_id=_required_uuid(payload, "course_offering_id"),
        student_person_id=_required_uuid(payload, "student_person_id"),
        grade_value=normalized_grade,
        observed_at=_required_datetime(payload, "observed_at"),
        source_version=source_version.strip(),
    )


def _required_text(
    payload: dict[object, object],
    key: str,
    *,
    maximum_length: int,
) -> str:
    """Return one trimmed non-empty bounded string field."""

    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum_length:
        raise GradeEventRejectedError(f"Grade event {key} is invalid")
    return value.strip()


def _required_uuid(
    payload: dict[object, object],
    key: str,
) -> UUID:
    """Return one canonical UUID field."""

    value = payload.get(key)
    if not isinstance(value, str):
        raise GradeEventRejectedError(f"Grade event {key} is invalid")
    try:
        return UUID(value)
    except ValueError as exc:
        raise GradeEventRejectedError(f"Grade event {key} is invalid") from exc


def _required_datetime(
    payload: dict[object, object],
    key: str,
) -> datetime:
    """Return one timezone-aware ISO 8601 timestamp field."""

    value = payload.get(key)
    if not isinstance(value, str):
        raise GradeEventRejectedError(f"Grade event {key} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GradeEventRejectedError(f"Grade event {key} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GradeEventRejectedError(f"Grade event {key} must be timezone-aware")
    return parsed


__all__ = [
    "GRADE_EVENT_SIGNATURE_HEADER",
    "GRADE_EVENT_SIGNATURE_VERSION",
    "GRADE_EVENT_SOURCE_VERSION",
    "GRADE_EVENT_TIMESTAMP_HEADER",
    "MAX_GRADE_EVENT_BODY_BYTES",
    "MAX_GRADE_EVENT_CLOCK_SKEW",
    "MIN_GRADE_EVENT_SECRET_LENGTH",
    "compute_grade_event_signature",
    "parse_grade_event_payload",
    "parse_grade_event_timestamp",
    "verify_grade_event_signature",
]
