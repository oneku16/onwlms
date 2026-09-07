"""PostgreSQL academic catalog and course-selection repository adapter."""

import hashlib
import json
from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TypeVar
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from academics.application.contracts import AcademicGradeTarget
from academics.application.contracts import AcademicSchedulingReferenceIds
from academics.application.contracts import AcceptedStudentAcademicEnrollmentCommand
from academics.application.contracts import AcceptedStudentAcademicEnrollmentResult
from academics.application.ports import CourseSelectionDecisionTransaction
from academics.application.ports import CourseSelectionSubmissionTransaction
from academics.domain.exceptions import CourseSelectionDecisionError
from academics.domain.exceptions import CourseSelectionError
from academics.domain.models import AcademicCalendarEvent
from academics.domain.models import AcademicEnrollmentStatus
from academics.domain.models import AcademicYear
from academics.domain.models import AdministrativeOverride
from academics.domain.models import Cohort
from academics.domain.models import Course
from academics.domain.models import CourseEnrollment
from academics.domain.models import CourseEnrollmentStatus
from academics.domain.models import CourseOffering
from academics.domain.models import CourseSelectionApproval
from academics.domain.models import CourseSelectionPolicy
from academics.domain.models import CourseSelectionRequest
from academics.domain.models import CourseSelectionStatus
from academics.domain.models import CurriculumCourse
from academics.domain.models import CurriculumCourseKind
from academics.domain.models import Department
from academics.domain.models import EducationMode
from academics.domain.models import Faculty
from academics.domain.models import MeetingWindow
from academics.domain.models import Program
from academics.domain.models import ProgramCurriculum
from academics.domain.models import Room
from academics.domain.models import SelectionRuleCode
from academics.domain.models import SelectionRuleViolation
from academics.domain.models import StudentAcademicEnrollment
from academics.domain.models import TeacherAssignment
from academics.domain.models import Term
from academics.infrastructure.models import AcademicCalendarEventModel
from academics.infrastructure.models import AcademicYearModel
from academics.infrastructure.models import AdmissionsEnrollmentRegistrationModel
from academics.infrastructure.models import CohortModel
from academics.infrastructure.models import CourseEnrollmentModel
from academics.infrastructure.models import CourseModel
from academics.infrastructure.models import CourseOfferingMeetingModel
from academics.infrastructure.models import CourseOfferingModel
from academics.infrastructure.models import CourseSelectionApprovalModel
from academics.infrastructure.models import CourseSelectionOverrideModel
from academics.infrastructure.models import CourseSelectionOverrideViolationModel
from academics.infrastructure.models import CourseSelectionPolicyModel
from academics.infrastructure.models import CourseSelectionRequestModel
from academics.infrastructure.models import CourseSelectionRequestOfferingModel
from academics.infrastructure.models import CurriculumCourseModel
from academics.infrastructure.models import CurriculumPrerequisiteModel
from academics.infrastructure.models import DepartmentModel
from academics.infrastructure.models import FacultyModel
from academics.infrastructure.models import ProgramCurriculumModel
from academics.infrastructure.models import ProgramModel
from academics.infrastructure.models import RoomModel
from academics.infrastructure.models import StudentAcademicEnrollmentModel
from academics.infrastructure.models import TeacherAssignmentModel
from academics.infrastructure.models import TermModel
from core.errors import ConflictError
from core.errors import NotFoundError
from core.identifiers import new_uuid7
from shared.database import Database

ModelT = TypeVar("ModelT")
DomainT = TypeVar("DomainT")


def _term_grade_lock_key(*, organization_id: UUID, term_id: UUID) -> int:
    """Derive the stable signed lock key shared with official grade writes."""

    digest = hashlib.blake2b(digest_size=8, person=b"ownsis-termgrade")
    digest.update(organization_id.bytes)
    digest.update(term_id.bytes)
    return int.from_bytes(digest.digest(), byteorder="big", signed=True)


