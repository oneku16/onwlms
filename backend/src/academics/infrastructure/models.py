"""SQLAlchemy 2 persistence models owned by the academic module."""

from datetime import date
from datetime import datetime
from datetime import time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import Time
from sqlalchemy import UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from shared.models import BaseModel
from shared.models import TimestampMixin
from shared.models import UUIDPrimaryKeyMixin


class AcademicTenantModelMixin:
    """Provide the explicit tenant owner for academic persistence records."""

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )


class FacultyModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a faculty while campus identity remains externally owned."""

    __tablename__ = "academic_faculties"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_faculties_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_academic_faculties_organization_id_code",
        ),
    )

    campus_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class DepartmentModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a department below a tenant faculty."""

    __tablename__ = "academic_departments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_departments_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_academic_departments_organization_id_code",
        ),
        ForeignKeyConstraint(
            ["organization_id", "faculty_id"],
            ["academic_faculties.organization_id", "academic_faculties.id"],
            name="fk_academic_departments_tenant_faculty",
        ),
    )

    faculty_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class ProgramModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a program and configurable education mode."""

    __tablename__ = "academic_programs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_programs_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_academic_programs_organization_id_code",
        ),
        ForeignKeyConstraint(
            ["organization_id", "department_id"],
            ["academic_departments.organization_id", "academic_departments.id"],
            name="fk_academic_programs_tenant_department",
        ),
    )

    department_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    education_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    credit_unit_label: Mapped[str] = mapped_column(String(64), nullable=False)


class AcademicYearModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist an organization academic year."""

    __tablename__ = "academic_years"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_years_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_academic_years_organization_id_name",
        ),
        CheckConstraint(
            "starts_on < ends_on",
            name="academic_year_date_order",
        ),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)


class TermModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist an instructional term and its closure state."""

    __tablename__ = "academic_terms"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_terms_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "academic_year_id",
            "name",
            name="uq_academic_terms_organization_year_name",
        ),
        ForeignKeyConstraint(
            ["organization_id", "academic_year_id"],
            ["academic_years.organization_id", "academic_years.id"],
            name="fk_academic_terms_tenant_academic_year",
        ),
        CheckConstraint("starts_on < ends_on", name="academic_term_date_order"),
    )

    academic_year_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    enrollment_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AcademicCalendarEventModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a tenant academic-calendar event."""

    __tablename__ = "academic_calendar_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_calendar_events_organization_id_id",
        ),
        CheckConstraint(
            "starts_at < ends_at",
            name="academic_calendar_event_time_order",
        ),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instruction_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CourseModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist an official course definition."""

    __tablename__ = "academic_courses"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_courses_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_academic_courses_organization_id_code",
        ),
        ForeignKeyConstraint(
            ["organization_id", "department_id"],
            ["academic_departments.organization_id", "academic_departments.id"],
            name="fk_academic_courses_tenant_department",
        ),
        CheckConstraint("credits > 0", name="academic_course_positive_credits"),
    )

    department_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    credits: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)


class CourseOfferingModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a term-specific course offering."""

    __tablename__ = "academic_course_offerings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_course_offerings_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "term_id",
            "course_id",
            "section_code",
            name="uq_academic_offerings_tenant_term_course_section",
        ),
        ForeignKeyConstraint(
            ["organization_id", "course_id"],
            ["academic_courses.organization_id", "academic_courses.id"],
            name="fk_academic_offerings_tenant_course",
        ),
        ForeignKeyConstraint(
            ["organization_id", "term_id"],
            ["academic_terms.organization_id", "academic_terms.id"],
            name="fk_academic_offerings_tenant_term",
        ),
        CheckConstraint("capacity > 0", name="positive_capacity"),
    )

    course_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    term_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    campus_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    section_code: Mapped[str] = mapped_column(String(64), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)


