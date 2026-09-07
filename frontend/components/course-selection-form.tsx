"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import {
  parseCourseSelectionRequest,
  type StudentCourseSelectionContext,
} from "@/lib/api/course-selection";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";

const weekdayNames = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

export function CourseSelectionForm({
  canSubmit,
  context,
  organizationId,
}: {
  readonly canSubmit: boolean;
  readonly context: StudentCourseSelectionContext;
  readonly organizationId: string;
}) {
  const initialEnrollment = context.enrollments[0];
  const [enrollmentId, setEnrollmentId] = useState(initialEnrollment?.id ?? "");
  const [termId, setTermId] = useState(initialEnrollment?.terms[0]?.id ?? "");
  const [offeringIds, setOfferingIds] = useState<readonly string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();
  const enrollment = context.enrollments.find(
    (candidate) => candidate.id === enrollmentId,
  );
  const term = enrollment?.terms.find((candidate) => candidate.id === termId);

  function chooseEnrollment(nextEnrollmentId: string): void {
    const nextEnrollment = context.enrollments.find(
      (candidate) => candidate.id === nextEnrollmentId,
    );
    setEnrollmentId(nextEnrollmentId);
    setTermId(nextEnrollment?.terms[0]?.id ?? "");
    setOfferingIds([]);
  }

  function chooseOffering(offeringId: string, checked: boolean): void {
    setOfferingIds((current) =>
      checked
        ? [...current, offeringId]
        : current.filter((candidate) => candidate !== offeringId),
    );
  }

  async function submitSelection(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    setMessage(null);
    setError(null);
    if (!enrollment || !term || offeringIds.length === 0) {
      setError(
        "Choose an active enrollment, an open term, and at least one course.",
      );
      return;
    }

    setSubmitting(true);
    try {
      const request = await clientApiRequest(
        "/api/v1/academics/course-selection-requests",
        parseCourseSelectionRequest,
        {
          method: "POST",
          organizationId,
          body: {
            student_academic_enrollment_id: enrollment.id,
            term_id: term.id,
            offering_ids: offeringIds,
          },
        },
      );
      setMessage(
        `Course selection ${request.id} was submitted with ${request.requestedCredits} requested credits and is ${request.status}.`,
      );
      setOfferingIds([]);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The course-selection request could not be submitted.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (context.enrollments.length === 0) {
    return (
      <p className="empty-state">
        No active academic enrollment is available for course selection.
      </p>
    );
  }

  return (
    <form
      className="form-card"
      onSubmit={(event) => void submitSelection(event)}
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Term enrollment</p>
          <h2>Submit a course selection</h2>
        </div>
      </div>
      <p className="inline-notice">
        The choices below come from your active academic enrollment, open terms,
        current curriculum, and available course offerings.
      </p>
      <div className="form-grid">
        <label>
          Academic enrollment
          <select
            name="studentAcademicEnrollmentId"
            onChange={(event) => chooseEnrollment(event.currentTarget.value)}
            value={enrollmentId}
          >
            {context.enrollments.map((option) => (
              <option key={option.id} value={option.id}>
                {option.programName}
              </option>
            ))}
          </select>
        </label>
        <label>
          Open term
          <select
            name="termId"
            onChange={(event) => {
              setTermId(event.currentTarget.value);
              setOfferingIds([]);
            }}
            value={termId}
          >
            {enrollment?.terms.length ? (
              enrollment.terms.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))
            ) : (
              <option value="">No open selection term</option>
            )}
          </select>
        </label>
      </div>
      {term ? (
        <p className="inline-notice">
          Select up to {term.maximumCredits} credits before{" "}
          {new Date(term.deadline).toLocaleString()}.{" "}
          {term.approvalRequired
            ? "An authorized reviewer must approve the request."
            : "Approval is not normally required."}
        </p>
      ) : null}
      <fieldset disabled={!term || submitting}>
        <legend>Available course offerings</legend>
        {term?.offerings.length ? (
          <div className="resource-grid">
            {term.offerings.map((offering) => (
              <label className="resource-card" key={offering.id}>
                <span className="checkbox-label">
                  <input
                    checked={offeringIds.includes(offering.id)}
                    name="offeringIds"
                    onChange={(event) =>
                      chooseOffering(offering.id, event.currentTarget.checked)
                    }
                    type="checkbox"
                    value={offering.id}
                  />
                  <strong>
                    {offering.courseCode} · {offering.courseTitle}
                  </strong>
                </span>
                <small>
                  Section {offering.sectionCode} · {offering.credits} credits ·
                  capacity {offering.capacity}
                </small>
                {offering.meetingWindows.map((window) => (
                  <small
                    key={`${window.weekday}-${window.startsAt}-${window.endsAt}`}
                  >
                    {weekdayNames[window.weekday - 1]} {window.startsAt}–
                    {window.endsAt}
                  </small>
                ))}
              </label>
            ))}
          </div>
        ) : (
          <p className="empty-state">
            No curriculum-backed offerings are available for this term.
          </p>
        )}
      </fieldset>
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className="inline-success" role="status">
          {message}
        </p>
      ) : null}
      {!canSubmit ? (
        <p className="inline-notice">
          Your current membership cannot submit course selections.
        </p>
      ) : !csrfAvailable ? (
        <p className="inline-notice">
          Submission is unavailable because the session has no CSRF token.
        </p>
      ) : null}
      <div className="form-actions">
        <button
          className="button"
          type="submit"
          disabled={
            !canSubmit ||
            !csrfAvailable ||
            submitting ||
            !term ||
            offeringIds.length === 0
          }
        >
          {submitting ? "Submitting selection…" : "Submit course selection"}
        </button>
      </div>
    </form>
  );
}
