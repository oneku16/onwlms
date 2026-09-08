"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import {
  parseStudentEnrollment,
  type StudentEnrollmentView,
} from "@/lib/api/academics";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { resourceTitle, type ResourceSummary } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { isoFromDateTimeInput, textValue } from "@/lib/forms";

export function StudentEnrollmentAdministration({
  academicYears,
  canManage,
  cohorts,
  initialEnrollments,
  organizationId,
  programs,
  students,
}: {
  readonly academicYears: readonly ResourceSummary[];
  readonly canManage: boolean;
  readonly cohorts: readonly ResourceSummary[];
  readonly initialEnrollments: readonly StudentEnrollmentView[];
  readonly organizationId: string;
  readonly programs: readonly ResourceSummary[];
  readonly students: readonly ResourceSummary[];
}) {
  const [enrollments, setEnrollments] = useState(initialEnrollments);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingEnrollmentId, setPendingEnrollmentId] = useState<string | null>(
    null,
  );
  const [lifecycleMessage, setLifecycleMessage] = useState<string | null>(null);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function transition(
    event: FormEvent<HTMLFormElement>,
    enrollment: StudentEnrollmentView,
    action: "withdraw" | "complete",
  ): Promise<void> {
    event.preventDefault();
    const explanation = textValue(
      new FormData(event.currentTarget).get("explanation"),
    );
    setLifecycleMessage(null);
    setLifecycleError(null);
    if (!explanation) {
      setLifecycleError(
        `An explanation is required to ${action} an enrollment.`,
      );
      return;
    }
    setPendingEnrollmentId(enrollment.id);
    try {
      const updated = await clientApiRequest(
        `/api/v1/academics/student-enrollments/${encodeURIComponent(enrollment.id)}/${action}`,
        parseStudentEnrollment,
        { method: "POST", organizationId, body: { explanation } },
      );
      setEnrollments((current) =>
        current.map((candidate) =>
          candidate.id === updated.id ? updated : candidate,
        ),
      );
      setLifecycleMessage(
        `The enrollment for ${resourceTitle(students, updated.studentId, "Student")} is now ${updated.status}.`,
      );
    } catch (caught) {
      setLifecycleError(
        caught instanceof ApiError
          ? caught.message
          : "The enrollment lifecycle could not be changed.",
      );
    } finally {
      setPendingEnrollmentId(null);
    }
  }

  async function enrollStudent(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setMessage(null);
    setError(null);
    const enrolledAt = isoFromDateTimeInput(form.get("enrolledAt"));
    if (!enrolledAt) {
      setError("Enter a valid enrollment date and time.");
      return;
    }
    const cohortId = textValue(form.get("cohortId"));
    setSubmitting(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/academics/student-enrollments",
        parseStudentEnrollment,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            student_id: textValue(form.get("studentId")),
            program_id: textValue(form.get("programId")),
            academic_year_id: textValue(form.get("academicYearId")),
            cohort_id: cohortId === "" ? null : cohortId,
            enrolled_at: enrolledAt,
          },
        },
      );
      setEnrollments((current) => [...current, created]);
      setMessage(
        `${resourceTitle(students, created.studentId, "Student")} was enrolled in ${resourceTitle(programs, created.programId, "Program")}.`,
      );
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The student enrollment could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {lifecycleError ? (
        <p className="inline-alert" role="alert">
          {lifecycleError}
        </p>
      ) : null}
      {lifecycleMessage ? (
        <p className="inline-success" role="status">
          {lifecycleMessage}
        </p>
      ) : null}
      {enrollments.length === 0 ? (
        <EmptyState message="No student enrollments are available." />
      ) : (
        <section aria-labelledby="student-enrollments-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current records</p>
              <h2 id="student-enrollments-heading">
                {enrollments.length.toLocaleString()} student enrollment
                {enrollments.length === 1 ? "" : "s"}
              </h2>
            </div>
          </div>
          <div className="resource-grid">
            {enrollments.map((enrollment) => (
              <article className="resource-card" key={enrollment.id}>
                <div className="resource-card-heading">
                  <div>
                    <h2>
                      {resourceTitle(students, enrollment.studentId, "Student")}
                    </h2>
                    <p>
                      {resourceTitle(programs, enrollment.programId, "Program")}{" "}
                      ·{" "}
                      {resourceTitle(
                        academicYears,
                        enrollment.academicYearId,
                        "Academic year",
                      )}
                    </p>
                  </div>
                  <span className="status-pill">{enrollment.status}</span>
                </div>
                <dl className="resource-metadata">
                  <div>
                    <dt>Cohort</dt>
                    <dd>
                      {enrollment.cohortId === null
                        ? "None"
                        : resourceTitle(cohorts, enrollment.cohortId, "Cohort")}
                    </dd>
                  </div>
                  <div>
                    <dt>Enrolled</dt>
                    <dd>
                      <time dateTime={enrollment.enrolledAt}>
                        {new Intl.DateTimeFormat(undefined, {
                          dateStyle: "medium",
                          timeStyle: "short",
                        }).format(new Date(enrollment.enrolledAt))}
                      </time>
                    </dd>
                  </div>
                </dl>
                {enrollment.status === "active" ? (
                  <>
                    <form
                      className="form-grid"
                      onSubmit={(event) =>
                        void transition(event, enrollment, "complete")
                      }
                    >
                      <label className="form-span">
                        Completion explanation for{" "}
                        {resourceTitle(
                          students,
                          enrollment.studentId,
                          "Student",
                        )}
                        <input name="explanation" maxLength={2000} />
                      </label>
                      <div className="form-actions">
                        <button
                          className="button button-small"
                          type="submit"
                          disabled={
                            !canManage ||
                            !csrfAvailable ||
                            pendingEnrollmentId === enrollment.id
                          }
                        >
                          Complete enrollment
                        </button>
                      </div>
                    </form>
                    <form
                      className="form-grid"
                      onSubmit={(event) =>
                        void transition(event, enrollment, "withdraw")
                      }
                    >
                      <label className="form-span">
                        Withdrawal explanation for{" "}
                        {resourceTitle(
                          students,
                          enrollment.studentId,
                          "Student",
                        )}
                        <input name="explanation" maxLength={2000} />
                        <small>
                          Withdrawing also withdraws every enrolled course of
                          this academic enrollment.
                        </small>
                      </label>
                      <div className="form-actions">
                        <button
                          className="button button-secondary button-small"
                          type="submit"
                          disabled={
                            !canManage ||
                            !csrfAvailable ||
                            pendingEnrollmentId === enrollment.id
                          }
                        >
                          Withdraw enrollment
                        </button>
                      </div>
                    </form>
                  </>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      )}
      <form
        className="form-card"
        onSubmit={(event) => void enrollStudent(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Academic enrollment</p>
            <h2>Enroll a student</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Student profile
            <select name="studentId" required defaultValue="">
              <ResourceOptions
                includeIdentifier
                placeholder="Select a tenant student"
                resources={students}
              />
            </select>
          </label>
          <label>
            Program
            <select name="programId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a program"
                resources={programs}
              />
            </select>
          </label>
          <label>
            Academic year
            <select name="academicYearId" required defaultValue="">
              <ResourceOptions
                placeholder="Select an academic year"
                resources={academicYears}
              />
            </select>
          </label>
          <label>
            Cohort (optional)
            <select name="cohortId" defaultValue="">
              <option value="">No cohort</option>
              {cohorts.map((cohort) => (
                <option key={cohort.id} value={cohort.id}>
                  {cohort.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Enrolled at
            <input name="enrolledAt" type="datetime-local" required />
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage student enrollments."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canManage ||
              !csrfAvailable ||
              submitting ||
              students.length === 0 ||
              programs.length === 0 ||
              academicYears.length === 0
            }
          >
            {submitting ? "Enrolling…" : "Enroll student"}
          </button>
        </div>
      </form>
    </div>
  );
}