class CourseOfferingMeetingModel(
    AcademicTenantModelMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one weekly meeting window for a course offering."""

    __tablename__ = "academic_course_offering_meetings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "course_offering_id"],
            [
                "academic_course_offerings.organization_id",
                "academic_course_offerings.id",
            ],
            name="fk_academic_offering_meetings_tenant_offering",
        ),
        CheckConstraint(
            "weekday >= 1 AND weekday <= 7",
            name="weekday_range",
        ),
        CheckConstraint(
            "starts_at < ends_at",
            name="time_order",
        ),
    )

    course_offering_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[time] = mapped_column(Time, nullable=False)
    ends_at: Mapped[time] = mapped_column(Time, nullable=False)


class CohortModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a named program cohort."""

    __tablename__ = "academic_cohorts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_cohorts_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_academic_cohorts_organization_id_code",
        ),
        ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["academic_programs.organization_id", "academic_programs.id"],
            name="fk_academic_cohorts_tenant_program",
        ),
        ForeignKeyConstraint(
            ["organization_id", "academic_year_id"],
            ["academic_years.organization_id", "academic_years.id"],
            name="fk_academic_cohorts_tenant_academic_year",
        ),
    )

    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    academic_year_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class RoomModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a campus room used by scheduling."""

    __tablename__ = "academic_rooms"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_rooms_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "campus_id",
            "code",
            name="uq_academic_rooms_tenant_campus_code",
        ),
        CheckConstraint("capacity > 0", name="academic_room_positive_capacity"),
    )

    campus_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    room_type: Mapped[str] = mapped_column(String(64), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)


class TeacherAssignmentModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist an opaque teacher assignment to an academic offering."""

    __tablename__ = "academic_teacher_assignments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "course_offering_id",
            "teacher_id",
            name="uq_academic_teacher_assignments_tenant_offering_teacher",
        ),
        ForeignKeyConstraint(
            ["organization_id", "course_offering_id"],
            [
                "academic_course_offerings.organization_id",
                "academic_course_offerings.id",
            ],
            name="fk_academic_teacher_assignments_tenant_offering",
        ),
    )

    course_offering_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    teacher_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)


class StudentAcademicEnrollmentModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist official student participation in a program."""

    __tablename__ = "academic_student_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_student_enrollments_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "student_id",
            "program_id",
            "academic_year_id",
            name="uq_academic_student_enrollment_tenant_student_program_year",
        ),
        ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["academic_programs.organization_id", "academic_programs.id"],
            name="fk_academic_student_enrollments_tenant_program",
        ),
        ForeignKeyConstraint(
            ["organization_id", "academic_year_id"],
            ["academic_years.organization_id", "academic_years.id"],
            name="fk_academic_student_enrollments_tenant_year",
        ),
        ForeignKeyConstraint(
            ["organization_id", "cohort_id"],
            ["academic_cohorts.organization_id", "academic_cohorts.id"],
            name="fk_academic_student_enrollments_tenant_cohort",
        ),
    )

    student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    academic_year_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    cohort_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class AdmissionsEnrollmentRegistrationModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Bind an Admissions conversion to one module-owned enrollment."""

    __tablename__ = "academic_admissions_enrollment_registrations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "conversion_id",
            name="uq_academic_admissions_enrollments_tenant_conversion",
        ),
        UniqueConstraint(
            "organization_id",
            "academic_enrollment_id",
            name="uq_academic_admissions_enrollments_tenant_enrollment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "academic_enrollment_id"],
            [
                "academic_student_enrollments.organization_id",
                "academic_student_enrollments.id",
            ],
            name="fk_academic_admissions_enrollments_tenant_enrollment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "intake_term_id"],
            ["academic_terms.organization_id", "academic_terms.id"],
            name="fk_academic_admissions_enrollments_tenant_term",
            ondelete="RESTRICT",
        ),
    )

    conversion_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    academic_enrollment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    intake_term_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    command_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class ProgramCurriculumModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one versioned program curriculum."""

    __tablename__ = "academic_program_curricula"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_program_curricula_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "program_id",
            "academic_year_id",
            name="uq_academic_curricula_tenant_program_year",
        ),
        ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["academic_programs.organization_id", "academic_programs.id"],
            name="fk_academic_curricula_tenant_program",
        ),
        ForeignKeyConstraint(
            ["organization_id", "academic_year_id"],
            ["academic_years.organization_id", "academic_years.id"],
            name="fk_academic_curricula_tenant_year",
        ),
    )

    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    academic_year_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class CurriculumCourseModel(
    AcademicTenantModelMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a required or elective curriculum course."""

    __tablename__ = "academic_curriculum_courses"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_curriculum_courses_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "curriculum_id",
            "course_id",
            name="uq_academic_curriculum_courses_tenant_curriculum_course",
        ),
        ForeignKeyConstraint(
            ["organization_id", "curriculum_id"],
            [
                "academic_program_curricula.organization_id",
                "academic_program_curricula.id",
            ],
            name="fk_academic_curriculum_courses_tenant_curriculum",
        ),
        ForeignKeyConstraint(
            ["organization_id", "course_id"],
            ["academic_courses.organization_id", "academic_courses.id"],
            name="fk_academic_curriculum_courses_tenant_course",
        ),
        CheckConstraint(
            "credits > 0",
            name="positive_credits",
        ),
    )

    curriculum_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    course_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    credits: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)


