"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { parseCourseSelectionRequest } from "@/lib/api/course-selection";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function CourseSelectionForm({
  canSubmit,
  organizationId,
}: {
  readonly canSubmit: boolean;
  readonly organizationId: string;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function submitSelection(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const studentAcademicEnrollmentId = String(
      form.get("studentAcademicEnrollmentId") ?? "",
    ).trim();
    const termId = String(form.get("termId") ?? "").trim();
    const offeringIds = String(form.get("offeringIds") ?? "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    const overrideReason = String(form.get("overrideReason") ?? "").trim();

    setMessage(null);
    setError(null);
    if (
      !uuidPattern.test(studentAcademicEnrollmentId) ||
      !uuidPattern.test(termId) ||
      offeringIds.length === 0 ||
      offeringIds.some((offeringId) => !uuidPattern.test(offeringId))
    ) {
      setError(
        "Enter valid UUIDs for the academic enrollment, term, and every course offering.",
      );
      return;
    }
    if (new Set(offeringIds).size !== offeringIds.length) {
      setError("Each course offering UUID may be submitted only once.");
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
            student_academic_enrollment_id: studentAcademicEnrollmentId,
            term_id: termId,
            offering_ids: offeringIds,
            ...(overrideReason ? { override_reason: overrideReason } : {}),
          },
        },
      );
      setMessage(
        `Course selection ${request.id} was submitted with ${request.requestedCredits} requested credits and is ${request.status}.`,
      );
      formElement.reset();
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
        Use the academic-enrollment identifier issued for your current student
        record. OwnSIS verifies that it belongs to your signed-in identity.
      </p>
      <div className="form-grid">
        <label>
          Student academic enrollment UUID
          <input
            name="studentAcademicEnrollmentId"
            required
            autoComplete="off"
            placeholder="00000000-0000-0000-0000-000000000000"
          />
        </label>
        <label>
          Term UUID
          <input
            name="termId"
            required
            autoComplete="off"
            placeholder="00000000-0000-0000-0000-000000000000"
          />
        </label>
        <label className="form-span">
          Course offering UUIDs
          <textarea
            name="offeringIds"
            required
            rows={4}
            placeholder="Separate multiple UUIDs with commas"
          />
          <small>
            Submit at least one offering. Duplicate identifiers are not
            accepted.
          </small>
        </label>
        <label className="form-span">
          Override reason (optional)
          <textarea name="overrideReason" maxLength={1000} rows={4} />
          <small>
            Providing a reason requests policy review; it does not bypass
            approval or academic rules.
          </small>
        </label>
      </div>
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
          disabled={!canSubmit || !csrfAvailable || submitting}
        >
          {submitting ? "Submitting selection…" : "Submit course selection"}
        </button>
      </div>
    </form>
  );
}
