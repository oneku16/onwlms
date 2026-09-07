"""Moodle deadline reads are constrained to the mapped user's courses."""

from datetime import UTC
from datetime import datetime
from urllib.parse import parse_qs

from httpx import AsyncClient
from httpx import MockTransport
from httpx import Request
from httpx import Response

from integrations.infrastructure.gateway import MoodleWebServiceGateway


async def test_deadline_query_uses_mapped_user_enrollments_before_assignments() -> None:
    requests: list[dict[str, list[str]]] = []

    def handle(request: Request) -> Response:
        parameters = parse_qs(request.content.decode("utf-8"))
        requests.append(parameters)
        function = parameters["wsfunction"][0]
        if function == "core_enrol_get_users_courses":
            assert parameters["userid"] == ["moodle-user-42"]
            return Response(200, json=[{"id": 11}, {"id": 22}])
        assert function == "mod_assign_get_assignments"
        assert parameters["courseids[0]"] == ["11"]
        assert parameters["courseids[1]"] == ["22"]
        return Response(
            200,
            json={
                "courses": [
                    {
                        "id": 11,
                        "assignments": [
                            {
                                "id": 8,
                                "name": "Essay",
                                "duedate": 1_786_003_200,
                            }
                        ],
                    },
                    {
                        "id": 99,
                        "assignments": [
                            {
                                "id": 9,
                                "name": "Unrelated course assignment",
                                "duedate": 1_786_003_200,
                            }
                        ],
                    },
                ]
            },
        )

    async with AsyncClient(transport=MockTransport(handle)) as client:
        gateway = MoodleWebServiceGateway(
            base_url="https://moodle.example",
            token="protected-token",
            timeout_seconds=2,
            http_client=client,
        )
        values = await gateway.list_deadlines(external_user_id="moodle-user-42")

    assert len(requests) == 2
    assert len(values) == 1
    assert values[0].external_reference == "assignment:8"
    assert values[0].title == "Essay"
    assert values[0].due_at == datetime.fromtimestamp(1_786_003_200, UTC)
    assert values[0].source_version == "moodle-webservice-v1"
