"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseGradeEvidenceList,
  parseReconciliationRun,
  type GradeEvidenceView,
  type ReconciliationRunView,
} from "@/lib/api/integrations";
import { parseFinalGradeMutation } from "@/lib/api/grading";
import type { ResourceSummary } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { optionalTextValue, textValue } from "@/lib/forms";

function shortReference(value: string): string {
  return value.slice(0, 8);
}

function formatInstant(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
}

function RunSummary({ run }: { readonly run: ReconciliationRunView }) {
  return (
    <article className="resource-card">
      <div className="resource-card-heading">
        <div>
          <h3>Run {shortReference(run.id)}</h3>
          <p>Started {formatInstant(run.startedAt)}</p>
        </div>
        <span className="status-pill">{run.status}</span>
      </div>
      <dl className="resource-metadata">
        <div>
          <dt>Offerings</dt>
          <dd>
            {run.offeringCount.toLocaleString()} ({" "}
            {run.unmappedOfferingCount.toLocaleString()} unmapped )
          </dd>
        </div>
        <div>
          <dt>Observed totals</dt>
          <dd>{run.observedCount.toLocaleString()}</dd>
        </div>
        <div>
          <dt>New evidence</dt>
          <dd>{run.newEvidenceCount.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Duplicates</dt>
          <dd>{run.duplicateCount.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Unmapped learners</dt>
          <dd>{run.unmappedUserCount.toLocaleString()}</dd>
        </div>
        {run.errorCode ? (
          <div>
            <dt>Error code</dt>
            <dd>{run.errorCode}</dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}

/**
 * Review Moodle-owned grade evidence. Evidence is never authoritative here:
 * accepting one item asks Grading to record or revise an official grade under
 * its own permission, closure, and explanation rules.
 */
export function GradeEvidenceReview({
  canReconcile,
  canReview,
  gradingScales,
  initialEvidence,
  initialRuns,
  organizationId,
  terms,
}: {
  readonly canReconcile: boolean;
  readonly canReview: boolean;
  readonly gradingScales: readonly ResourceSummary[];
  readonly initialEvidence: readonly GradeEvidenceView[];
  readonly initialRuns: readonly ReconciliationRunView[];
  readonly organizationId: string;
  readonly terms: readonly ResourceSummary[];
}) {
  const [evidence, setEvidence] = useState(initialEvidence);
  const [runs, setRuns] = useState(initialRuns);
  const [pendingEvidenceId, setPendingEvidenceId] = useState<string | null>(
    null,
  );
  const [reconciling, setReconciling] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();
  const pending = evidence.filter((item) => item.status === "pending");
  const resolved = evidence.filter((item) => item.status !== "pending");

  async function refreshEvidence(): Promise<void> {
    const refreshed = await clientApiRequest(
      "/api/v1/integrations/moodle/grade-evidence?limit=100",
      parseGradeEvidenceList,
      { organizationId },
    );
    setEvidence(refreshed);
  }

  async function accept(
    event: FormEvent<HTMLFormElement>,
    item: GradeEvidenceView,
  ): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const gradingScaleId = textValue(form.get("gradingScaleId"));
    setMessage(null);
    setError(null);
    if (!gradingScaleId) {
      setError("Select the official grading scale before accepting evidence.");
      return;
    }
    setPendingEvidenceId(item.id);
    try {
      const explanation = optionalTextValue(form.get("explanation"));
      const grade = await clientApiRequest(
        `/api/v1/grading/external-evidence/${encodeURIComponent(item.id)}/accept`,
        parseFinalGradeMutation,
        {
          method: "POST",
          organizationId,
          body: {
            grading_scale_id: gradingScaleId,
            ...(explanation === null ? {} : { explanation }),
          },
        },
      );
      await refreshEvidence();
      setMessage(
        grade.revisionNumber === 0
          ? `Evidence ${shortReference(item.id)} became official grade ${shortReference(grade.id)}.`
          : `Evidence ${shortReference(item.id)} revised official grade ${shortReference(grade.id)} to revision ${grade.revisionNumber}.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The evidence could not be accepted as an official grade.",
      );
    } finally {
      setPendingEvidenceId(null);
    }
  }

  async function reject(
    event: FormEvent<HTMLFormElement>,
    item: GradeEvidenceView,
  ): Promise<void> {
    event.preventDefault();
    const reason = textValue(new FormData(event.currentTarget).get("reason"));
    setMessage(null);
    setError(null);
    if (!reason) {
      setError("A rejection reason is required.");
      return;
    }
    setPendingEvidenceId(item.id);
    try {
      await clientApiRequest(
        `/api/v1/grading/external-evidence/${encodeURIComponent(item.id)}/reject`,
        () => null,
        { method: "POST", organizationId, body: { reason } },
      );
      await refreshEvidence();
      setMessage(`Evidence ${shortReference(item.id)} was rejected.`);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The evidence could not be rejected.",
      );
    } finally {
      setPendingEvidenceId(null);
    }
  }

  async function reconcile(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const termId = textValue(new FormData(formElement).get("termId"));
    setRunMessage(null);
    setRunError(null);
    if (!termId) {
      setRunError("Select the term to reconcile.");
      return;
    }
    setReconciling(true);
    try {
      const run = await clientApiRequest(
        "/api/v1/integrations/moodle/grade-reconciliations",
        parseReconciliationRun,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: { term_id: termId },
        },
      );
      setRuns((current) => [run, ...current]);
      await refreshEvidence();
      setRunMessage(
        `Run ${shortReference(run.id)} observed ${run.observedCount.toLocaleString()} totals and stored ${run.newEvidenceCount.toLocaleString()} new evidence records.`,
      );
      formElement.reset();
    } catch (caught) {
      setRunError(
        caught instanceof ApiError
          ? caught.message
          : "The reconciliation run could not be completed.",
      );
    } finally {
      setReconciling(false);
    }
  }

  return (
    <div className="notification-layout">
      <section aria-labelledby="grade-evidence-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">External learning evidence</p>
            <h2 id="grade-evidence-heading">Moodle grade evidence</h2>
          </div>
          <span className="status-pill">
            {pending.length.toLocaleString()} pending
          </span>
        </div>
        <p className="inline-notice">
          Moodle results are evidence, not official grades. Accepting one asks
          OwnSIS Grading to record or revise the official result under its own
          permission, term-closure, and explanation rules.
        </p>
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
        {!canReview ? (
          <p className="inline-notice">
            Your current membership cannot accept or reject grade evidence.
          </p>
        ) : !csrfAvailable ? (
          <p className="inline-notice">
            Decisions are unavailable because the session has no CSRF token.
          </p>
        ) : null}
        {canReview && gradingScales.length === 0 ? (
          <p className="inline-notice">
            No official grading scale is configured, so evidence cannot be
            accepted yet.
          </p>
        ) : null}
        {pending.length === 0 ? (
          <EmptyState message="No Moodle grade evidence is awaiting a decision." />
        ) : (
          <div className="resource-grid">
            {pending.map((item) => (
              <article className="resource-card" key={item.id}>
                <div className="resource-card-heading">
                  <div>
                    <h3>Evidence {shortReference(item.id)}</h3>
                    <p>
                      Offering {shortReference(item.courseOfferingId)} · person{" "}
                      {shortReference(item.studentPersonId)}
                    </p>
                  </div>
                  <span className="status-pill">{item.gradeValue}</span>
                </div>
                <dl className="resource-metadata">
                  <div>
                    <dt>Observed</dt>
                    <dd>{formatInstant(item.observedAt)}</dd>
                  </div>
                  <div>
                    <dt>Received</dt>
                    <dd>{formatInstant(item.receivedAt)}</dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>{item.sourceVersion}</dd>
                  </div>
                  <div>
                    <dt>External event</dt>
                    <dd>{item.externalEventId}</dd>
                  </div>
                </dl>
                <form
                  className="form-grid"
                  onSubmit={(event) => void accept(event, item)}
                >
                  <label>
                    Grading scale for {shortReference(item.id)}
                    <select name="gradingScaleId" required defaultValue="">
                      <ResourceOptions
                        placeholder="Select an official scale"
                        resources={gradingScales}
                      />
                    </select>
                  </label>
                  <label className="form-span">
                    Explanation for {shortReference(item.id)}
                    <input name="explanation" maxLength={2000} />
                    <small>
                      Required when an official grade already exists or the term
                      is closed.
                    </small>
                  </label>
                  <div className="form-actions">
                    <button
                      className="button button-small"
                      type="submit"
                      disabled={
                        !canReview ||
                        !csrfAvailable ||
                        gradingScales.length === 0 ||
                        pendingEvidenceId === item.id
                      }
                    >
                      {pendingEvidenceId === item.id
                        ? "Working…"
                        : "Accept as official grade"}
                    </button>
                  </div>
                </form>
                <form
                  className="form-grid"
                  onSubmit={(event) => void reject(event, item)}
                >
                  <label className="form-span">
                    Rejection reason for {shortReference(item.id)}
                    <input name="reason" maxLength={2000} />
                  </label>
                  <div className="form-actions">
                    <button
                      className="button button-secondary button-small"
                      type="submit"
                      disabled={
                        !canReview ||
                        !csrfAvailable ||
                        pendingEvidenceId === item.id
                      }
                    >
                      Reject evidence
                    </button>
                  </div>
                </form>
              </article>
            ))}
          </div>
        )}
      </section>
      {resolved.length > 0 ? (
        <section aria-labelledby="resolved-evidence-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Decision history</p>
              <h2 id="resolved-evidence-heading">Resolved evidence</h2>
            </div>
          </div>
          <div className="resource-grid">
            {resolved.map((item) => (
              <article className="resource-card" key={item.id}>
                <div className="resource-card-heading">
                  <div>
                    <h3>Evidence {shortReference(item.id)}</h3>
                    <p>
                      Offering {shortReference(item.courseOfferingId)} · grade{" "}
                      {item.gradeValue}
                    </p>
                  </div>
                  <span className="status-pill">{item.status}</span>
                </div>
                <dl className="resource-metadata">
                  {item.reasonCode ? (
                    <div>
                      <dt>Reason code</dt>
                      <dd>{item.reasonCode}</dd>
                    </div>
                  ) : null}
                  {item.acceptedFinalGradeId ? (
                    <div>
                      <dt>Official grade</dt>
                      <dd>{shortReference(item.acceptedFinalGradeId)}</dd>
                    </div>
                  ) : null}
                  {item.resolvedAt ? (
                    <div>
                      <dt>Resolved</dt>
                      <dd>{formatInstant(item.resolvedAt)}</dd>
                    </div>
                  ) : null}
                </dl>
              </article>
            ))}
          </div>
        </section>
      ) : null}
      <form className="form-card" onSubmit={(event) => void reconcile(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Selected-term reconciliation</p>
            <h2>Observe Moodle course totals</h2>
          </div>
        </div>
        <p className="inline-notice">
          Reconciliation reads course totals for the mapped offerings of one
          term and stores them as pending evidence. Unmapped offerings and
          learners are counted, never guessed.
        </p>
        <div className="form-grid">
          <label>
            Term
            <select name="termId" required defaultValue="">
              <ResourceOptions placeholder="Select a term" resources={terms} />
            </select>
          </label>
        </div>
        {runError ? (
          <p className="inline-alert" role="alert">
            {runError}
          </p>
        ) : null}
        {runMessage ? (
          <p className="inline-success" role="status">
            {runMessage}
          </p>
        ) : null}
        {!canReconcile ? (
          <p className="inline-notice">
            Your current membership cannot run Moodle grade reconciliation.
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canReconcile ||
              !csrfAvailable ||
              reconciling ||
              terms.length === 0
            }
          >
            {reconciling ? "Reconciling…" : "Reconcile term grades"}
          </button>
        </div>
      </form>
      {runs.length > 0 ? (
        <section aria-labelledby="reconciliation-runs-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Operational evidence</p>
              <h2 id="reconciliation-runs-heading">Reconciliation runs</h2>
            </div>
          </div>
          <div className="resource-grid">
            {runs.map((run) => (
              <RunSummary key={run.id} run={run} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
