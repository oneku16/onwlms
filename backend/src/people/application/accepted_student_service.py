"""Application capability for Admissions-owned accepted-student conversion."""

from core.identifiers import new_uuid7
from people.application.contracts import AcceptedStudentRegistrationCommand
from people.application.contracts import AcceptedStudentRegistrationResult
from people.application.ports import AcceptedStudentRegistrationWriter
from people.domain.models import ContactKind
from people.domain.models import ContactMethod
from people.domain.models import Person
from people.domain.models import PersonProfile
from people.domain.models import ProfileKind


class AcceptedStudentRegistrationService:
    """Create a validated person and exact student profile idempotently."""

    def __init__(self, *, writer: AcceptedStudentRegistrationWriter) -> None:
        self._writer = writer

    async def register_accepted_student(
        self,
        command: AcceptedStudentRegistrationCommand,
    ) -> AcceptedStudentRegistrationResult:
        """Register minimized accepted-applicant data through one atomic writer."""

        contacts: list[ContactMethod] = []
        if command.email is not None:
            contacts.append(
                ContactMethod(
                    id=new_uuid7(),
                    kind=ContactKind.EMAIL,
                    value=command.email,
                    label="Admissions",
                    is_primary=True,
                )
            )
        if command.phone is not None:
            contacts.append(
                ContactMethod(
                    id=new_uuid7(),
                    kind=ContactKind.PHONE,
                    value=command.phone,
                    label="Admissions",
                    is_primary=command.email is None,
                )
            )
        person = Person(
            id=new_uuid7(),
            organization_id=command.organization_id,
            given_name=command.given_name,
            family_name=command.family_name,
            contacts=tuple(contacts),
        )
        profile = PersonProfile(
            id=command.student_profile_id,
            organization_id=command.organization_id,
            person_id=person.id,
            kind=ProfileKind.STUDENT,
        )
        return await self._writer.register_accepted_student(
            command=command,
            person=person,
            profile=profile,
        )


__all__ = ["AcceptedStudentRegistrationService"]
