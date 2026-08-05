"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";

function parseAccepted(): true {
  return true;
}

export function GradeAmendmentForm({
  canSubmit,
  organizationId,
}: {
  readonly canSubmit: boolean;
  readonly organizationId: string;
}) {
  const [status, setStatus] = useState<"idle" | "submitting" | "submitted">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setError(null);
    setStatus("submitting");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const finalGradeId = String(form.get("officialGradeId") ?? "").trim();
    const gradingScaleId = String(form.get("gradingScaleId") ?? "").trim();
    try {
      await clientApiRequest(
        `/api/v1/grading/final-grades/${encodeURIComponent(finalGradeId)}/revisions`,
        parseAccepted,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            raw_score: String(form.get("rawScore") ?? "").trim(),
            explanation: String(form.get("explanation") ?? "").trim(),
            grading_scale_id: gradingScaleId || null,
            expected_revision_number: Number(
              form.get("expectedRevisionNumber") ?? 0,
            ),
          },
        },
      );
      setStatus("submitted");
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The amendment request could not be submitted.",
      );
      setStatus("idle");
    }
  }

  return (
    <form className="form-card" onSubmit={(event) => void submit(event)}>
      <div className="form-grid">
        <label>
          Official grade identifier
          <input name="officialGradeId" required autoComplete="off" />
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
          Current revision number
          <input
            name="expectedRevisionNumber"
            required
            type="number"
            min={0}
            step={1}
            inputMode="numeric"
          />
          <small>
            This prevents overwriting a grade that changed after the page was
            opened.
          </small>
        </label>
        <label className="form-span">
          Replacement grading scale identifier (optional)
          <input name="gradingScaleId" autoComplete="off" />
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
            The explanation is sent to the official grading workflow and must be
            preserved with grade history.
          </small>
        </label>
      </div>
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      {status === "submitted" ? (
        <p className="inline-success" role="status">
          The official grade revision was recorded with its explanation.
        </p>
      ) : null}
      {!canSubmit ? (
        <p className="inline-notice">
          Your current membership does not grant official-grade revision
          permission. The explanation flow remains read-only.
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
          disabled={!canSubmit || !csrfAvailable || status === "submitting"}
        >
          {status === "submitting" ? "Recording…" : "Record grade revision"}
        </button>
      </div>
    </form>
  );
}
