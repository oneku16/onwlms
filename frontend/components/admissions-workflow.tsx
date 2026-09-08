"use client";

import type { FormEvent } from "react";
import { useRef, useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import {
  applicationSources,
  applicationStatuses,
  decisionOutcomes,
  parseApplication,
  parseApplicationDocument,
  parseApplicationDocuments,
  parseApplications,
  parseDecision,
  parseEnrollmentConversion,
  parseReview,
  parseReviews,
  reviewOutcomes,
  reviewStages,
  type ApplicationDocumentView,
  type ApplicationView,
  type ReviewView,
} from "@/lib/api/admissions";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { resourceTitle, type ResourceSummary } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import {
  optionalTextValue,
  positiveIntegerValue,
  textValue,
} from "@/lib/forms";

type PendingAction =
  | "filter"
  | "create"
  | "submit"
  | "review"
  | "document"
  | "decision"
  | "enrollment";

const checksumPattern = /^[0-9a-fA-F]{64}$/;

function applicationLabel(application: ApplicationView): string {
  return `Application ${application.id.slice(0, 8)}`;
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

function applicationPath(applicationId: string, suffix = ""): string {
  return `/api/v1/admissions/applications/${encodeURIComponent(applicationId)}${suffix}`;
}

export function AdmissionsWorkflow({
  canCreate,
  canDecide,
  canEnroll,
  canManageDocuments,
  canReview,
  canSubmit,
  initialApplications,
  organizationId,
  programs,
  terms,
}: {
  readonly canCreate: boolean;
  readonly canDecide: boolean;
  readonly canEnroll: boolean;
  readonly canManageDocuments: boolean;
  readonly canReview: boolean;
  readonly canSubmit: boolean;
  readonly initialApplications: readonly ApplicationView[];
  readonly organizationId: string;
  readonly programs: readonly ResourceSummary[];
  readonly terms: readonly ResourceSummary[];
}) {
  const [applications, setApplications] = useState(initialApplications);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reviews, setReviews] = useState<readonly ReviewView[]>([]);
  const [documents, setDocuments] = useState<
    readonly ApplicationDocumentView[]
  >([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [createMessage, setCreateMessage] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selectionSequence = useRef(0);
  const csrfAvailable = useCsrfProtection();
  const selected =
    applications.find((candidate) => candidate.id === selectedId) ?? null;
  const busy = pending !== null;

  function replaceApplication(updated: ApplicationView): void {
    setApplications((current) =>
      current.map((candidate) =>
        candidate.id === updated.id ? updated : candidate,
      ),
    );
  }

  /**
   * Re-read the application after a lifecycle action so the displayed status
   * comes from the backend. A refresh failure is reported explicitly rather
   * than being mistaken for a failure of the action that already succeeded.
   */
  async function refreshApplication(applicationId: string): Promise<string> {
    try {
      replaceApplication(
        await clientApiRequest(
          applicationPath(applicationId),
          parseApplication,
          { organizationId },
        ),
      );
      return "";
    } catch {
      return " The displayed status could not be refreshed; reload the page to see the latest state.";
    }
  }

  async function applyFilter(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const status = textValue(new FormData(event.currentTarget).get("status"));
    const query = new URLSearchParams({ limit: "100" });
    if (status) {
      query.set("application_status", status);
    }
    setPending("filter");
    setListError(null);
    try {
      const loaded = await clientApiRequest(
        `/api/v1/admissions/applications?${query.toString()}`,
        parseApplications,
        { organizationId },
      );
      setApplications(loaded);
      setSelectedId(null);
      setReviews([]);
      setDocuments([]);
    } catch (caught) {
      setListError(
        caught instanceof ApiError
          ? caught.message
          : "Admissions applications could not be loaded.",
      );
    } finally {
      setPending(null);
    }
  }

  async function createApplication(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setPending("create");
    setCreateMessage(null);
    setCreateError(null);
    try {
      const created = await clientApiRequest(
        "/api/v1/admissions/applications",
        parseApplication,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            given_name: textValue(form.get("givenName")),
            family_name: textValue(form.get("familyName")),
            email: optionalTextValue(form.get("email")),
            phone: optionalTextValue(form.get("phone")),
            program_id: textValue(form.get("programId")),
            intake_id: textValue(form.get("intakeId")),
            seat_category: textValue(form.get("seatCategory")),
            source: textValue(form.get("source")),
          },
        },
      );
      setApplications((current) => [created, ...current]);
      setCreateMessage(
        `${applicationLabel(created)} was created with status ${created.status}. Applicant contact details are not shown again.`,
      );
      formElement.reset();
    } catch (caught) {
      setCreateError(
        caught instanceof ApiError
          ? caught.message
          : "The admissions application could not be created.",
      );
    } finally {
      setPending(null);
    }
  }

  async function selectApplication(
    application: ApplicationView,
  ): Promise<void> {
    const sequence = ++selectionSequence.current;
    setSelectedId(application.id);
    setReviews([]);
    setDocuments([]);
    setMessage(null);
    setError(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const [loadedReviews, loadedDocuments] = await Promise.all([
        canReview
          ? clientApiRequest(
              applicationPath(application.id, "/reviews?limit=100"),
              parseReviews,
              { organizationId },
            )
          : Promise.resolve<readonly ReviewView[]>([]),
        canManageDocuments
          ? clientApiRequest(
              applicationPath(application.id, "/documents?limit=100"),
              parseApplicationDocuments,
              { organizationId },
            )
          : Promise.resolve<readonly ApplicationDocumentView[]>([]),
      ]);
      if (selectionSequence.current === sequence) {
        setReviews(loadedReviews);
        setDocuments(loadedDocuments);
      }
    } catch (caught) {
      if (selectionSequence.current === sequence) {
        setDetailError(
          caught instanceof ApiError
            ? caught.message
            : "The application history could not be loaded.",
        );
      }
    } finally {
      if (selectionSequence.current === sequence) {
        setDetailLoading(false);
      }
    }
  }

  async function runAction(
    action: PendingAction,
    perform: () => Promise<string>,
    failure: string,
  ): Promise<void> {
    setPending(action);
    setMessage(null);
    setError(null);
    try {
      setMessage(await perform());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : failure);
    } finally {
      setPending(null);
    }
  }

  function submitApplication(application: ApplicationView): void {
    void runAction(
      "submit",
      async () => {
        const submitted = await clientApiRequest(
          applicationPath(application.id, "/submit"),
          parseApplication,
          { method: "POST", organizationId },
        );
        replaceApplication(submitted);
        return `${applicationLabel(submitted)} was submitted and is now ${submitted.status}.`;
      },
      "The application could not be submitted.",
    );
  }

  function enrollApplication(application: ApplicationView): void {
    void runAction(
      "enrollment",
      async () => {
        const conversion = await clientApiRequest(
          applicationPath(application.id, "/enrollment"),
          parseEnrollmentConversion,
          {
            method: "POST",
            organizationId,
            idempotencyKey: crypto.randomUUID(),
          },
        );
        const refreshNotice = await refreshApplication(application.id);
        return `${applicationLabel(application)} was converted: student ${conversion.studentId.slice(0, 8)}, academic enrollment ${conversion.academicEnrollmentId.slice(0, 8)}.${refreshNotice}`;
      },
      "The accepted application could not be enrolled.",
    );
  }

  function recordReview(
    event: FormEvent<HTMLFormElement>,
    application: ApplicationView,
  ): void {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    void runAction(
      "review",
      async () => {
        const review = await clientApiRequest(
          applicationPath(application.id, "/reviews"),
          parseReview,
          {
            method: "POST",
            organizationId,
            idempotencyKey: crypto.randomUUID(),
            body: {
              stage: textValue(form.get("stage")),
              outcome: textValue(form.get("outcome")),
              explanation: optionalTextValue(form.get("explanation")),
            },
          },
        );
        setReviews((current) => [...current, review]);
        const refreshNotice = await refreshApplication(application.id);
        formElement.reset();
        return `Recorded the ${review.stage} review as ${review.outcome}.${refreshNotice}`;
      },
      "The review could not be recorded.",
    );
  }

  function addDocument(
    event: FormEvent<HTMLFormElement>,
    application: ApplicationView,
  ): void {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const sizeBytes = positiveIntegerValue(form.get("sizeBytes"));
    const checksum = textValue(form.get("checksum"));
    if (sizeBytes === null || !checksumPattern.test(checksum)) {
      setMessage(null);
      setError(
        "Enter the size in bytes as a positive whole number and a 64-character SHA-256 checksum.",
      );
      return;
    }
    void runAction(
      "document",
      async () => {
        const document = await clientApiRequest(
          applicationPath(application.id, "/documents"),
          parseApplicationDocument,
          {
            method: "POST",
            organizationId,
            idempotencyKey: crypto.randomUUID(),
            body: {
              document_type: textValue(form.get("documentType")),
              file_reference: textValue(form.get("fileReference")),
              media_type: textValue(form.get("mediaType")),
              size_bytes: sizeBytes,
              checksum_sha256: checksum.toLowerCase(),
            },
          },
        );
        setDocuments((current) => [...current, document]);
        formElement.reset();
        return `Recorded ${document.documentType} metadata for ${applicationLabel(application)}.`;
      },
      "The document metadata could not be recorded.",
    );
  }

  function decide(
    event: FormEvent<HTMLFormElement>,
    application: ApplicationView,
  ): void {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    void runAction(
      "decision",
      async () => {
        const decision = await clientApiRequest(
          applicationPath(application.id, "/decisions"),
          parseDecision,
          {
            method: "POST",
            organizationId,
            idempotencyKey: crypto.randomUUID(),
            body: {
              outcome: textValue(form.get("outcome")),
              reason: textValue(form.get("reason")),
            },
          },
        );
        const refreshNotice = await refreshApplication(application.id);
        formElement.reset();
        return `${applicationLabel(application)} was ${decision.outcome}${decision.reservationId ? " with a seat reservation" : ""}.${refreshNotice}`;
      },
      "The decision could not be recorded.",
    );
  }

  const mutationBlocked = !csrfAvailable || busy;

  return (
    <div className="notification-layout">
      <form className="form-card" onSubmit={(event) => void applyFilter(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Application lifecycle</p>
            <h2>Filter applications</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Application status
            <select name="status" defaultValue="">
              <option value="">All statuses</option>
              {applicationStatuses.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>
        </div>
        {listError ? (
          <p className="inline-alert" role="alert">
            {listError}
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button button-secondary"
            type="submit"
            disabled={busy}
          >
            {pending === "filter" ? "Loading…" : "Apply filter"}
          </button>
        </div>
      </form>

      <form
        className="form-card"
        onSubmit={(event) => void createApplication(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Intake</p>
            <h2>Create an application</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Given name
            <input name="givenName" required maxLength={128} />
          </label>
          <label>
            Family name
            <input name="familyName" required maxLength={128} />
          </label>
          <label>
            Email (optional)
            <input
              name="email"
              type="email"
              maxLength={320}
              autoComplete="off"
            />
          </label>
          <label>
            Phone (optional)
            <input name="phone" type="tel" maxLength={64} autoComplete="off" />
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
            Intake term
            <select name="intakeId" required defaultValue="">
              <ResourceOptions
                placeholder="Select an intake term"
                resources={terms}
              />
            </select>
          </label>
          <label>
            Seat category
            <input name="seatCategory" required maxLength={64} />
          </label>
          <label>
            Source
            <select name="source" required defaultValue="administrator_entered">
              {applicationSources.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </select>
          </label>
        </div>
        <FormFeedback
          canMutate={canCreate}
          csrfAvailable={csrfAvailable}
          error={createError}
          message={createMessage}
          permissionNotice="Your current membership cannot create applications."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canCreate ||
              mutationBlocked ||
              programs.length === 0 ||
              terms.length === 0
            }
          >
            {pending === "create" ? "Creating…" : "Create application"}
          </button>
        </div>
      </form>

      {applications.length === 0 ? (
        <EmptyState message="No admissions applications match the current filter." />
      ) : (
        <section aria-labelledby="applications-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current records</p>
              <h2 id="applications-heading">
                {applications.length.toLocaleString()} application
                {applications.length === 1 ? "" : "s"}
              </h2>
            </div>
          </div>
          <div className="resource-grid">
            {applications.map((application) => (
              <article className="resource-card" key={application.id}>
                <div className="resource-card-heading">
                  <div>
                    <h2>{applicationLabel(application)}</h2>
                    <p>
                      {resourceTitle(
                        programs,
                        application.programId,
                        "Program",
                      )}{" "}
                      · {resourceTitle(terms, application.intakeId, "Intake")}
                    </p>
                  </div>
                  <span className="status-pill">{application.status}</span>
                </div>
                <dl className="resource-metadata">
                  <div>
                    <dt>Seat category</dt>
                    <dd>{application.seatCategory}</dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>{application.source}</dd>
                  </div>
                  <div>
                    <dt>Deposit</dt>
                    <dd>{application.depositStatus}</dd>
                  </div>
                  <div>
                    <dt>Created</dt>
                    <dd>{formatInstant(application.createdAt)}</dd>
                  </div>
                </dl>
                <div className="button-row">
                  <button
                    className="button button-secondary button-small"
                    type="button"
                    disabled={selectedId === application.id}
                    onClick={() => void selectApplication(application)}
                  >
                    {selectedId === application.id
                      ? "Selected"
                      : `Select ${application.id.slice(0, 8)}`}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {selected ? (
        <section className="form-card" aria-labelledby="selected-application">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Selected application</p>
              <h2 id="selected-application">{applicationLabel(selected)}</h2>
            </div>
            <span className="status-pill">{selected.status}</span>
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
          {!csrfAvailable ? (
            <p className="inline-notice">
              Actions are unavailable because the session has no CSRF token.
            </p>
          ) : null}
          <div className="button-row">
            {selected.status === "draft" ? (
              <button
                className="button button-small"
                type="button"
                disabled={!canSubmit || mutationBlocked}
                onClick={() => submitApplication(selected)}
              >
                {pending === "submit" ? "Submitting…" : "Submit application"}
              </button>
            ) : null}
            {selected.status === "accepted" ? (
              <button
                className="button button-small"
                type="button"
                disabled={!canEnroll || mutationBlocked}
                onClick={() => enrollApplication(selected)}
              >
                {pending === "enrollment"
                  ? "Enrolling…"
                  : "Enroll accepted application"}
              </button>
            ) : null}
          </div>
          {selected.status === "draft" && !canSubmit ? (
            <p className="inline-notice">
              Your current membership cannot submit applications.
            </p>
          ) : null}
          {selected.status === "accepted" && !canEnroll ? (
            <p className="inline-notice">
              Your current membership cannot convert accepted applications.
            </p>
          ) : null}

          <div className="section-heading">
            <div>
              <p className="eyebrow">Immutable history</p>
              <h2>Reviews</h2>
            </div>
          </div>
          {detailError ? (
            <p className="inline-alert" role="alert">
              {detailError}
            </p>
          ) : null}
          {detailLoading ? (
            <p className="inline-notice" role="status">
              Loading application history…
            </p>
          ) : !canReview ? (
            <p className="inline-notice">
              Your current membership cannot read admissions reviews.
            </p>
          ) : reviews.length === 0 ? (
            <p className="inline-notice">No reviews have been recorded.</p>
          ) : (
            <ul className="dashboard-list">
              {reviews.map((review) => (
                <li key={review.id}>
                  <span>
                    <strong>
                      {review.stage} · {review.outcome}
                    </strong>
                    {review.explanation ? (
                      <small>{review.explanation}</small>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <form onSubmit={(event) => recordReview(event, selected)}>
            <div className="form-grid">
              <label>
                Review stage
                <select name="stage" required defaultValue="">
                  <option value="" disabled>
                    Select a stage
                  </option>
                  {reviewStages.map((stage) => (
                    <option key={stage} value={stage}>
                      {stage}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Review outcome
                <select name="outcome" required defaultValue="">
                  <option value="" disabled>
                    Select an outcome
                  </option>
                  {reviewOutcomes.map((outcome) => (
                    <option key={outcome} value={outcome}>
                      {outcome}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-span">
                Review explanation (optional)
                <textarea name="explanation" maxLength={2000} rows={3} />
              </label>
            </div>
            <div className="form-actions">
              <button
                className="button button-secondary button-small"
                type="submit"
                disabled={!canReview || mutationBlocked}
              >
                {pending === "review" ? "Recording…" : "Record review"}
              </button>
            </div>
          </form>

          <div className="section-heading">
            <div>
              <p className="eyebrow">External document store</p>
              <h2>Documents</h2>
            </div>
          </div>
          <p className="inline-notice">
            OwnSIS records document metadata only. The file itself must already
            exist in the external document store referenced below.
          </p>
          {!canManageDocuments ? (
            <p className="inline-notice">
              Your current membership cannot manage application documents.
            </p>
          ) : detailLoading ? null : documents.length === 0 ? (
            <p className="inline-notice">No document metadata is recorded.</p>
          ) : (
            <ul className="dashboard-list">
              {documents.map((document) => (
                <li key={document.id}>
                  <span>
                    <strong>
                      {document.documentType} · {document.mediaType}
                    </strong>
                    <small>
                      {document.fileReference} ·{" "}
                      {document.sizeBytes.toLocaleString()} bytes ·{" "}
                      {formatInstant(document.uploadedAt)}
                    </small>
                  </span>
                </li>
              ))}
            </ul>
          )}
          <form onSubmit={(event) => addDocument(event, selected)}>
            <div className="form-grid">
              <label>
                Document type
                <input name="documentType" required maxLength={128} />
              </label>
              <label>
                Media type
                <input
                  name="mediaType"
                  required
                  maxLength={255}
                  spellCheck={false}
                />
              </label>
              <label className="form-span">
                File reference
                <input
                  name="fileReference"
                  required
                  maxLength={512}
                  spellCheck={false}
                />
              </label>
              <label>
                Size in bytes
                <input
                  name="sizeBytes"
                  type="number"
                  min="1"
                  step="1"
                  required
                />
              </label>
              <label>
                SHA-256 checksum
                <input
                  name="checksum"
                  required
                  minLength={64}
                  maxLength={64}
                  pattern="[0-9a-fA-F]{64}"
                  spellCheck={false}
                />
              </label>
            </div>
            <div className="form-actions">
              <button
                className="button button-secondary button-small"
                type="submit"
                disabled={!canManageDocuments || mutationBlocked}
              >
                {pending === "document"
                  ? "Recording…"
                  : "Record document metadata"}
              </button>
            </div>
          </form>

          <div className="section-heading">
            <div>
              <p className="eyebrow">Official outcome</p>
              <h2>Decision</h2>
            </div>
          </div>
          <form onSubmit={(event) => decide(event, selected)}>
            <div className="form-grid">
              <label>
                Decision outcome
                <select name="outcome" required defaultValue="">
                  <option value="" disabled>
                    Select an outcome
                  </option>
                  {decisionOutcomes.map((outcome) => (
                    <option key={outcome} value={outcome}>
                      {outcome}
                    </option>
                  ))}
                </select>
              </label>
              <label className="form-span">
                Decision reason
                <textarea name="reason" required maxLength={2000} rows={3} />
              </label>
            </div>
            {!canDecide ? (
              <p className="inline-notice">
                Your current membership cannot record admissions decisions.
              </p>
            ) : null}
            <div className="form-actions">
              <button
                className="button button-small"
                type="submit"
                disabled={!canDecide || mutationBlocked}
              >
                {pending === "decision" ? "Recording…" : "Record decision"}
              </button>
            </div>
          </form>
        </section>
      ) : null}
    </div>
  );
}