class CurriculumPrerequisiteModel(
    AcademicTenantModelMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a prerequisite for one curriculum course."""

    __tablename__ = "academic_curriculum_prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "curriculum_course_id",
            "prerequisite_course_id",
            name="uq_academic_prerequisites_tenant_item_prerequisite",
        ),
        ForeignKeyConstraint(
            ["organization_id", "curriculum_course_id"],
            [
                "academic_curriculum_courses.organization_id",
                "academic_curriculum_courses.id",
            ],
            name="fk_academic_prerequisites_tenant_curriculum_course",
        ),
        ForeignKeyConstraint(
            ["organization_id", "prerequisite_course_id"],
            ["academic_courses.organization_id", "academic_courses.id"],
            name="fk_academic_prerequisites_tenant_course",
        ),
    )

    curriculum_course_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    prerequisite_course_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )


class CourseSelectionPolicyModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist a configurable program and term selection policy."""

    __tablename__ = "academic_course_selection_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "program_id",
            "term_id",
            name="uq_academic_selection_policies_tenant_program_term",
        ),
        ForeignKeyConstraint(
            ["organization_id", "program_id"],
            ["academic_programs.organization_id", "academic_programs.id"],
            name="fk_academic_selection_policies_tenant_program",
        ),
        ForeignKeyConstraint(
            ["organization_id", "term_id"],
            ["academic_terms.organization_id", "academic_terms.id"],
            name="fk_academic_selection_policies_tenant_term",
        ),
        CheckConstraint(
            "maximum_credits > 0",
            name="positive_max_credits",
        ),
    )

    program_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    term_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    education_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    maximum_credits: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CourseSelectionRequestModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one course-selection request and decision state."""

    __tablename__ = "academic_course_selection_requests"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_selection_requests_organization_id_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "student_academic_enrollment_id"],
            [
                "academic_student_enrollments.organization_id",
                "academic_student_enrollments.id",
            ],
            name="fk_academic_selection_requests_tenant_student_enrollment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "term_id"],
            ["academic_terms.organization_id", "academic_terms.id"],
            name="fk_academic_selection_requests_tenant_term",
        ),
        CheckConstraint(
            "requested_credits > 0",
            name="positive_credits",
        ),
    )

    student_academic_enrollment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    term_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_credits: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    submitted_by: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    decided_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class CourseSelectionRequestOfferingModel(
    AcademicTenantModelMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist one selected offering without using unvalidated JSON."""

    __tablename__ = "academic_course_selection_request_offerings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "request_id",
            "course_offering_id",
            name="uq_academic_request_offerings_tenant_request_offering",
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            [
                "academic_course_selection_requests.organization_id",
                "academic_course_selection_requests.id",
            ],
            name="fk_academic_request_offerings_tenant_request",
        ),
        ForeignKeyConstraint(
            ["organization_id", "course_offering_id"],
            [
                "academic_course_offerings.organization_id",
                "academic_course_offerings.id",
            ],
            name="fk_academic_request_offerings_tenant_offering",
        ),
    )

    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    course_offering_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )


class CourseSelectionOverrideModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist auditable metadata for an administrative rule override."""

    __tablename__ = "academic_course_selection_overrides"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_academic_selection_overrides_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "request_id",
            name="uq_academic_selection_overrides_tenant_request",
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            [
                "academic_course_selection_requests.organization_id",
                "academic_course_selection_requests.id",
            ],
            name="fk_academic_selection_overrides_tenant_request",
        ),
    )

    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    override_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class CourseSelectionOverrideViolationModel(
    AcademicTenantModelMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist each overridden rule as an explicit relational record."""

    __tablename__ = "academic_course_selection_override_violations"
    __table_args__ = (
        Index(
            "ix_academic_override_violations_org",
            "organization_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "override_id"],
            [
                "academic_course_selection_overrides.organization_id",
                "academic_course_selection_overrides.id",
            ],
            name="fk_academic_override_violations_tenant_override",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    override_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    related_identifier: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )


class CourseSelectionApprovalModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist append-only advisor or administrator decision history."""

    __tablename__ = "academic_course_selection_approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            [
                "academic_course_selection_requests.organization_id",
                "academic_course_selection_requests.id",
            ],
            name="fk_academic_selection_approvals_tenant_request",
        ),
    )

    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class CourseEnrollmentModel(
    AcademicTenantModelMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    BaseModel,
):
    """Persist official student enrollment in a course offering."""

    __tablename__ = "academic_course_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "student_academic_enrollment_id",
            "course_offering_id",
            name="uq_academic_course_enrollments_tenant_student_offering",
        ),
        ForeignKeyConstraint(
            ["organization_id", "student_academic_enrollment_id"],
            [
                "academic_student_enrollments.organization_id",
                "academic_student_enrollments.id",
            ],
            name="fk_academic_course_enrollments_tenant_student_enrollment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "course_offering_id"],
            [
                "academic_course_offerings.organization_id",
                "academic_course_offerings.id",
            ],
            name="fk_academic_course_enrollments_tenant_offering",
        ),
        ForeignKeyConstraint(
            ["organization_id", "selection_request_id"],
            [
                "academic_course_selection_requests.organization_id",
                "academic_course_selection_requests.id",
            ],
            name="fk_academic_course_enrollments_tenant_selection_request",
        ),
        CheckConstraint(
            "credits > 0",
            name="positive_credits",
        ),
    )

    student_academic_enrollment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    course_offering_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    credits: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    selection_request_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )


__all__ = [
    "AcademicCalendarEventModel",
    "AcademicYearModel",
    "AdmissionsEnrollmentRegistrationModel",
    "CohortModel",
    "CourseEnrollmentModel",
    "CourseModel",
    "CourseOfferingMeetingModel",
    "CourseOfferingModel",
    "CourseSelectionApprovalModel",
    "CourseSelectionOverrideModel",
    "CourseSelectionOverrideViolationModel",
    "CourseSelectionPolicyModel",
    "CourseSelectionRequestModel",
    "CourseSelectionRequestOfferingModel",
    "CurriculumCourseModel",
    "CurriculumPrerequisiteModel",
    "DepartmentModel",
    "FacultyModel",
    "ProgramCurriculumModel",
    "ProgramModel",
    "RoomModel",
    "StudentAcademicEnrollmentModel",
    "TeacherAssignmentModel",
    "TermModel",
]
