"use client";

import type { FormEvent } from "react";
import { useRef, useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseCurrentRevisionNumber,
  parseFinalGradeMutation,
  parseTranscriptGradeChoices,
  type AcademicEnrollmentChoice,
  type GradingScaleChoice,
  type TranscriptGradeChoice,
} from "@/lib/api/grading";
import type { ResourceSummary } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";

type LoadingState = "idle" | "transcript" | "revision" | "submitting";

function labelFor(
  resources: readonly ResourceSummary[],
  id: string,
  fallback: string,
): string {
  return (
    resources.find((resource) => resource.id === id)?.title ??
    `${fallback} ${id.slice(0, 8)}`
  );
}

export function GradeAmendmentForm({
  canReviseClosedTerm,
  canSubmit,
  courses,
  enrollments,
  gradingScales,
  organizationId,
  programs,
  students,
  terms,
}: {
  readonly canReviseClosedTerm: boolean;
  readonly canSubmit: boolean;
  readonly courses: readonly ResourceSummary[];
  readonly enrollments: readonly AcademicEnrollmentChoice[];
  readonly gradingScales: readonly GradingScaleChoice[];
  readonly organizationId: string;
  readonly programs: readonly ResourceSummary[];
  readonly students: readonly ResourceSummary[];
  readonly terms: readonly ResourceSummary[];
}) {
  const [enrollmentId, setEnrollmentId] = useState("");
  const [grades, setGrades] = useState<readonly TranscriptGradeChoice[]>([]);
  const [finalGradeId, setFinalGradeId] = useState("");
  const [revisionNumber, setRevisionNumber] = useState<number | null>(null);
  const [loading, setLoading] = useState<LoadingState>("idle");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadSequence = useRef(0);
  const csrfAvailable = useCsrfProtection();

  async function chooseEnrollment(nextEnrollmentId: string): Promise<void> {
    const sequence = ++loadSequence.current;
    setEnrollmentId(nextEnrollmentId);
    setGrades([]);
    setFinalGradeId("");
    setRevisionNumber(null);
    setSubmitted(false);
    setError(null);
    if (!nextEnrollmentId) {
      setLoading("idle");
      return;
    }
    setLoading("transcript");
    try {
      const nextGrades = await clientApiRequest(
        `/api/v1/grading/students/${encodeURIComponent(nextEnrollmentId)}/transcript`,
        parseTranscriptGradeChoices,
        { organizationId },
      );
      if (loadSequence.current === sequence) {
        setGrades(nextGrades);
      }
    } catch (caught) {
      if (loadSequence.current === sequence) {
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Official grades could not be loaded for this enrollment.",
        );
      }
    } finally {
      if (loadSequence.current === sequence) {
        setLoading("idle");
      }
    }
  }

  async function chooseGrade(nextFinalGradeId: string): Promise<void> {
    const sequence = ++loadSequence.current;
    setFinalGradeId(nextFinalGradeId);
    setRevisionNumber(null);
    setSubmitted(false);
    setError(null);
    if (!nextFinalGradeId) {
      setLoading("idle");
      return;
    }
    setLoading("revision");
    try {
      const currentRevision = await clientApiRequest(
        `/api/v1/grading/final-grades/${encodeURIComponent(nextFinalGradeId)}/revisions`,
        parseCurrentRevisionNumber,
        { organizationId },
      );
      if (loadSequence.current === sequence) {
        setRevisionNumber(currentRevision);
      }
    } catch (caught) {
      if (loadSequence.current === sequence) {
        setError(
          caught instanceof ApiError
            ? caught.message
            : "The current grade revision could not be verified.",
        );
      }
    } finally {
      if (loadSequence.current === sequence) {
        setLoading("idle");
      }
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!canSubmit || !finalGradeId || revisionNumber === null) {
      return;
    }
    setError(null);
    setSubmitted(false);
    setLoading("submitting");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const gradingScaleId = String(form.get("gradingScaleId") ?? "").trim();
    try {
      const revised = await clientApiRequest(
        `/api/v1/grading/final-grades/${encodeURIComponent(finalGradeId)}/revisions`,
        parseFinalGradeMutation,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            raw_score: String(form.get("rawScore") ?? "").trim(),
            explanation: String(form.get("explanation") ?? "").trim(),
            grading_scale_id: gradingScaleId || null,
            expected_revision_number: revisionNumber,
          },
        },
      );
      setRevisionNumber(revised.revisionNumber);
      setSubmitted(true);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The amendment request could not be submitted.",
      );
    } finally {
      setLoading("idle");
    }
  }

  return (
    <form className="form-card" onSubmit={(event) => void submit(event)}>
      <div className="form-grid">
        <label>
          Academic enrollment
          <select
            name="academicEnrollmentId"
            onChange={(event) =>
              void chooseEnrollment(event.currentTarget.value)
            }
            required
            value={enrollmentId}
          >
            <option value="" disabled>
              Select an authorized enrollment
            </option>
            {enrollments.map((enrollment) => (
              <option key={enrollment.id} value={enrollment.id}>
                {labelFor(students, enrollment.studentId, "Student")} ·{" "}
                {labelFor(programs, enrollment.programId, "Program")} ·{" "}
                {enrollment.status}
              </option>
            ))}
          </select>
        </label>
        <label>
          Official grade
          <select
            disabled={!enrollmentId || loading === "transcript"}
            name="officialGradeId"
            onChange={(event) => void chooseGrade(event.currentTarget.value)}
            required
            value={finalGradeId}
          >
            <option value="" disabled>
              {loading === "transcript"
                ? "Loading official grades…"
                : "Select an official grade"}
            </option>
            {grades.map((grade) => {
              const term = terms.find(
                (candidate) => candidate.id === grade.termId,
              );
              const unavailableClosedTerm =
                term?.status === "closed" && !canReviseClosedTerm;
              return (
                <option
                  disabled={unavailableClosedTerm}
                  key={grade.finalGradeId}
                  value={grade.finalGradeId}
                >
                  {labelFor(courses, grade.courseId, "Course")} ·{" "}
                  {labelFor(terms, grade.termId, "Term")} · {grade.symbol}
                  {unavailableClosedTerm
                    ? " · closed-term permission required"
                    : ""}
                </option>
              );
            })}
          </select>
        </label>
        <label>
          Revised raw score
          <input
            name="rawScore"
            required
            inputMode="decimal"
            maxLength={24}
            autoComplete="off"
          />
        </label>
        <label>
          Replacement grading scale (optional)
          <select name="gradingScaleId" defaultValue="">
            <option value="">Keep the current grading scale</option>
            {gradingScales.map((scale) => (
              <option key={scale.id} value={scale.id}>
                {scale.name}
              </option>
            ))}
          </select>
        </label>
        <label className="form-span">
          Amendment explanation
          <textarea
            name="explanation"
            required
            minLength={10}
            maxLength={2000}
            rows={6}
          />
          <small>
            The explanation is retained with immutable official-grade history.
            The current revision is verified from that history before
            submission.
          </small>
        </label>
      </div>
      {finalGradeId ? (
        <p className="inline-notice" role="status">
          {loading === "revision"
            ? "Verifying current revision…"
            : revisionNumber === null
              ? "Current revision could not be verified."
              : `Current revision: ${revisionNumber}.`}
        </p>
      ) : enrollmentId &&
        loading === "idle" &&
        grades.length === 0 &&
        !error ? (
        <p className="inline-notice">
          This enrollment has no official grades available for amendment.
        </p>
      ) : null}
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      {submitted ? (
        <p className="inline-success" role="status">
          The official grade revision was recorded with its explanation.
        </p>
      ) : null}
      {!canSubmit ? (
        <p className="inline-notice">
          Your current membership does not grant official-grade revision
          permission.
        </p>
      ) : !csrfAvailable ? (
        <p className="inline-notice">
          Submission is unavailable because the session has no CSRF token.
        </p>
      ) : enrollments.length === 0 ? (
        <p className="inline-notice">
          No academic enrollments are available for authorized grade amendment.
        </p>
      ) : !canReviseClosedTerm ? (
        <p className="inline-notice">
          Closed-term revisions require the separate closed-term amendment
          permission.
        </p>
      ) : null}
      <div className="form-actions">
        <button
          className="button"
          type="submit"
          disabled={
            !canSubmit ||
            !csrfAvailable ||
            !finalGradeId ||
            revisionNumber === null ||
            loading !== "idle"
          }
        >
          {loading === "submitting" ? "Recording…" : "Record grade revision"}
        </button>
      </div>
    </form>
  );
}
