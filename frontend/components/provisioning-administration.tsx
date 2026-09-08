"use client";

import { useState } from "react";

import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  isRetryableProvisioningJob,
  parseProvisioningJob,
  type ProvisioningJobView,
} from "@/lib/api/provisioning";
import { useCsrfProtection } from "@/lib/api/use-csrf";

function formatInstant(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
}

export function ProvisioningAdministration({
  canRetry,
  initialJobs,
  organizationId,
}: {
  readonly canRetry: boolean;
  readonly initialJobs: readonly ProvisioningJobView[];
  readonly organizationId: string;
}) {
  const [jobs, setJobs] = useState(initialJobs);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function retry(job: ProvisioningJobView): Promise<void> {
    setPendingId(job.id);
    setMessage(null);
    setError(null);
    try {
      const updated = await clientApiRequest(
        `/api/v1/operations/provisioning/${encodeURIComponent(job.id)}/retry`,
        parseProvisioningJob,
        { method: "POST", organizationId },
      );
      setJobs((current) =>
        current.map((candidate) =>
          candidate.id === updated.id ? updated : candidate,
        ),
      );
      setMessage(
        `${updated.target} provisioning ${updated.id.slice(0, 8)} was retried and is now ${updated.status}.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The provisioning job could not be retried.",
      );
    } finally {
      setPendingId(null);
    }
  }

  if (jobs.length === 0) {
    return <EmptyState message="No provisioning jobs are available." />;
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
      {!canRetry ? (
        <p className="inline-notice">
          Your current membership cannot retry provisioning jobs.
        </p>
      ) : !csrfAvailable ? (
        <p className="inline-notice">
          Retries are unavailable because the session has no CSRF token.
        </p>
      ) : (
        <p className="inline-notice">
          Only pending or retry-marked jobs can be retried; failed jobs are
          reported as evidence and cannot be re-run from here.
        </p>
      )}
      <section aria-labelledby="provisioning-jobs-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Current records</p>
            <h2 id="provisioning-jobs-heading">
              {jobs.length.toLocaleString()} provisioning job
              {jobs.length === 1 ? "" : "s"}
            </h2>
          </div>
        </div>
        <div className="resource-grid">
          {jobs.map((job) => (
            <article className="resource-card" key={job.id}>
              <div className="resource-card-heading">
                <div>
                  <h2>{job.target} provisioning</h2>
                  <p>
                    {job.subjectType} {job.subjectId.slice(0, 8)}
                  </p>
                </div>
                <span className="status-pill">{job.status}</span>
              </div>
              <dl className="resource-metadata">
                <div>
                  <dt>Attempts</dt>
                  <dd>{job.attempts.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{formatInstant(job.updatedAt)}</dd>
                </div>
                {job.lastErrorCode ? (
                  <div>
                    <dt>Last error</dt>
                    <dd>{job.lastErrorCode}</dd>
                  </div>
                ) : null}
                {job.externalReference ? (
                  <div>
                    <dt>External reference</dt>
                    <dd>{job.externalReference}</dd>
                  </div>
                ) : null}
              </dl>
              {isRetryableProvisioningJob(job) ? (
                <div className="button-row">
                  <button
                    className="button button-secondary button-small"
                    type="button"
                    disabled={!canRetry || !csrfAvailable || pendingId !== null}
                    onClick={() => void retry(job)}
                  >
                    {pendingId === job.id
                      ? "Retrying…"
                      : `Retry ${job.target} ${job.id.slice(0, 8)}`}
                  </button>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
