"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import {
  parseCourseSelectionRequest,
  type CourseSelectionRequest,
} from "@/lib/api/course-selection";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";

function requestLabel(requestId: string): string {
  return requestId.slice(0, 8);
}

export function EnrollmentApprovals({
  canDecide,
  initialRequests,
  organizationId,
}: {
  readonly canDecide: boolean;
  readonly initialRequests: readonly CourseSelectionRequest[];
  readonly organizationId: string;
}) {
  const [requests, setRequests] = useState(initialRequests);
  const [pendingRequestId, setPendingRequestId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function decide(
    request: CourseSelectionRequest,
    approved: boolean,
    reason?: string,
  ): Promise<void> {
    setPendingRequestId(request.id);
    setMessage(null);
    setError(null);
    try {
      const updated = await clientApiRequest(
        `/api/v1/academics/course-selection-requests/${encodeURIComponent(request.id)}/decision`,
        parseCourseSelectionRequest,
        {
          method: "PATCH",
          organizationId,
          body: approved ? { approved: true } : { approved: false, reason },
        },
      );
      setRequests((current) =>
        current.filter((candidate) => candidate.id !== updated.id),
      );
      setMessage(
        `Course selection ${requestLabel(updated.id)} was ${updated.status}.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The course-selection decision could not be saved.",
      );
    } finally {
      setPendingRequestId(null);
    }
  }

  function reject(
    event: FormEvent<HTMLFormElement>,
    request: CourseSelectionRequest,
  ): void {
    event.preventDefault();
    const reason = String(
      new FormData(event.currentTarget).get("reason") ?? "",
    ).trim();
    if (!reason) {
      setMessage(null);
      setError("A rejection reason is required.");
      return;
    }
    void decide(request, false, reason);
  }

  return (
    <div className="notification-layout">
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
      {!canDecide ? (
        <p className="inline-notice">
          Your current membership cannot decide course-selection requests.
        </p>
      ) : !csrfAvailable ? (
        <p className="inline-notice">
          Decisions are unavailable because the session has no CSRF token.
        </p>
      ) : null}
      {requests.length === 0 ? (
        <EmptyState message="No course-selection requests are awaiting a decision." />
      ) : (
        <section aria-labelledby="pending-course-selections">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Pending review</p>
              <h2 id="pending-course-selections">Course selections</h2>
            </div>
            <span className="status-pill">
              {requests.length.toLocaleString()} pending
            </span>
          </div>
          <div className="resource-grid">
            {requests.map((request) => {
              const busy = pendingRequestId === request.id;
              const disabled =
                !canDecide || !csrfAvailable || pendingRequestId !== null;
              const label = requestLabel(request.id);
              return (
                <article className="resource-card" key={request.id}>
                  <div className="resource-card-heading">
                    <div>
                      <p className="eyebrow">Request {label}</p>
                      <h2>{request.requestedCredits} requested credits</h2>
                    </div>
                    <span className="status-pill">{request.status}</span>
                  </div>
                  <dl className="resource-metadata">
                    <div>
                      <dt>Student enrollment</dt>
                      <dd>{request.studentAcademicEnrollmentId}</dd>
                    </div>
                    <div>
                      <dt>Term</dt>
                      <dd>{request.termId}</dd>
                    </div>
                    <div>
                      <dt>Offerings</dt>
                      <dd>{request.offeringIds.join(", ")}</dd>
                    </div>
                  </dl>
                  {request.overrideReason ? (
                    <p>
                      Override request: {request.overrideReason}
                      {request.overriddenRules.length > 0
                        ? ` (${request.overriddenRules.join(", ")})`
                        : ""}
                    </p>
                  ) : null}
                  <div className="button-row">
                    <button
                      className="button button-small"
                      type="button"
                      disabled={disabled}
                      onClick={() => void decide(request, true)}
                    >
                      {busy ? "Saving decision…" : `Approve ${label}`}
                    </button>
                  </div>
                  <form onSubmit={(event) => reject(event, request)}>
                    <div className="form-grid">
                      <label className="form-span">
                        Rejection reason for {label}
                        <textarea
                          name="reason"
                          required
                          maxLength={1000}
                          rows={3}
                          disabled={disabled}
                        />
                      </label>
                    </div>
                    <div className="form-actions">
                      <button
                        className="button button-secondary button-small"
                        type="submit"
                        disabled={disabled}
                      >
                        {busy ? "Saving decision…" : `Reject ${label}`}
                      </button>
                    </div>
                  </form>
                </article>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