class SQLAlchemyAcademicRepository:
    """Persist academic catalog and selection aggregates under tenant context."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def save_faculty(self, faculty: Faculty) -> None:
        """Create one tenant faculty."""

        await self._add(
            organization_id=faculty.organization_id,
            model=FacultyModel(
                id=faculty.id,
                organization_id=faculty.organization_id,
                campus_id=faculty.campus_id,
                code=faculty.code,
                name=faculty.name,
            ),
            conflict_message="Faculty already exists.",
        )

    async def get_faculty(
        self,
        *,
        organization_id: UUID,
        faculty_id: UUID,
    ) -> Faculty | None:
        """Return a faculty only from the requested tenant."""

        return await self._get(
            organization_id=organization_id,
            statement=select(FacultyModel).where(
                FacultyModel.organization_id == organization_id,
                FacultyModel.id == faculty_id,
            ),
            mapper=lambda model: Faculty(
                id=model.id,
                organization_id=model.organization_id,
                campus_id=model.campus_id,
                code=model.code,
                name=model.name,
            ),
        )

    async def save_department(self, department: Department) -> None:
        """Create one tenant department."""

        await self._add(
            organization_id=department.organization_id,
            model=DepartmentModel(
                id=department.id,
                organization_id=department.organization_id,
                faculty_id=department.faculty_id,
                code=department.code,
                name=department.name,
            ),
            conflict_message="Department already exists.",
        )

    async def get_department(
        self,
        *,
        organization_id: UUID,
        department_id: UUID,
    ) -> Department | None:
        """Return a department only from the requested tenant."""

        return await self._get(
            organization_id=organization_id,
            statement=select(DepartmentModel).where(
                DepartmentModel.organization_id == organization_id,
                DepartmentModel.id == department_id,
            ),
            mapper=lambda model: Department(
                id=model.id,
                organization_id=model.organization_id,
                faculty_id=model.faculty_id,
                code=model.code,
                name=model.name,
            ),
        )

    async def save_program(self, program: Program) -> None:
        """Create one tenant program."""

        await self._add(
            organization_id=program.organization_id,
            model=ProgramModel(
                id=program.id,
                organization_id=program.organization_id,
                department_id=program.department_id,
                code=program.code,
                name=program.name,
                education_mode=program.education_mode.value,
                credit_unit_label=program.credit_unit_label,
            ),
            conflict_message="Program already exists.",
        )

    async def get_program(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
    ) -> Program | None:
        """Return a program only from the requested tenant."""

        return await self._get(
            organization_id=organization_id,
            statement=select(ProgramModel).where(
                ProgramModel.organization_id == organization_id,
                ProgramModel.id == program_id,
            ),
            mapper=lambda model: Program(
                id=model.id,
                organization_id=model.organization_id,
                department_id=model.department_id,
                code=model.code,
                name=model.name,
                education_mode=EducationMode(model.education_mode),
                credit_unit_label=model.credit_unit_label,
            ),
        )

    async def save_academic_year(self, academic_year: AcademicYear) -> None:
        """Create one tenant academic year."""

        await self._add(
            organization_id=academic_year.organization_id,
            model=AcademicYearModel(
                id=academic_year.id,
                organization_id=academic_year.organization_id,
                name=academic_year.name,
                starts_on=academic_year.starts_on,
                ends_on=academic_year.ends_on,
            ),
            conflict_message="Academic year already exists.",
        )

    async def get_academic_year(
        self,
        *,
        organization_id: UUID,
        academic_year_id: UUID,
    ) -> AcademicYear | None:
        """Return an academic year only from the requested tenant."""

        return await self._get(
            organization_id=organization_id,
            statement=select(AcademicYearModel).where(
                AcademicYearModel.organization_id == organization_id,
                AcademicYearModel.id == academic_year_id,
            ),
            mapper=lambda model: AcademicYear(
                id=model.id,
                organization_id=model.organization_id,
                name=model.name,
                starts_on=model.starts_on,
                ends_on=model.ends_on,
            ),
        )

    async def save_term(self, term: Term) -> None:
        """Create one instructional term."""

        await self._add(
            organization_id=term.organization_id,
            model=TermModel(
                id=term.id,
                organization_id=term.organization_id,
                academic_year_id=term.academic_year_id,
                name=term.name,
                starts_on=term.starts_on,
                ends_on=term.ends_on,
                enrollment_deadline=term.enrollment_deadline,
                is_closed=term.is_closed,
            ),
            conflict_message="Academic term already exists.",
        )

    async def get_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        """Return a term only from the requested tenant."""

        return await self._get(
            organization_id=organization_id,
            statement=select(TermModel).where(
                TermModel.organization_id == organization_id,
                TermModel.id == term_id,
            ),
            mapper=lambda model: Term(
                id=model.id,
                organization_id=model.organization_id,
                academic_year_id=model.academic_year_id,
                name=model.name,
                starts_on=model.starts_on,
                ends_on=model.ends_on,
                enrollment_deadline=model.enrollment_deadline,
                is_closed=model.is_closed,
            ),
        )

    async def close_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        """Close an exact-tenant term under its shared protocol and row lock."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            acquired = await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {
                    "lock_key": _term_grade_lock_key(
                        organization_id=organization_id,
                        term_id=term_id,
                    )
                },
            )
            if acquired is not True:
                raise ConflictError(
                    "Term grading state is being updated; retry the request."
                )
            model = await session.scalar(
                select(TermModel)
                .where(
                    TermModel.organization_id == organization_id,
                    TermModel.id == term_id,
                )
                .with_for_update()
            )
            if model is None:
                return None
            if not model.is_closed:
                model.is_closed = True
                await session.flush()
            return Term(
                id=model.id,
                organization_id=model.organization_id,
                academic_year_id=model.academic_year_id,
                name=model.name,
                starts_on=model.starts_on,
                ends_on=model.ends_on,
                enrollment_deadline=model.enrollment_deadline,
                is_closed=model.is_closed,
            )

    async def save_calendar_event(self, event: AcademicCalendarEvent) -> None:
        """Create one academic-calendar event."""

        await self._add(
            organization_id=event.organization_id,
            model=AcademicCalendarEventModel(
                id=event.id,
                organization_id=event.organization_id,
                title=event.title,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                instruction_allowed=event.instruction_allowed,
            ),
            conflict_message="Academic calendar event already exists.",
        )

    async def save_course(self, course: Course) -> None:
        """Create one official course."""

        await self._add(
            organization_id=course.organization_id,
            model=CourseModel(
                id=course.id,
                organization_id=course.organization_id,
                department_id=course.department_id,
                code=course.code,
                title=course.title,
                credits=course.credits,
            ),
            conflict_message="Course already exists.",
        )

    async def get_course(
        self,
        *,
        organization_id: UUID,
        course_id: UUID,
    ) -> Course | None:
        """Return a course only from the requested tenant."""

        return await self._get(
            organization_id=organization_id,
            statement=select(CourseModel).where(
                CourseModel.organization_id == organization_id,
                CourseModel.id == course_id,
            ),
            mapper=lambda model: Course(
                id=model.id,
                organization_id=model.organization_id,
                department_id=model.department_id,
                code=model.code,
                title=model.title,
                credits=model.credits,
            ),
        )

    async def save_course_offering(self, offering: CourseOffering) -> None:
        """Create one course offering and normalized weekly meetings."""

        try:
            async with self._database.session(
                organization_id=offering.organization_id,
            ) as session:
                session.add(
                    CourseOfferingModel(
                        id=offering.id,
                        organization_id=offering.organization_id,
                        course_id=offering.course_id,
                        term_id=offering.term_id,
                        campus_id=offering.campus_id,
                        section_code=offering.section_code,
                        capacity=offering.capacity,
                    )
                )
                await session.flush()
                for meeting in offering.meeting_windows:
                    session.add(
                        CourseOfferingMeetingModel(
                            id=new_uuid7(),
                            organization_id=offering.organization_id,
                            course_offering_id=offering.id,
                            weekday=meeting.weekday,
                            starts_at=meeting.starts_at,
                            ends_at=meeting.ends_at,
                        )
                    )
        except IntegrityError as exc:
            raise ConflictError("Course offering already exists.") from exc

    async def get_course_offering(
        self,
        *,
        organization_id: UUID,
        offering_id: UUID,
    ) -> CourseOffering | None:
        """Return one complete offering only from the requested tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(CourseOfferingModel).where(
                    CourseOfferingModel.organization_id == organization_id,
                    CourseOfferingModel.id == offering_id,
                )
            )
            if model is None:
                return None
            meetings = tuple(
                (
                    await session.scalars(
                        select(CourseOfferingMeetingModel)
                        .where(
                            CourseOfferingMeetingModel.organization_id
                            == organization_id,
                            CourseOfferingMeetingModel.course_offering_id
                            == offering_id,
                        )
                        .order_by(CourseOfferingMeetingModel.id)
                    )
                ).all()
            )
            return CourseOffering(
                id=model.id,
                organization_id=model.organization_id,
                course_id=model.course_id,
                term_id=model.term_id,
                campus_id=model.campus_id,
                section_code=model.section_code,
                capacity=model.capacity,
                meeting_windows=tuple(
                    MeetingWindow(
                        weekday=meeting.weekday,
                        starts_at=meeting.starts_at,
                        ends_at=meeting.ends_at,
                    )
                    for meeting in meetings
                ),
            )

    async def save_cohort(self, cohort: Cohort) -> None:
        """Create one tenant program cohort."""

        await self._add(
            organization_id=cohort.organization_id,
            model=CohortModel(
                id=cohort.id,
                organization_id=cohort.organization_id,
                program_id=cohort.program_id,
                academic_year_id=cohort.academic_year_id,
                code=cohort.code,
                name=cohort.name,
            ),
            conflict_message="Cohort already exists.",
        )

    async def get_cohort(
        self,
        *,
        organization_id: UUID,
        cohort_id: UUID,
    ) -> Cohort | None:
        """Return a cohort only from the requested tenant."""

        return await self._get(
            organization_id=organization_id,
            statement=select(CohortModel).where(
                CohortModel.organization_id == organization_id,
                CohortModel.id == cohort_id,
            ),
            mapper=lambda model: Cohort(
                id=model.id,
                organization_id=model.organization_id,
                program_id=model.program_id,
                academic_year_id=model.academic_year_id,
                code=model.code,
                name=model.name,
            ),
        )

    async def save_room(self, room: Room) -> None:
        """Create one campus room."""

        await self._add(
            organization_id=room.organization_id,
            model=RoomModel(
                id=room.id,
                organization_id=room.organization_id,
                campus_id=room.campus_id,
                code=room.code,
                room_type=room.room_type,
                capacity=room.capacity,
            ),
            conflict_message="Campus room already exists.",
        )

    async def save_teacher_assignment(
        self,
        assignment: TeacherAssignment,
    ) -> None:
        """Create one offering teacher assignment."""

        await self._add(
            organization_id=assignment.organization_id,
            model=TeacherAssignmentModel(
                id=assignment.id,
                organization_id=assignment.organization_id,
                course_offering_id=assignment.course_offering_id,
                teacher_id=assignment.teacher_id,
                role=assignment.role,
            ),
            conflict_message="Teacher is already assigned to this offering.",
        )

    async def save_student_enrollment(
        self,
        enrollment: StudentAcademicEnrollment,
    ) -> None:
        """Create one official student academic enrollment."""

        await self._add(
            organization_id=enrollment.organization_id,
            model=StudentAcademicEnrollmentModel(
                id=enrollment.id,
                organization_id=enrollment.organization_id,
                student_id=enrollment.student_id,
                program_id=enrollment.program_id,
                academic_year_id=enrollment.academic_year_id,
                cohort_id=enrollment.cohort_id,
                status=enrollment.status.value,
                enrolled_at=enrollment.enrolled_at,
            ),
            conflict_message="Student already has this academic enrollment.",
        )

    async def get_student_enrollment(
        self,
        *,
        organization_id: UUID,
        enrollment_id: UUID,
    ) -> StudentAcademicEnrollment | None:
        """Return an official enrollment only from the requested tenant."""

        return await self._get(
            organization_id=organization_id,
            statement=select(StudentAcademicEnrollmentModel).where(
                StudentAcademicEnrollmentModel.organization_id == organization_id,
                StudentAcademicEnrollmentModel.id == enrollment_id,
            ),
            mapper=self._student_enrollment_from_model,
        )

    async def register_admissions_enrollment(
        self,
        *,
        command: AcceptedStudentAcademicEnrollmentCommand,
        enrollment: StudentAcademicEnrollment,
    ) -> AcceptedStudentAcademicEnrollmentResult:
        """Atomically create or resolve an Admissions-keyed enrollment."""

        self._require_admissions_enrollment_match(
            command=command,
            enrollment=enrollment,
        )
        command_digest = self._admissions_command_digest(command)
        try:
            async with self._database.session(
                organization_id=command.organization_id,
            ) as session:
                existing = await session.scalar(
                    select(AdmissionsEnrollmentRegistrationModel).where(
                        AdmissionsEnrollmentRegistrationModel.organization_id
                        == command.organization_id,
                        AdmissionsEnrollmentRegistrationModel.conversion_id
                        == command.idempotency_key,
                    )
                )
                if existing is not None:
                    return self._resolve_admissions_registration(
                        existing=existing,
                        command=command,
                        command_digest=command_digest,
                    )
                session.add(
                    StudentAcademicEnrollmentModel(
                        id=enrollment.id,
                        organization_id=enrollment.organization_id,
                        student_id=enrollment.student_id,
                        program_id=enrollment.program_id,
                        academic_year_id=enrollment.academic_year_id,
                        cohort_id=enrollment.cohort_id,
                        status=enrollment.status.value,
                        enrolled_at=enrollment.enrolled_at,
                    )
                )
                session.add(
                    AdmissionsEnrollmentRegistrationModel(
                        id=new_uuid7(),
                        organization_id=command.organization_id,
                        conversion_id=command.idempotency_key,
                        academic_enrollment_id=enrollment.id,
                        intake_term_id=command.intake_term_id,
                        command_digest=command_digest,
                    )
                )
            return AcceptedStudentAcademicEnrollmentResult(
                academic_enrollment_id=enrollment.id,
            )
        except IntegrityError as exc:
            existing = await self._get_admissions_registration(command)
            if existing is not None:
                return self._resolve_admissions_registration(
                    existing=existing,
                    command=command,
                    command_digest=command_digest,
                )
            raise ConflictError(
                "Accepted-student academic enrollment conflicts with stored state."
            ) from exc

    async def get_admissions_enrollment(
        self,
        command: AcceptedStudentAcademicEnrollmentCommand,
    ) -> AcceptedStudentAcademicEnrollmentResult | None:
        """Return an exact prior tenant binding or reject a changed replay."""

        existing = await self._get_admissions_registration(command)
        if existing is None:
            return None
        return self._resolve_admissions_registration(
            existing=existing,
            command=command,
            command_digest=self._admissions_command_digest(command),
        )

    async def _get_admissions_registration(
        self,
        command: AcceptedStudentAcademicEnrollmentCommand,
    ) -> AdmissionsEnrollmentRegistrationModel | None:
        """Reload a winning concurrent Admissions registration."""

        async with self._database.session(
            organization_id=command.organization_id,
        ) as session:
            model: AdmissionsEnrollmentRegistrationModel | None = await session.scalar(
                select(AdmissionsEnrollmentRegistrationModel).where(
                    AdmissionsEnrollmentRegistrationModel.organization_id
                    == command.organization_id,
                    AdmissionsEnrollmentRegistrationModel.conversion_id
                    == command.idempotency_key,
                )
            )
            return model

    @staticmethod
    def _admissions_command_digest(
        command: AcceptedStudentAcademicEnrollmentCommand,
    ) -> str:
        """Hash non-sensitive command fields for changed-replay detection."""

        payload = json.dumps(
            {
                "academic_enrollment_id": str(command.academic_enrollment_id),
                "enrolled_at": command.enrolled_at.isoformat(),
                "intake_term_id": str(command.intake_term_id),
                "organization_id": str(command.organization_id),
                "program_id": str(command.program_id),
                "student_profile_id": str(command.student_profile_id),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _require_admissions_enrollment_match(
        *,
        command: AcceptedStudentAcademicEnrollmentCommand,
        enrollment: StudentAcademicEnrollment,
    ) -> None:
        """Reject tenant or stable-identifier substitution before persistence."""

        if (
            enrollment.organization_id != command.organization_id
            or enrollment.id != command.academic_enrollment_id
            or enrollment.student_id != command.student_profile_id
            or enrollment.program_id != command.program_id
            or enrollment.cohort_id is not None
            or enrollment.enrolled_at != command.enrolled_at
        ):
            raise ConflictError(
                "Academic enrollment does not match the conversion command."
            )

    @staticmethod
    def _resolve_admissions_registration(
        *,
        existing: AdmissionsEnrollmentRegistrationModel,
        command: AcceptedStudentAcademicEnrollmentCommand,
        command_digest: str,
    ) -> AcceptedStudentAcademicEnrollmentResult:
        """Return an exact prior binding or reject a changed replay."""

        if (
            existing.organization_id != command.organization_id
            or existing.command_digest != command_digest
            or existing.academic_enrollment_id != command.academic_enrollment_id
            or existing.intake_term_id != command.intake_term_id
        ):
            raise ConflictError(
                "Conversion key is already bound to another academic enrollment."
            )
        return AcceptedStudentAcademicEnrollmentResult(
            academic_enrollment_id=existing.academic_enrollment_id,
        )

    async def save_curriculum(self, curriculum: ProgramCurriculum) -> None:
        """Create or replace one normalized program-year curriculum."""

        try:
            async with self._database.session(
                organization_id=curriculum.organization_id,
            ) as session:
                model = await session.scalar(
                    select(ProgramCurriculumModel)
                    .where(
                        ProgramCurriculumModel.organization_id
                        == curriculum.organization_id,
                        ProgramCurriculumModel.program_id == curriculum.program_id,
                        ProgramCurriculumModel.academic_year_id
                        == curriculum.academic_year_id,
                    )
                    .with_for_update()
                )
                if model is None:
                    model = ProgramCurriculumModel(
                        id=curriculum.id,
                        organization_id=curriculum.organization_id,
                        program_id=curriculum.program_id,
                        academic_year_id=curriculum.academic_year_id,
                    )
                    session.add(model)
                    await session.flush()
                elif model.id != curriculum.id:
                    raise ConflictError(
                        "Program-year curriculum identity cannot be replaced."
                    )
                else:
                    course_ids = tuple(
                        (
                            await session.scalars(
                                select(CurriculumCourseModel.id).where(
                                    CurriculumCourseModel.organization_id
                                    == curriculum.organization_id,
                                    CurriculumCourseModel.curriculum_id == model.id,
                                )
                            )
                        ).all()
                    )
                    if course_ids:
                        await session.execute(
                            delete(CurriculumPrerequisiteModel).where(
                                CurriculumPrerequisiteModel.organization_id
                                == curriculum.organization_id,
                                CurriculumPrerequisiteModel.curriculum_course_id.in_(
                                    course_ids
                                ),
                            )
                        )
                    await session.execute(
                        delete(CurriculumCourseModel).where(
                            CurriculumCourseModel.organization_id
                            == curriculum.organization_id,
                            CurriculumCourseModel.curriculum_id == model.id,
                        )
                    )
                for course in curriculum.courses:
                    curriculum_course_id = new_uuid7()
                    session.add(
                        CurriculumCourseModel(
                            id=curriculum_course_id,
                            organization_id=curriculum.organization_id,
                            curriculum_id=model.id,
                            course_id=course.course_id,
                            kind=course.kind.value,
                            credits=course.credits,
                        )
                    )
                    await session.flush()
                    for prerequisite_id in sorted(
                        course.prerequisite_course_ids,
                        key=str,
                    ):
                        session.add(
                            CurriculumPrerequisiteModel(
                                id=new_uuid7(),
                                organization_id=curriculum.organization_id,
                                curriculum_course_id=curriculum_course_id,
                                prerequisite_course_id=prerequisite_id,
                            )
                        )
        except IntegrityError as exc:
            raise ConflictError("Curriculum conflicts with stored data.") from exc

    async def get_curriculum(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        academic_year_id: UUID,
    ) -> ProgramCurriculum | None:
        """Return one complete normalized program-year curriculum."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(ProgramCurriculumModel).where(
                    ProgramCurriculumModel.organization_id == organization_id,
                    ProgramCurriculumModel.program_id == program_id,
                    ProgramCurriculumModel.academic_year_id == academic_year_id,
                )
            )
            if model is None:
                return None
            course_models = tuple(
                (
                    await session.scalars(
                        select(CurriculumCourseModel)
                        .where(
                            CurriculumCourseModel.organization_id == organization_id,
                            CurriculumCourseModel.curriculum_id == model.id,
                        )
                        .order_by(CurriculumCourseModel.id)
                    )
                ).all()
            )
            course_model_ids = tuple(value.id for value in course_models)
            prerequisites: tuple[CurriculumPrerequisiteModel, ...] = ()
            if course_model_ids:
                prerequisites = tuple(
                    (
                        await session.scalars(
                            select(CurriculumPrerequisiteModel).where(
                                CurriculumPrerequisiteModel.organization_id
                                == organization_id,
                                CurriculumPrerequisiteModel.curriculum_course_id.in_(
                                    course_model_ids
                                ),
                            )
                        )
                    ).all()
                )
            return ProgramCurriculum(
                id=model.id,
                organization_id=model.organization_id,
                program_id=model.program_id,
                academic_year_id=model.academic_year_id,
                courses=tuple(
                    CurriculumCourse(
                        course_id=course.course_id,
                        kind=CurriculumCourseKind(course.kind),
                        credits=course.credits,
                        prerequisite_course_ids=frozenset(
                            prerequisite.prerequisite_course_id
                            for prerequisite in prerequisites
                            if prerequisite.curriculum_course_id == course.id
                        ),
                    )
                    for course in course_models
                ),
            )

    async def save_selection_policy(
        self,
        policy: CourseSelectionPolicy,
    ) -> None:
        """Create or replace one program-term selection policy."""

        try:
            async with self._database.session(
                organization_id=policy.organization_id,
            ) as session:
                model = await session.scalar(
                    select(CourseSelectionPolicyModel)
                    .where(
                        CourseSelectionPolicyModel.organization_id
                        == policy.organization_id,
                        CourseSelectionPolicyModel.program_id == policy.program_id,
                        CourseSelectionPolicyModel.term_id == policy.term_id,
                    )
                    .with_for_update()
                )
                if model is None:
                    session.add(
                        CourseSelectionPolicyModel(
                            id=new_uuid7(),
                            organization_id=policy.organization_id,
                            program_id=policy.program_id,
                            term_id=policy.term_id,
                            education_mode=policy.education_mode.value,
                            maximum_credits=policy.maximum_credits,
                            deadline=policy.deadline,
                            approval_required=policy.approval_required,
                        )
                    )
                else:
                    model.education_mode = policy.education_mode.value
                    model.maximum_credits = policy.maximum_credits
                    model.deadline = policy.deadline
                    model.approval_required = policy.approval_required
        except IntegrityError as exc:
            raise ConflictError(
                "Course-selection policy conflicts with stored data."
            ) from exc

    async def get_selection_policy(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        term_id: UUID,
    ) -> CourseSelectionPolicy | None:
        """Return one exact program-term selection policy."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(CourseSelectionPolicyModel).where(
                    CourseSelectionPolicyModel.organization_id == organization_id,
                    CourseSelectionPolicyModel.program_id == program_id,
                    CourseSelectionPolicyModel.term_id == term_id,
                )
            )
            if model is None:
                return None
            return CourseSelectionPolicy(
                organization_id=model.organization_id,
                program_id=model.program_id,
                term_id=model.term_id,
                education_mode=EducationMode(model.education_mode),
                maximum_credits=model.maximum_credits,
                deadline=model.deadline,
                approval_required=model.approval_required,
            )

    async def list_faculties(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[Faculty, ...]:
        """Return a bounded stable faculty page for one tenant."""

        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(FacultyModel)
                        .where(FacultyModel.organization_id == organization_id)
                        .order_by(FacultyModel.code, FacultyModel.id)
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            Faculty(
                id=model.id,
                organization_id=model.organization_id,
                campus_id=model.campus_id,
                code=model.code,
                name=model.name,
            )
            for model in models
        )

    async def list_departments(
        self,
        *,
        organization_id: UUID,
        faculty_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Department, ...]:
        """Return a bounded stable department page for one tenant."""

        statement = select(DepartmentModel).where(
            DepartmentModel.organization_id == organization_id
        )
        if faculty_id is not None:
            statement = statement.where(DepartmentModel.faculty_id == faculty_id)
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(DepartmentModel.code, DepartmentModel.id)
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            Department(
                id=model.id,
                organization_id=model.organization_id,
                faculty_id=model.faculty_id,
                code=model.code,
                name=model.name,
            )
            for model in models
        )

    async def list_programs(
        self,
        *,
        organization_id: UUID,
        department_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Program, ...]:
        """Return a bounded stable program page for one tenant."""

        statement = select(ProgramModel).where(
            ProgramModel.organization_id == organization_id
        )
        if department_id is not None:
            statement = statement.where(ProgramModel.department_id == department_id)
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(ProgramModel.code, ProgramModel.id)
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            Program(
                id=model.id,
                organization_id=model.organization_id,
                department_id=model.department_id,
                code=model.code,
                name=model.name,
                education_mode=EducationMode(model.education_mode),
                credit_unit_label=model.credit_unit_label,
            )
            for model in models
        )

    async def list_academic_years(
        self,
        *,
        organization_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[AcademicYear, ...]:
        """Return a bounded stable academic-year page for one tenant."""

        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(AcademicYearModel)
                        .where(AcademicYearModel.organization_id == organization_id)
                        .order_by(
                            AcademicYearModel.starts_on.desc(),
                            AcademicYearModel.id,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            AcademicYear(
                id=model.id,
                organization_id=model.organization_id,
                name=model.name,
                starts_on=model.starts_on,
                ends_on=model.ends_on,
            )
            for model in models
        )

    async def list_terms(
        self,
        *,
        organization_id: UUID,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Term, ...]:
        """Return a bounded stable term page for one tenant."""

        statement = select(TermModel).where(
            TermModel.organization_id == organization_id
        )
        if academic_year_id is not None:
            statement = statement.where(TermModel.academic_year_id == academic_year_id)
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(TermModel.starts_on.desc(), TermModel.id)
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            Term(
                id=model.id,
                organization_id=model.organization_id,
                academic_year_id=model.academic_year_id,
                name=model.name,
                starts_on=model.starts_on,
                ends_on=model.ends_on,
                enrollment_deadline=model.enrollment_deadline,
                is_closed=model.is_closed,
            )
            for model in models
        )

    async def list_courses(
        self,
        *,
        organization_id: UUID,
        department_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Course, ...]:
        """Return a bounded stable course page for one tenant."""

        statement = select(CourseModel).where(
            CourseModel.organization_id == organization_id
        )
        if department_id is not None:
            statement = statement.where(CourseModel.department_id == department_id)
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(CourseModel.code, CourseModel.id)
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            Course(
                id=model.id,
                organization_id=model.organization_id,
                department_id=model.department_id,
                code=model.code,
                title=model.title,
                credits=model.credits,
            )
            for model in models
        )

    async def list_course_offerings(
        self,
        *,
        organization_id: UUID,
        term_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[CourseOffering, ...]:
        """Return a bounded stable complete offering page for one tenant."""

        statement = select(CourseOfferingModel).where(
            CourseOfferingModel.organization_id == organization_id
        )
        if term_id is not None:
            statement = statement.where(CourseOfferingModel.term_id == term_id)
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(
                            CourseOfferingModel.section_code,
                            CourseOfferingModel.id,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
            offering_ids = tuple(model.id for model in models)
            meetings: tuple[CourseOfferingMeetingModel, ...] = ()
            if offering_ids:
                meetings = tuple(
                    (
                        await session.scalars(
                            select(CourseOfferingMeetingModel)
                            .where(
                                CourseOfferingMeetingModel.organization_id
                                == organization_id,
                                CourseOfferingMeetingModel.course_offering_id.in_(
                                    offering_ids
                                ),
                            )
                            .order_by(CourseOfferingMeetingModel.id)
                        )
                    ).all()
                )
        return tuple(
            CourseOffering(
                id=model.id,
                organization_id=model.organization_id,
                course_id=model.course_id,
                term_id=model.term_id,
                campus_id=model.campus_id,
                section_code=model.section_code,
                capacity=model.capacity,
                meeting_windows=tuple(
                    MeetingWindow(
                        weekday=meeting.weekday,
                        starts_at=meeting.starts_at,
                        ends_at=meeting.ends_at,
                    )
                    for meeting in meetings
                    if meeting.course_offering_id == model.id
                ),
            )
            for model in models
        )

    async def list_cohorts(
        self,
        *,
        organization_id: UUID,
        program_id: UUID | None,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Cohort, ...]:
        """Return a bounded stable cohort page for one tenant."""

        statement = select(CohortModel).where(
            CohortModel.organization_id == organization_id
        )
        if program_id is not None:
            statement = statement.where(CohortModel.program_id == program_id)
        if academic_year_id is not None:
            statement = statement.where(
                CohortModel.academic_year_id == academic_year_id
            )
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(CohortModel.code, CohortModel.id)
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            Cohort(
                id=model.id,
                organization_id=model.organization_id,
                program_id=model.program_id,
                academic_year_id=model.academic_year_id,
                code=model.code,
                name=model.name,
            )
            for model in models
        )

    async def list_rooms_page(
        self,
        *,
        organization_id: UUID,
        campus_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Room, ...]:
        """Return a bounded stable room page for one tenant."""

        statement = select(RoomModel).where(
            RoomModel.organization_id == organization_id
        )
        if campus_id is not None:
            statement = statement.where(RoomModel.campus_id == campus_id)
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(RoomModel.code, RoomModel.id)
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            Room(
                id=model.id,
                organization_id=model.organization_id,
                campus_id=model.campus_id,
                code=model.code,
                room_type=model.room_type,
                capacity=model.capacity,
            )
            for model in models
        )

    async def list_teacher_assignments(
        self,
        *,
        organization_id: UUID,
        course_offering_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[TeacherAssignment, ...]:
        """Return a bounded stable teacher-assignment page for one tenant."""

        statement = select(TeacherAssignmentModel).where(
            TeacherAssignmentModel.organization_id == organization_id
        )
        if course_offering_id is not None:
            statement = statement.where(
                TeacherAssignmentModel.course_offering_id == course_offering_id
            )
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(
                            TeacherAssignmentModel.course_offering_id,
                            TeacherAssignmentModel.id,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            TeacherAssignment(
                id=model.id,
                organization_id=model.organization_id,
                course_offering_id=model.course_offering_id,
                teacher_id=model.teacher_id,
                role=model.role,
            )
            for model in models
        )

    async def list_student_enrollments(
        self,
        *,
        organization_id: UUID,
        student_id: UUID | None,
        program_id: UUID | None,
        academic_year_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[StudentAcademicEnrollment, ...]:
        """Return a bounded stable academic-enrollment page for one tenant."""

        statement = select(StudentAcademicEnrollmentModel).where(
            StudentAcademicEnrollmentModel.organization_id == organization_id
        )
        if student_id is not None:
            statement = statement.where(
                StudentAcademicEnrollmentModel.student_id == student_id
            )
        if program_id is not None:
            statement = statement.where(
                StudentAcademicEnrollmentModel.program_id == program_id
            )
        if academic_year_id is not None:
            statement = statement.where(
                StudentAcademicEnrollmentModel.academic_year_id == academic_year_id
            )
        async with self._database.session(organization_id=organization_id) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(
                            StudentAcademicEnrollmentModel.enrolled_at.desc(),
                            StudentAcademicEnrollmentModel.id,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
        return tuple(
            StudentAcademicEnrollment(
                id=model.id,
                organization_id=model.organization_id,
                student_id=model.student_id,
                program_id=model.program_id,
                academic_year_id=model.academic_year_id,
                cohort_id=model.cohort_id,
                status=AcademicEnrollmentStatus(model.status),
                enrolled_at=model.enrolled_at,
            )
            for model in models
        )

    async def admissions_target_exists(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether a program and intake-as-term belong to one tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            stored_program_id = await session.scalar(
                select(ProgramModel.id).where(
                    ProgramModel.organization_id == organization_id,
                    ProgramModel.id == program_id,
                )
            )
            if stored_program_id is None:
                return False
            stored_term_id = await session.scalar(
                select(TermModel.id).where(
                    TermModel.organization_id == organization_id,
                    TermModel.id == intake_id,
                )
            )
            return stored_term_id is not None

    async def admissions_target_is_open(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        intake_id: UUID,
    ) -> bool:
        """Return whether a same-tenant target exists and its term remains open."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            stored_program_id = await session.scalar(
                select(ProgramModel.id).where(
                    ProgramModel.organization_id == organization_id,
                    ProgramModel.id == program_id,
                )
            )
            if stored_program_id is None:
                return False
            stored_open_term_id = await session.scalar(
                select(TermModel.id).where(
                    TermModel.organization_id == organization_id,
                    TermModel.id == intake_id,
                    TermModel.is_closed.is_(False),
                )
            )
            return stored_open_term_id is not None

    async def get_grade_target(
        self,
        *,
        organization_id: UUID,
        course_enrollment_id: UUID,
    ) -> AcademicGradeTarget | None:
        """Resolve joined official grading facts in one tenant transaction."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            enrollment = await session.scalar(
                select(CourseEnrollmentModel).where(
                    CourseEnrollmentModel.organization_id == organization_id,
                    CourseEnrollmentModel.id == course_enrollment_id,
                )
            )
            if enrollment is None:
                return None
            student_enrollment = await session.scalar(
                select(StudentAcademicEnrollmentModel).where(
                    StudentAcademicEnrollmentModel.organization_id == organization_id,
                    StudentAcademicEnrollmentModel.id
                    == enrollment.student_academic_enrollment_id,
                )
            )
            offering = await session.scalar(
                select(CourseOfferingModel).where(
                    CourseOfferingModel.organization_id == organization_id,
                    CourseOfferingModel.id == enrollment.course_offering_id,
                )
            )
            if student_enrollment is None or offering is None:
                return None
            if student_enrollment.status != AcademicEnrollmentStatus.ACTIVE.value:
                return None
            # Completed course participation remains a legitimate finalization and
            # revision target; withdrawal in either enrollment invalidates grading.
            if enrollment.status not in {
                CourseEnrollmentStatus.ENROLLED.value,
                CourseEnrollmentStatus.COMPLETED.value,
            }:
                return None
            course = await session.scalar(
                select(CourseModel).where(
                    CourseModel.organization_id == organization_id,
                    CourseModel.id == offering.course_id,
                )
            )
            term = await session.scalar(
                select(TermModel).where(
                    TermModel.organization_id == organization_id,
                    TermModel.id == offering.term_id,
                )
            )
            if course is None or term is None:
                return None
            return AcademicGradeTarget(
                organization_id=organization_id,
                student_academic_enrollment_id=student_enrollment.id,
                course_enrollment_id=enrollment.id,
                course_offering_id=offering.id,
                course_id=course.id,
                term_id=term.id,
                credits=enrollment.credits,
            )

    async def get_term_closure(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> bool | None:
        """Return tenant term closure or None for an unknown term."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            term = await session.scalar(
                select(TermModel).where(
                    TermModel.organization_id == organization_id,
                    TermModel.id == term_id,
                )
            )
            return term.is_closed if term is not None else None

    async def existing_scheduling_reference_ids(
        self,
        *,
        organization_id: UUID,
        room_ids: frozenset[UUID],
        course_offering_ids: frozenset[UUID],
        cohort_ids: frozenset[UUID],
    ) -> AcademicSchedulingReferenceIds:
        """Return requested Scheduling references from one tenant transaction."""

        async with self._database.session(organization_id=organization_id) as session:
            existing_rooms = (
                frozenset(
                    (
                        await session.scalars(
                            select(RoomModel.id).where(
                                RoomModel.organization_id == organization_id,
                                RoomModel.id.in_(room_ids),
                            )
                        )
                    ).all()
                )
                if room_ids
                else frozenset()
            )
            existing_offerings = (
                frozenset(
                    (
                        await session.scalars(
                            select(CourseOfferingModel.id).where(
                                CourseOfferingModel.organization_id == organization_id,
                                CourseOfferingModel.id.in_(course_offering_ids),
                            )
                        )
                    ).all()
                )
                if course_offering_ids
                else frozenset()
            )
            existing_cohorts = (
                frozenset(
                    (
                        await session.scalars(
                            select(CohortModel.id).where(
                                CohortModel.organization_id == organization_id,
                                CohortModel.id.in_(cohort_ids),
                            )
                        )
                    ).all()
                )
                if cohort_ids
                else frozenset()
            )
        return AcademicSchedulingReferenceIds(
            organization_id=organization_id,
            room_ids=existing_rooms,
            course_offering_ids=existing_offerings,
            cohort_ids=existing_cohorts,
        )

    async def list_rooms(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[Room, ...]:
        """Return stable ordered room facts from one tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(RoomModel)
                        .where(RoomModel.organization_id == organization_id)
                        .order_by(RoomModel.code, RoomModel.id)
                    )
                ).all()
            )
        return tuple(
            Room(
                id=model.id,
                organization_id=model.organization_id,
                campus_id=model.campus_id,
                code=model.code,
                room_type=model.room_type,
                capacity=model.capacity,
            )
            for model in models
        )

    async def list_calendar_events(
        self,
        *,
        organization_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
    ) -> tuple[AcademicCalendarEvent, ...]:
        """Return all events intersecting one bounded tenant horizon."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(AcademicCalendarEventModel)
                        .where(
                            AcademicCalendarEventModel.organization_id
                            == organization_id,
                            AcademicCalendarEventModel.starts_at < ends_at,
                            AcademicCalendarEventModel.ends_at > starts_at,
                        )
                        .order_by(
                            AcademicCalendarEventModel.starts_at,
                            AcademicCalendarEventModel.ends_at,
                            AcademicCalendarEventModel.id,
                        )
                    )
                ).all()
            )
        return tuple(
            AcademicCalendarEvent(
                id=model.id,
                organization_id=model.organization_id,
                title=model.title,
                starts_at=model.starts_at,
                ends_at=model.ends_at,
                instruction_allowed=model.instruction_allowed,
            )
            for model in models
        )

    async def list_course_enrollments(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> tuple[CourseEnrollment, ...]:
        """Return stable ordered official course enrollments."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        select(CourseEnrollmentModel).where(
                            CourseEnrollmentModel.organization_id == organization_id,
                            CourseEnrollmentModel.student_academic_enrollment_id
                            == student_academic_enrollment_id,
                        )
                    )
                ).all()
            )
        return tuple(
            sorted(
                (self._course_enrollment_from_model(model) for model in models),
                key=lambda value: str(value.id),
            )
        )

    async def list_selection_requests(
        self,
        *,
        organization_id: UUID,
        status: CourseSelectionStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[CourseSelectionRequest, ...]:
        """Return a bounded newest-first selection-request page for one tenant."""

        statement = select(CourseSelectionRequestModel).where(
            CourseSelectionRequestModel.organization_id == organization_id
        )
        if status is not None:
            statement = statement.where(
                CourseSelectionRequestModel.status == status.value
            )
        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            models = tuple(
                (
                    await session.scalars(
                        statement.order_by(
                            CourseSelectionRequestModel.submitted_at.desc(),
                            CourseSelectionRequestModel.id,
                        )
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
            return tuple(
                [
                    await self._selection_request_from_model(
                        session=session,
                        model=model,
                    )
                    for model in models
                ]
            )

    async def get_selection_request(
        self,
        *,
        organization_id: UUID,
        request_id: UUID,
    ) -> CourseSelectionRequest | None:
        """Return one complete selection request from the requested tenant."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(
                select(CourseSelectionRequestModel).where(
                    CourseSelectionRequestModel.organization_id == organization_id,
                    CourseSelectionRequestModel.id == request_id,
                )
            )
            if model is None:
                return None
            return await self._selection_request_from_model(
                session=session,
                model=model,
            )

    @asynccontextmanager
    async def submission_transaction(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> AsyncIterator[CourseSelectionSubmissionTransaction]:
        """Lock one student aggregate through evaluation and submission."""

        try:
            async with self._database.session(
                organization_id=organization_id
            ) as session:
                enrollment_model = await session.scalar(
                    select(StudentAcademicEnrollmentModel)
                    .where(
                        StudentAcademicEnrollmentModel.organization_id
                        == organization_id,
                        StudentAcademicEnrollmentModel.id
                        == student_academic_enrollment_id,
                    )
                    .with_for_update()
                )
                if enrollment_model is None:
                    raise NotFoundError("Student academic enrollment was not found.")
                yield _SQLAlchemyCourseSelectionTransaction(
                    repository=self,
                    session=session,
                    organization_id=organization_id,
                    student_enrollment=self._student_enrollment_from_model(
                        enrollment_model
                    ),
                    request_model=None,
                    request=None,
                )
        except IntegrityError as exc:
            raise CourseSelectionError(
                "Course selection conflicts with current enrollment state."
            ) from exc

    @asynccontextmanager
    async def decision_transaction(
        self,
        *,
        organization_id: UUID,
        request_id: UUID,
    ) -> AsyncIterator[CourseSelectionDecisionTransaction]:
        """Lock one request and student aggregate through approval evaluation."""

        try:
            async with self._database.session(
                organization_id=organization_id
            ) as session:
                request_model = await session.scalar(
                    select(CourseSelectionRequestModel)
                    .where(
                        CourseSelectionRequestModel.organization_id == organization_id,
                        CourseSelectionRequestModel.id == request_id,
                    )
                    .with_for_update()
                )
                if request_model is None:
                    raise CourseSelectionDecisionError(
                        "Course-selection request no longer exists."
                    )
                request = await self._selection_request_from_model(
                    session=session,
                    model=request_model,
                )
                enrollment_model = await session.scalar(
                    select(StudentAcademicEnrollmentModel)
                    .where(
                        StudentAcademicEnrollmentModel.organization_id
                        == organization_id,
                        StudentAcademicEnrollmentModel.id
                        == request.student_academic_enrollment_id,
                    )
                    .with_for_update()
                )
                if enrollment_model is None:
                    raise NotFoundError("Student academic enrollment was not found.")
                yield _SQLAlchemyCourseSelectionTransaction(
                    repository=self,
                    session=session,
                    organization_id=organization_id,
                    student_enrollment=self._student_enrollment_from_model(
                        enrollment_model
                    ),
                    request_model=request_model,
                    request=request,
                )
        except IntegrityError as exc:
            raise CourseSelectionDecisionError(
                "Course-selection decision conflicts with current state."
            ) from exc

    async def save_submission(
        self,
        *,
        request: CourseSelectionRequest,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Atomically create a request and any immediate enrollments."""

        try:
            async with self._database.session(
                organization_id=request.organization_id,
            ) as session:
                existing = await session.scalar(
                    select(CourseSelectionRequestModel).where(
                        CourseSelectionRequestModel.organization_id
                        == request.organization_id,
                        CourseSelectionRequestModel.id == request.id,
                    )
                )
                if existing is not None:
                    raise ConflictError("Course-selection request already exists.")
                await self._check_and_lock_capacity(
                    session=session,
                    organization_id=request.organization_id,
                    enrollments=enrollments,
                    offering_capacities=offering_capacities,
                )
                self._add_selection_request(session=session, request=request)
                await session.flush()
                for enrollment in enrollments:
                    session.add(self._course_enrollment_to_model(enrollment))
        except IntegrityError as exc:
            raise CourseSelectionError(
                "Course selection conflicts with current enrollment state."
            ) from exc

    async def save_decision(
        self,
        *,
        request: CourseSelectionRequest,
        approval: CourseSelectionApproval,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Atomically decide a pending request and create resulting enrollments."""

        try:
            async with self._database.session(
                organization_id=request.organization_id,
            ) as session:
                model = await session.scalar(
                    select(CourseSelectionRequestModel)
                    .where(
                        CourseSelectionRequestModel.organization_id
                        == request.organization_id,
                        CourseSelectionRequestModel.id == request.id,
                    )
                    .with_for_update()
                )
                if model is None:
                    raise CourseSelectionDecisionError(
                        "Course-selection request no longer exists."
                    )
                if model.status != CourseSelectionStatus.PENDING.value:
                    raise CourseSelectionDecisionError(
                        "Course-selection request was already decided."
                    )
                await self._check_and_lock_capacity(
                    session=session,
                    organization_id=request.organization_id,
                    enrollments=enrollments,
                    offering_capacities=offering_capacities,
                )
                self._apply_selection_request(model=model, request=request)
                session.add(
                    CourseSelectionApprovalModel(
                        id=approval.id,
                        organization_id=approval.organization_id,
                        request_id=approval.request_id,
                        actor_id=approval.actor_id,
                        approved=approval.approved,
                        decided_at=approval.decided_at,
                        reason=approval.reason,
                    )
                )
                for enrollment in enrollments:
                    session.add(self._course_enrollment_to_model(enrollment))
        except IntegrityError as exc:
            raise CourseSelectionDecisionError(
                "Course-selection decision conflicts with current state."
            ) from exc

    async def _add(
        self,
        *,
        organization_id: UUID,
        model: object,
        conflict_message: str,
    ) -> None:
        """Add one tenant model and translate database uniqueness failures."""

        try:
            async with self._database.session(
                organization_id=organization_id,
            ) as session:
                session.add(model)
        except IntegrityError as exc:
            raise ConflictError(conflict_message) from exc

    async def _get(
        self,
        *,
        organization_id: UUID,
        statement: Select[tuple[ModelT]],
        mapper: Callable[[ModelT], DomainT],
    ) -> DomainT | None:
        """Resolve one model through exact tenant and stable identity predicates."""

        async with self._database.session(
            organization_id=organization_id,
        ) as session:
            model = await session.scalar(statement)
            return mapper(model) if model is not None else None

    @staticmethod
    async def _check_and_lock_capacity(
        *,
        session: AsyncSession,
        organization_id: UUID,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Lock each offering and reject stale, full, or duplicate enrollment."""

        # Stable lock ordering prevents overlapping multi-offering decisions from
        # deadlocking merely because students selected offerings in another order.
        for enrollment in sorted(
            enrollments,
            key=lambda value: str(value.course_offering_id),
        ):
            offering = await session.scalar(
                select(CourseOfferingModel)
                .where(
                    CourseOfferingModel.organization_id == organization_id,
                    CourseOfferingModel.id == enrollment.course_offering_id,
                )
                .with_for_update()
            )
            expected_capacity = offering_capacities.get(enrollment.course_offering_id)
            if offering is None or expected_capacity is None:
                raise CourseSelectionError("Course offering capacity is unknown.")
            if offering.capacity != expected_capacity:
                raise CourseSelectionError(
                    "Course offering capacity changed during selection."
                )
            duplicate = await session.scalar(
                select(CourseEnrollmentModel.id).where(
                    CourseEnrollmentModel.organization_id == organization_id,
                    CourseEnrollmentModel.student_academic_enrollment_id
                    == enrollment.student_academic_enrollment_id,
                    CourseEnrollmentModel.course_offering_id
                    == enrollment.course_offering_id,
                    CourseEnrollmentModel.status
                    == CourseEnrollmentStatus.ENROLLED.value,
                )
            )
            if duplicate is not None:
                raise CourseSelectionError(
                    "Student is already enrolled in the course offering."
                )
            occupied = await session.scalar(
                select(func.count(CourseEnrollmentModel.id)).where(
                    CourseEnrollmentModel.organization_id == organization_id,
                    CourseEnrollmentModel.course_offering_id
                    == enrollment.course_offering_id,
                    CourseEnrollmentModel.status
                    == CourseEnrollmentStatus.ENROLLED.value,
                )
            )
            if (occupied or 0) >= offering.capacity:
                raise CourseSelectionError("Course offering capacity was reached.")

    @staticmethod
    def _add_selection_request(
        *,
        session: AsyncSession,
        request: CourseSelectionRequest,
    ) -> None:
        """Append a request row, ordered offering membership, and override audit."""

        model = CourseSelectionRequestModel(
            id=request.id,
            organization_id=request.organization_id,
        )
        SQLAlchemyAcademicRepository._apply_selection_request(
            model=model,
            request=request,
        )
        session.add(model)
        for offering_id in request.offering_ids:
            session.add(
                CourseSelectionRequestOfferingModel(
                    id=new_uuid7(),
                    organization_id=request.organization_id,
                    request_id=request.id,
                    course_offering_id=offering_id,
                )
            )
        if request.override is None:
            return
        override_id = new_uuid7()
        session.add(
            CourseSelectionOverrideModel(
                id=override_id,
                organization_id=request.organization_id,
                request_id=request.id,
                actor_id=request.override.actor_id,
                reason=request.override.reason,
                override_created_at=request.override.created_at,
            )
        )
        for violation in request.override.violated_rules:
            related_ids: tuple[UUID | None, ...] = (
                tuple(violation.related_ids) if violation.related_ids else (None,)
            )
            for related_id in related_ids:
                session.add(
                    CourseSelectionOverrideViolationModel(
                        id=new_uuid7(),
                        organization_id=request.organization_id,
                        override_id=override_id,
                        rule_code=violation.code.value,
                        related_identifier=related_id,
                    )
                )

    @staticmethod
    def _apply_selection_request(
        *,
        model: CourseSelectionRequestModel,
        request: CourseSelectionRequest,
    ) -> None:
        """Apply current request lifecycle state without rewriting audit rows."""

        model.student_academic_enrollment_id = request.student_academic_enrollment_id
        model.term_id = request.term_id
        model.requested_credits = request.requested_credits
        model.status = request.status.value
        model.submitted_at = request.submitted_at
        model.submitted_by = request.submitted_by
        model.decided_at = request.decided_at
        model.decided_by = request.decided_by
        model.rejection_reason = request.rejection_reason

    @staticmethod
    async def _selection_request_from_model(
        *,
        session: AsyncSession,
        model: CourseSelectionRequestModel,
    ) -> CourseSelectionRequest:
        """Load one request aggregate with ordered selections and override audit."""

        offerings = tuple(
            (
                await session.scalars(
                    select(CourseSelectionRequestOfferingModel)
                    .where(
                        CourseSelectionRequestOfferingModel.organization_id
                        == model.organization_id,
                        CourseSelectionRequestOfferingModel.request_id == model.id,
                    )
                    .order_by(CourseSelectionRequestOfferingModel.id)
                )
            ).all()
        )
        override_model = await session.scalar(
            select(CourseSelectionOverrideModel).where(
                CourseSelectionOverrideModel.organization_id == model.organization_id,
                CourseSelectionOverrideModel.request_id == model.id,
            )
        )
        override = None
        if override_model is not None:
            violation_models = tuple(
                (
                    await session.scalars(
                        select(CourseSelectionOverrideViolationModel)
                        .where(
                            CourseSelectionOverrideViolationModel.organization_id
                            == model.organization_id,
                            CourseSelectionOverrideViolationModel.override_id
                            == override_model.id,
                        )
                        .order_by(CourseSelectionOverrideViolationModel.id)
                    )
                ).all()
            )
            ordered_codes = tuple(
                dict.fromkeys(value.rule_code for value in violation_models)
            )
            override = AdministrativeOverride(
                actor_id=override_model.actor_id,
                reason=override_model.reason,
                created_at=override_model.override_created_at,
                violated_rules=tuple(
                    SelectionRuleViolation(
                        code=SelectionRuleCode(code),
                        related_ids=tuple(
                            value.related_identifier
                            for value in violation_models
                            if value.rule_code == code
                            and value.related_identifier is not None
                        ),
                    )
                    for code in ordered_codes
                ),
            )
        return CourseSelectionRequest(
            id=model.id,
            organization_id=model.organization_id,
            student_academic_enrollment_id=(model.student_academic_enrollment_id),
            term_id=model.term_id,
            offering_ids=tuple(value.course_offering_id for value in offerings),
            requested_credits=model.requested_credits,
            status=CourseSelectionStatus(model.status),
            submitted_at=model.submitted_at,
            submitted_by=model.submitted_by,
            override=override,
            decided_at=model.decided_at,
            decided_by=model.decided_by,
            rejection_reason=model.rejection_reason,
        )

    @staticmethod
    def _student_enrollment_from_model(
        model: StudentAcademicEnrollmentModel,
    ) -> StudentAcademicEnrollment:
        """Translate a stored student academic enrollment."""

        return StudentAcademicEnrollment(
            id=model.id,
            organization_id=model.organization_id,
            student_id=model.student_id,
            program_id=model.program_id,
            academic_year_id=model.academic_year_id,
            cohort_id=model.cohort_id,
            status=AcademicEnrollmentStatus(model.status),
            enrolled_at=model.enrolled_at,
        )

    @staticmethod
    def _course_enrollment_to_model(
        enrollment: CourseEnrollment,
    ) -> CourseEnrollmentModel:
        """Translate an official course enrollment into persistence."""

        return CourseEnrollmentModel(
            id=enrollment.id,
            organization_id=enrollment.organization_id,
            student_academic_enrollment_id=(enrollment.student_academic_enrollment_id),
            course_offering_id=enrollment.course_offering_id,
            credits=enrollment.credits,
            status=enrollment.status.value,
            enrolled_at=enrollment.enrolled_at,
            selection_request_id=enrollment.selection_request_id,
        )

    @staticmethod
    def _course_enrollment_from_model(
        model: CourseEnrollmentModel,
    ) -> CourseEnrollment:
        """Translate a stored course enrollment into a validated domain value."""

        return CourseEnrollment(
            id=model.id,
            organization_id=model.organization_id,
            student_academic_enrollment_id=(model.student_academic_enrollment_id),
            course_offering_id=model.course_offering_id,
            credits=model.credits,
            status=CourseEnrollmentStatus(model.status),
            enrolled_at=model.enrolled_at,
            selection_request_id=model.selection_request_id,
        )


class _SQLAlchemyCourseSelectionTransaction:
    """Evaluate and persist one selection while exact aggregate locks are held."""

    def __init__(
        self,
        *,
        repository: SQLAlchemyAcademicRepository,
        session: AsyncSession,
        organization_id: UUID,
        student_enrollment: StudentAcademicEnrollment,
        request_model: CourseSelectionRequestModel | None,
        request: CourseSelectionRequest | None,
    ) -> None:
        self._repository = repository
        self._session = session
        self._organization_id = organization_id
        self._student_enrollment = student_enrollment
        self._request_model = request_model
        self._request = request

    @property
    def student_enrollment(self) -> StudentAcademicEnrollment:
        """Return the student enrollment protected by an exclusive row lock."""

        return self._student_enrollment

    @property
    def request(self) -> CourseSelectionRequest:
        """Return the request protected by an exclusive row lock."""

        if self._request is None:
            raise RuntimeError("A submission transaction has no existing request.")
        return self._request

    async def get_term(
        self,
        *,
        organization_id: UUID,
        term_id: UUID,
    ) -> Term | None:
        """Read and protect term closure state through transaction commit."""

        self._require_tenant(organization_id)
        model = await self._session.scalar(
            select(TermModel)
            .where(
                TermModel.organization_id == organization_id,
                TermModel.id == term_id,
            )
            .with_for_update(read=True)
        )
        if model is None:
            return None
        return Term(
            id=model.id,
            organization_id=model.organization_id,
            academic_year_id=model.academic_year_id,
            name=model.name,
            starts_on=model.starts_on,
            ends_on=model.ends_on,
            enrollment_deadline=model.enrollment_deadline,
            is_closed=model.is_closed,
        )

    async def get_course_offering(
        self,
        *,
        organization_id: UUID,
        offering_id: UUID,
    ) -> CourseOffering | None:
        """Read one complete offering in the active tenant transaction."""

        self._require_tenant(organization_id)
        model = await self._session.scalar(
            select(CourseOfferingModel).where(
                CourseOfferingModel.organization_id == organization_id,
                CourseOfferingModel.id == offering_id,
            )
        )
        if model is None:
            return None
        meetings = tuple(
            (
                await self._session.scalars(
                    select(CourseOfferingMeetingModel)
                    .where(
                        CourseOfferingMeetingModel.organization_id == organization_id,
                        CourseOfferingMeetingModel.course_offering_id == offering_id,
                    )
                    .order_by(CourseOfferingMeetingModel.id)
                )
            ).all()
        )
        return CourseOffering(
            id=model.id,
            organization_id=model.organization_id,
            course_id=model.course_id,
            term_id=model.term_id,
            campus_id=model.campus_id,
            section_code=model.section_code,
            capacity=model.capacity,
            meeting_windows=tuple(
                MeetingWindow(
                    weekday=meeting.weekday,
                    starts_at=meeting.starts_at,
                    ends_at=meeting.ends_at,
                )
                for meeting in meetings
            ),
        )

    async def get_curriculum(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        academic_year_id: UUID,
    ) -> ProgramCurriculum | None:
        """Read one normalized curriculum inside the active transaction."""

        self._require_tenant(organization_id)
        model = await self._session.scalar(
            select(ProgramCurriculumModel)
            .where(
                ProgramCurriculumModel.organization_id == organization_id,
                ProgramCurriculumModel.program_id == program_id,
                ProgramCurriculumModel.academic_year_id == academic_year_id,
            )
            .with_for_update()
        )
        if model is None:
            return None
        course_models = tuple(
            (
                await self._session.scalars(
                    select(CurriculumCourseModel)
                    .where(
                        CurriculumCourseModel.organization_id == organization_id,
                        CurriculumCourseModel.curriculum_id == model.id,
                    )
                    .order_by(CurriculumCourseModel.id)
                    .with_for_update()
                )
            ).all()
        )
        course_model_ids = tuple(value.id for value in course_models)
        prerequisites: tuple[CurriculumPrerequisiteModel, ...] = ()
        if course_model_ids:
            prerequisites = tuple(
                (
                    await self._session.scalars(
                        select(CurriculumPrerequisiteModel)
                        .where(
                            CurriculumPrerequisiteModel.organization_id
                            == organization_id,
                            CurriculumPrerequisiteModel.curriculum_course_id.in_(
                                course_model_ids
                            ),
                        )
                        .with_for_update()
                    )
                ).all()
            )
        return ProgramCurriculum(
            id=model.id,
            organization_id=model.organization_id,
            program_id=model.program_id,
            academic_year_id=model.academic_year_id,
            courses=tuple(
                CurriculumCourse(
                    course_id=course.course_id,
                    kind=CurriculumCourseKind(course.kind),
                    credits=course.credits,
                    prerequisite_course_ids=frozenset(
                        prerequisite.prerequisite_course_id
                        for prerequisite in prerequisites
                        if prerequisite.curriculum_course_id == course.id
                    ),
                )
                for course in course_models
            ),
        )

    async def get_selection_policy(
        self,
        *,
        organization_id: UUID,
        program_id: UUID,
        term_id: UUID,
    ) -> CourseSelectionPolicy | None:
        """Read one selection policy inside the active transaction."""

        self._require_tenant(organization_id)
        model = await self._session.scalar(
            select(CourseSelectionPolicyModel)
            .where(
                CourseSelectionPolicyModel.organization_id == organization_id,
                CourseSelectionPolicyModel.program_id == program_id,
                CourseSelectionPolicyModel.term_id == term_id,
            )
            .with_for_update(read=True)
        )
        if model is None:
            return None
        return CourseSelectionPolicy(
            organization_id=model.organization_id,
            program_id=model.program_id,
            term_id=model.term_id,
            education_mode=EducationMode(model.education_mode),
            maximum_credits=model.maximum_credits,
            deadline=model.deadline,
            approval_required=model.approval_required,
        )

    async def list_course_enrollments(
        self,
        *,
        organization_id: UUID,
        student_academic_enrollment_id: UUID,
    ) -> tuple[CourseEnrollment, ...]:
        """Read the locked student's current official course enrollments."""

        self._require_tenant(organization_id)
        if student_academic_enrollment_id != self._student_enrollment.id:
            raise NotFoundError("Student academic enrollment was not found.")
        models = tuple(
            (
                await self._session.scalars(
                    select(CourseEnrollmentModel).where(
                        CourseEnrollmentModel.organization_id == organization_id,
                        CourseEnrollmentModel.student_academic_enrollment_id
                        == student_academic_enrollment_id,
                    )
                )
            ).all()
        )
        return tuple(
            sorted(
                (
                    self._repository._course_enrollment_from_model(model)
                    for model in models
                ),
                key=lambda value: str(value.id),
            )
        )

    async def save_submission(
        self,
        *,
        request: CourseSelectionRequest,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Persist a submission in the active aggregate transaction."""

        self._require_request_scope(request)
        existing = await self._session.scalar(
            select(CourseSelectionRequestModel.id).where(
                CourseSelectionRequestModel.organization_id == request.organization_id,
                CourseSelectionRequestModel.id == request.id,
            )
        )
        if existing is not None:
            raise ConflictError("Course-selection request already exists.")
        await self._repository._check_and_lock_capacity(
            session=self._session,
            organization_id=request.organization_id,
            enrollments=enrollments,
            offering_capacities=offering_capacities,
        )
        self._repository._add_selection_request(
            session=self._session,
            request=request,
        )
        await self._session.flush()
        for enrollment in enrollments:
            self._session.add(self._repository._course_enrollment_to_model(enrollment))
        await self._session.flush()

    async def save_decision(
        self,
        *,
        request: CourseSelectionRequest,
        approval: CourseSelectionApproval,
        enrollments: tuple[CourseEnrollment, ...],
        offering_capacities: dict[UUID, int],
    ) -> None:
        """Persist a decision in the active aggregate transaction."""

        self._require_request_scope(request)
        request_model = self._request_model
        if request_model is None or self.request.id != request.id:
            raise CourseSelectionDecisionError(
                "Course-selection request changed during decision."
            )
        if request_model.status != CourseSelectionStatus.PENDING.value:
            raise CourseSelectionDecisionError(
                "Course-selection request was already decided."
            )
        await self._repository._check_and_lock_capacity(
            session=self._session,
            organization_id=request.organization_id,
            enrollments=enrollments,
            offering_capacities=offering_capacities,
        )
        self._repository._apply_selection_request(
            model=request_model,
            request=request,
        )
        self._session.add(
            CourseSelectionApprovalModel(
                id=approval.id,
                organization_id=approval.organization_id,
                request_id=approval.request_id,
                actor_id=approval.actor_id,
                approved=approval.approved,
                decided_at=approval.decided_at,
                reason=approval.reason,
            )
        )
        for enrollment in enrollments:
            self._session.add(self._repository._course_enrollment_to_model(enrollment))
        await self._session.flush()

    def _require_tenant(self, organization_id: UUID) -> None:
        if organization_id != self._organization_id:
            raise NotFoundError("Course-selection state was not found.")

    def _require_request_scope(self, request: CourseSelectionRequest) -> None:
        self._require_tenant(request.organization_id)
        if request.student_academic_enrollment_id != self._student_enrollment.id:
            raise CourseSelectionDecisionError(
                "Course-selection student enrollment changed during mutation."
            )


__all__ = ["SQLAlchemyAcademicRepository"]
