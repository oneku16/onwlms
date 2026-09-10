"""Supported Moodle web-service API adapter."""

from datetime import UTC
from datetime import datetime

import httpx

from core.errors import ExternalServiceError
from integrations.domain.moodle import MoodleCourseGradeObservation
from integrations.domain.moodle import MoodleDeadlineEvidence

MOODLE_SOURCE_VERSION = "moodle-webservice-v1"


class MoodleWebServiceGateway:
    """Call Moodle REST web services behind an OwnSIS anti-corruption layer."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = f"{base_url.rstrip('/')}/webservice/rest/server.php"
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    async def ensure_user(
        self,
        *,
        external_username: str,
        display_name: str,
        email: str | None,
        idempotency_key: str,
    ) -> str:
        """Resolve a user by deterministic username or create it once."""

        del idempotency_key
        users = await self._call(
            function="core_user_get_users_by_field",
            parameters={"field": "username", "values[0]": external_username},
        )
        if isinstance(users, list) and users:
            identifier = users[0].get("id")
            if isinstance(identifier, int):
                return str(identifier)
        name_parts = display_name.strip().split(maxsplit=1)
        first_name = name_parts[0] if name_parts else "OwnSIS"
        last_name = name_parts[1] if len(name_parts) > 1 else "User"
        payload: dict[str, str] = {
            "users[0][username]": external_username,
            "users[0][firstname]": first_name,
            "users[0][lastname]": last_name,
            "users[0][auth]": "oidc",
        }
        if email:
            payload["users[0][email]"] = email
        created = await self._call(
            function="core_user_create_users",
            parameters=payload,
        )
        if not isinstance(created, list) or not created:
            raise ExternalServiceError("Moodle did not return a created user")
        identifier = created[0].get("id")
        if not isinstance(identifier, int):
            raise ExternalServiceError("Moodle returned an invalid user identifier")
        return str(identifier)

    async def ensure_course(
        self,
        *,
        course_code: str,
        course_title: str,
        idempotency_key: str,
    ) -> str:
        """Resolve a course by shortname or create a shell once."""

        del idempotency_key
        courses = await self._call(
            function="core_course_get_courses_by_field",
            parameters={"field": "shortname", "value": course_code},
        )
        if isinstance(courses, dict):
            values = courses.get("courses")
            if isinstance(values, list) and values:
                identifier = values[0].get("id")
                if isinstance(identifier, int):
                    return str(identifier)
        created = await self._call(
            function="core_course_create_courses",
            parameters={
                "courses[0][fullname]": course_title,
                "courses[0][shortname]": course_code,
                "courses[0][categoryid]": "1",
            },
        )
        if not isinstance(created, list) or not created:
            raise ExternalServiceError("Moodle did not return a created course")
        identifier = created[0].get("id")
        if not isinstance(identifier, int):
            raise ExternalServiceError("Moodle returned an invalid course identifier")
        return str(identifier)

    async def set_enrollment(
        self,
        *,
        external_user_id: str,
        external_course_id: str,
        role: str,
        active: bool,
        idempotency_key: str,
    ) -> None:
        """Apply learning enrollment state using supported enrollment functions."""

        del idempotency_key
        if role not in {"student", "teacher"}:
            raise ValueError("Moodle enrollment role must be student or teacher")
        if active:
            role_id = "5" if role == "student" else "3"
            await self._call(
                function="enrol_manual_enrol_users",
                parameters={
                    "enrolments[0][roleid]": role_id,
                    "enrolments[0][userid]": external_user_id,
                    "enrolments[0][courseid]": external_course_id,
                },
            )
            return
        await self._call(
            function="enrol_manual_unenrol_users",
            parameters={
                "enrolments[0][userid]": external_user_id,
                "enrolments[0][courseid]": external_course_id,
            },
        )

    async def list_deadlines(
        self,
        *,
        external_user_id: str,
    ) -> list[MoodleDeadlineEvidence]:
        """Translate assignments only from the mapped user's enrolled courses."""

        courses = await self._call(
            function="core_enrol_get_users_courses",
            parameters={"userid": external_user_id},
        )
        if not isinstance(courses, list):
            return []
        course_ids = [
            course.get("id")
            for course in courses[:100]
            if isinstance(course, dict) and isinstance(course.get("id"), int)
        ]
        if not course_ids:
            return []
        authorized_course_ids = frozenset(course_ids)
        payload = await self._call(
            function="mod_assign_get_assignments",
            parameters={
                f"courseids[{index}]": str(identifier)
                for index, identifier in enumerate(course_ids)
            },
        )
        if not isinstance(payload, dict):
            return []
        observed_at = datetime.now(UTC)
        results: list[MoodleDeadlineEvidence] = []
        course_values = payload.get("courses")
        if not isinstance(course_values, list):
            return []
        for course in course_values:
            if not isinstance(course, dict):
                continue
            if course.get("id") not in authorized_course_ids:
                continue
            assignments = course.get("assignments")
            if not isinstance(assignments, list):
                continue
            for assignment in assignments:
                if not isinstance(assignment, dict):
                    continue
                identifier = assignment.get("id")
                name = assignment.get("name")
                timestamp = assignment.get("duedate")
                if not isinstance(identifier, int):
                    continue
                if not isinstance(name, str) or not isinstance(timestamp, int):
                    continue
                results.append(
                    MoodleDeadlineEvidence(
                        external_reference=f"assignment:{identifier}",
                        title=name,
                        due_at=datetime.fromtimestamp(timestamp, UTC),
                        observed_at=observed_at,
                        source_version=MOODLE_SOURCE_VERSION,
                    )
                )
        return sorted(
            results,
            key=lambda value: (value.due_at, value.external_reference),
        )

    async def list_course_grades(
        self,
        *,
        external_course_id: str,
    ) -> list[MoodleCourseGradeObservation]:
        """Translate graded course totals for every learner in one course shell."""

        payload = await self._call(
            function="gradereport_user_get_grade_items",
            parameters={"courseid": external_course_id},
        )
        if not isinstance(payload, dict):
            return []
        user_grades = payload.get("usergrades")
        if not isinstance(user_grades, list):
            return []
        observed_at = datetime.now(UTC)
        results: list[MoodleCourseGradeObservation] = []
        for user_grade in user_grades:
            if not isinstance(user_grade, dict):
                continue
            user_id = user_grade.get("userid")
            items = user_grade.get("gradeitems")
            if not isinstance(user_id, int) or not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or item.get("itemtype") != "course":
                    continue
                item_id = item.get("id")
                raw_grade = item.get("graderaw")
                if not isinstance(item_id, int) or not _is_number(raw_grade):
                    continue
                graded = item.get("gradedategraded")
                results.append(
                    MoodleCourseGradeObservation(
                        external_user_id=str(user_id),
                        grade_item_id=str(item_id),
                        grade_raw=str(raw_grade),
                        graded_at=(
                            datetime.fromtimestamp(graded, UTC)
                            if isinstance(graded, int) and not isinstance(graded, bool)
                            else None
                        ),
                        observed_at=observed_at,
                        source_version=MOODLE_SOURCE_VERSION,
                    )
                )
        return sorted(
            results,
            key=lambda value: (value.external_user_id, value.grade_item_id),
        )

    async def _call(
        self,
        *,
        function: str,
        parameters: dict[str, str],
    ) -> object:
        """Invoke one allowlisted Moodle function with bounded HTTP behavior."""

        allowed = {
            "core_course_create_courses",
            "core_course_get_courses_by_field",
            "core_enrol_get_users_courses",
            "core_user_create_users",
            "core_user_get_users_by_field",
            "enrol_manual_enrol_users",
            "enrol_manual_unenrol_users",
            "gradereport_user_get_grade_items",
            "mod_assign_get_assignments",
        }
        if function not in allowed:
            raise ValueError("Unsupported Moodle web-service function")
        request_data = {
            "wstoken": self._token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
            **parameters,
        }
        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    self._endpoint,
                    data=request_data,
                )
            else:
                async with httpx.AsyncClient(
                    timeout=self._timeout_seconds,
                    follow_redirects=False,
                ) as client:
                    response = await client.post(self._endpoint, data=request_data)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceError("Moodle request failed") from exc
        if isinstance(payload, dict) and payload.get("exception"):
            raise ExternalServiceError("Moodle rejected the operation")
        return payload


def _is_number(value: object) -> bool:
    """Return whether a Moodle grade value is a real numeric grade."""

    return isinstance(value, int | float) and not isinstance(value, bool)


__all__ = ["MOODLE_SOURCE_VERSION", "MoodleWebServiceGateway"]
