"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { programEducationModeLabels } from "@/components/program-administration";
import { ResourceOptions } from "@/components/resource-options";
import {
  parseSelectionPolicy,
  programEducationModes,
  type SelectionPolicyView,
} from "@/lib/api/academics";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { resourceTitle, type ResourceSummary } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import {
  dateTimeInputFromIso,
  decimalValue,
  isoFromDateTimeInput,
  textValue,
} from "@/lib/forms";

interface PolicySelection {
  readonly programId: string;
  readonly termId: string;
  /** Null when the backend reported no policy for the pair yet. */
  readonly policy: SelectionPolicyView | null;
  /** Increments per load so the editor remounts with fresh defaults. */
  readonly revision: number;
}

export function SelectionPolicyAdministration({
  canManage,
  organizationId,
  programs,
  terms,
}: {
  readonly canManage: boolean;
  readonly organizationId: string;
  readonly programs: readonly ResourceSummary[];
  readonly terms: readonly ResourceSummary[];
}) {
  const [selection, setSelection] = useState<PolicySelection | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  function policyPath(programId: string, termId: string): string {
    return `/api/v1/academics/course-selection-policies/${encodeURIComponent(programId)}/${encodeURIComponent(termId)}`;
  }

  async function loadPolicy(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const programId = textValue(form.get("programId"));
    const termId = textValue(form.get("termId"));
    const revision = (selection?.revision ?? 0) + 1;
    setLoading(true);
    setLoadError(null);
    setMessage(null);
    setError(null);
    setSelection(null);
    try {
      const policy = await clientApiRequest(
        policyPath(programId, termId),
        parseSelectionPolicy,
        { organizationId },
      );
      setSelection({ programId, termId, policy, revision });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        setSelection({ programId, termId, policy: null, revision });
      } else {
        setLoadError(
          caught instanceof ApiError
            ? caught.message
            : "The course-selection policy could not be loaded.",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  async function savePolicy(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!selection) {
      return;
    }
    const form = new FormData(event.currentTarget);
    setMessage(null);
    setError(null);
    const deadline = isoFromDateTimeInput(form.get("deadline"));
    const maximumCredits = decimalValue(form.get("maximumCredits"));
    if (!deadline || !maximumCredits) {
      setError("Enter a valid deadline and a decimal credit maximum.");
      return;
    }
    setSaving(true);
    try {
      const saved = await clientApiRequest(
        policyPath(selection.programId, selection.termId),
        parseSelectionPolicy,
        {
          method: "PUT",
          organizationId,
          body: {
            approval_required: form.get("approvalRequired") === "on",
            deadline,
            education_mode: textValue(form.get("educationMode")),
            maximum_credits: maximumCredits,
          },
        },
      );
      setSelection((current) =>
        current ? { ...current, policy: saved } : current,
      );
      setMessage("Course-selection policy saved.");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The course-selection policy could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="notification-layout">
      <form className="form-card" onSubmit={(event) => void loadPolicy(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Course selection</p>
            <h2>Choose a program and term</h2>
          </div>
        </div>
        <div className="form-grid">
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
            Term
            <select name="termId" required defaultValue="">
              <ResourceOptions placeholder="Select a term" resources={terms} />
            </select>
          </label>
        </div>
        {loadError ? (
          <p className="inline-alert" role="alert">
            {loadError}
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={loading || programs.length === 0 || terms.length === 0}
          >
            {loading ? "Loading policy…" : "Load policy"}
          </button>
        </div>
      </form>
      {selection ? (
        <form
          className="form-card"
          key={`${selection.programId}:${selection.termId}:${selection.revision}`}
          onSubmit={(event) => void savePolicy(event)}
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">
                {resourceTitle(programs, selection.programId, "Program")} ·{" "}
                {resourceTitle(terms, selection.termId, "Term")}
              </p>
              <h2>
                {selection.policy
                  ? "Edit the course-selection policy"
                  : "Configure the course-selection policy"}
              </h2>
            </div>
            <span className="status-pill">
              {selection.policy ? "configured" : "not configured"}
            </span>
          </div>
          {!selection.policy ? (
            <p className="inline-notice">
              No course-selection policy exists for this program and term.
              Saving creates it.
            </p>
          ) : null}
          <div className="form-grid">
            <label>
              Selection deadline
              <input
                name="deadline"
                type="datetime-local"
                required
                defaultValue={
                  selection.policy
                    ? dateTimeInputFromIso(selection.policy.deadline)
                    : ""
                }
              />
              <small>
                Entered in your browser timezone and stored as a UTC instant.
              </small>
            </label>
            <label>
              Maximum credits
              <input
                name="maximumCredits"
                required
                inputMode="decimal"
                pattern="\d+(\.\d+)?"
                maxLength={12}
                defaultValue={selection.policy?.maximumCredits ?? ""}
              />
            </label>
            <label>
              Education mode
              <select
                name="educationMode"
                required
                defaultValue={selection.policy?.educationMode ?? ""}
              >
                <option value="" disabled>
                  Select an education mode
                </option>
                {programEducationModes.map((mode) => (
                  <option key={mode} value={mode}>
                    {programEducationModeLabels[mode]}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-label">
              <input
                name="approvalRequired"
                type="checkbox"
                defaultChecked={selection.policy?.approvalRequired ?? false}
              />
              Approval is required before enrollment
            </label>
          </div>
          <FormFeedback
            canMutate={canManage}
            csrfAvailable={csrfAvailable}
            error={error}
            message={message}
            permissionNotice="Your current membership cannot manage course-selection policies."
          />
          <div className="form-actions">
            <button
              className="button"
              type="submit"
              disabled={!canManage || !csrfAvailable || saving}
            >
              {saving ? "Saving…" : "Save policy"}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
