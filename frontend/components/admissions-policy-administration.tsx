"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceOptions } from "@/components/resource-options";
import {
  parseAdmissionQuota,
  parseAdmissionsPolicy,
  reviewStages,
  type AdmissionQuotaView,
  type AdmissionsPolicyView,
} from "@/lib/api/admissions";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { resourceTitle, type ResourceSummary } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import {
  decimalValue,
  optionalTextValue,
  positiveIntegerValue,
  textValue,
} from "@/lib/forms";

const minimumReservationSeconds = 60;
const maximumReservationSeconds = 31_536_000;

interface PolicySelection {
  readonly programId: string;
  readonly intakeId: string;
  /** Null when the backend reported no policy for the pair yet. */
  readonly policy: AdmissionsPolicyView | null;
  readonly revision: number;
}

interface QuotaSelection {
  readonly programId: string;
  readonly intakeId: string;
  readonly seatCategory: string;
  /** Null when no quota exists; saving then uses a freshly generated identifier. */
  readonly quota: AdmissionQuotaView | null;
  readonly revision: number;
}

export function AdmissionsPolicyAdministration({
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
  const [policySelection, setPolicySelection] =
    useState<PolicySelection | null>(null);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [policySaving, setPolicySaving] = useState(false);
  const [policyLoadError, setPolicyLoadError] = useState<string | null>(null);
  const [policyMessage, setPolicyMessage] = useState<string | null>(null);
  const [policyError, setPolicyError] = useState<string | null>(null);
  const [quotaSelection, setQuotaSelection] = useState<QuotaSelection | null>(
    null,
  );
  const [quotaLoading, setQuotaLoading] = useState(false);
  const [quotaSaving, setQuotaSaving] = useState(false);
  const [quotaLoadError, setQuotaLoadError] = useState<string | null>(null);
  const [quotaMessage, setQuotaMessage] = useState<string | null>(null);
  const [quotaError, setQuotaError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  function policyPath(programId: string, intakeId: string): string {
    return `/api/v1/admissions/policies/${encodeURIComponent(programId)}/${encodeURIComponent(intakeId)}`;
  }

  function describePair(programId: string, intakeId: string): string {
    return `${resourceTitle(programs, programId, "Program")} · ${resourceTitle(terms, intakeId, "Intake")}`;
  }

  async function loadPolicy(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const programId = textValue(form.get("policyProgramId"));
    const intakeId = textValue(form.get("policyIntakeId"));
    const revision = (policySelection?.revision ?? 0) + 1;
    setPolicyLoading(true);
    setPolicyLoadError(null);
    setPolicyMessage(null);
    setPolicyError(null);
    setPolicySelection(null);
    try {
      const policy = await clientApiRequest(
        policyPath(programId, intakeId),
        parseAdmissionsPolicy,
        { organizationId },
      );
      setPolicySelection({ programId, intakeId, policy, revision });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        setPolicySelection({ programId, intakeId, policy: null, revision });
      } else {
        setPolicyLoadError(
          caught instanceof ApiError
            ? caught.message
            : "The admissions policy could not be loaded.",
        );
      }
    } finally {
      setPolicyLoading(false);
    }
  }

  async function savePolicy(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!policySelection) {
      return;
    }
    const form = new FormData(event.currentTarget);
    setPolicyMessage(null);
    setPolicyError(null);
    const reservationSeconds = positiveIntegerValue(
      form.get("reservationDurationSeconds"),
    );
    if (
      reservationSeconds === null ||
      reservationSeconds < minimumReservationSeconds ||
      reservationSeconds > maximumReservationSeconds
    ) {
      setPolicyError(
        `Enter a reservation duration between ${minimumReservationSeconds.toLocaleString()} and ${maximumReservationSeconds.toLocaleString()} seconds.`,
      );
      return;
    }
    const depositAmountText = optionalTextValue(form.get("depositAmount"));
    const depositAmount =
      depositAmountText === null ? null : decimalValue(depositAmountText);
    if (depositAmountText !== null && depositAmount === null) {
      setPolicyError("Enter the deposit amount as a decimal number.");
      return;
    }
    setPolicySaving(true);
    try {
      const saved = await clientApiRequest(
        policyPath(policySelection.programId, policySelection.intakeId),
        parseAdmissionsPolicy,
        {
          method: "PUT",
          organizationId,
          body: {
            required_stages: form.getAll("requiredStages").map(String),
            deposit_required: form.get("depositRequired") === "on",
            deposit_amount: depositAmount,
            deposit_currency: optionalTextValue(form.get("depositCurrency")),
            reservation_duration_seconds: reservationSeconds,
          },
        },
      );
      setPolicySelection((current) =>
        current ? { ...current, policy: saved } : current,
      );
      setPolicyMessage("Admissions policy saved.");
    } catch (caught) {
      setPolicyError(
        caught instanceof ApiError
          ? caught.message
          : "The admissions policy could not be saved.",
      );
    } finally {
      setPolicySaving(false);
    }
  }

  async function loadQuota(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const programId = textValue(form.get("quotaProgramId"));
    const intakeId = textValue(form.get("quotaIntakeId"));
    const seatCategory = textValue(form.get("quotaSeatCategory"));
    const revision = (quotaSelection?.revision ?? 0) + 1;
    setQuotaLoading(true);
    setQuotaLoadError(null);
    setQuotaMessage(null);
    setQuotaError(null);
    setQuotaSelection(null);
    const query = new URLSearchParams({
      program_id: programId,
      intake_id: intakeId,
      seat_category: seatCategory,
    });
    try {
      const quota = await clientApiRequest(
        `/api/v1/admissions/quotas?${query.toString()}`,
        parseAdmissionQuota,
        { organizationId },
      );
      setQuotaSelection({ programId, intakeId, seatCategory, quota, revision });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        setQuotaSelection({
          programId,
          intakeId,
          seatCategory,
          quota: null,
          revision,
        });
      } else {
        setQuotaLoadError(
          caught instanceof ApiError
            ? caught.message
            : "The admission quota could not be loaded.",
        );
      }
    } finally {
      setQuotaLoading(false);
    }
  }

  async function saveQuota(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!quotaSelection) {
      return;
    }
    const form = new FormData(event.currentTarget);
    setQuotaMessage(null);
    setQuotaError(null);
    const capacity = positiveIntegerValue(form.get("capacity"));
    if (capacity === null) {
      setQuotaError("Enter the seat capacity as a positive whole number.");
      return;
    }
    const quotaId = quotaSelection.quota?.id ?? crypto.randomUUID();
    setQuotaSaving(true);
    try {
      const saved = await clientApiRequest(
        `/api/v1/admissions/quotas/${encodeURIComponent(quotaId)}`,
        parseAdmissionQuota,
        {
          method: "PUT",
          organizationId,
          body: {
            program_id: quotaSelection.programId,
            intake_id: quotaSelection.intakeId,
            seat_category: quotaSelection.seatCategory,
            capacity,
          },
        },
      );
      setQuotaSelection((current) =>
        current ? { ...current, quota: saved } : current,
      );
      setQuotaMessage(
        `Admission quota saved with capacity ${saved.capacity.toLocaleString()}.`,
      );
    } catch (caught) {
      setQuotaError(
        caught instanceof ApiError
          ? caught.message
          : "The admission quota could not be saved.",
      );
    } finally {
      setQuotaSaving(false);
    }
  }

  const choicesUnavailable = programs.length === 0 || terms.length === 0;

  return (
    <div className="notification-layout">
      <form className="form-card" onSubmit={(event) => void loadPolicy(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Admissions policy</p>
            <h2>Choose a program and intake</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Policy program
            <select name="policyProgramId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a program"
                resources={programs}
              />
            </select>
          </label>
          <label>
            Policy intake term
            <select name="policyIntakeId" required defaultValue="">
              <ResourceOptions
                placeholder="Select an intake term"
                resources={terms}
              />
            </select>
          </label>
        </div>
        {policyLoadError ? (
          <p className="inline-alert" role="alert">
            {policyLoadError}
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={policyLoading || choicesUnavailable}
          >
            {policyLoading ? "Loading policy…" : "Load admissions policy"}
          </button>
        </div>
      </form>
      {policySelection ? (
        <form
          className="form-card"
          key={`policy:${policySelection.revision}`}
          onSubmit={(event) => void savePolicy(event)}
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">
                {describePair(
                  policySelection.programId,
                  policySelection.intakeId,
                )}
              </p>
              <h2>
                {policySelection.policy
                  ? "Edit the admissions policy"
                  : "Configure the admissions policy"}
              </h2>
            </div>
            <span className="status-pill">
              {policySelection.policy ? "configured" : "not configured"}
            </span>
          </div>
          {!policySelection.policy ? (
            <p className="inline-notice">
              No admissions policy exists for this program and intake. Saving
              creates it.
            </p>
          ) : null}
          <fieldset disabled={policySaving}>
            <legend>Required review stages</legend>
            <div className="checkbox-grid">
              {reviewStages.map((stage) => (
                <label className="checkbox-label" key={stage}>
                  <input
                    name="requiredStages"
                    type="checkbox"
                    value={stage}
                    defaultChecked={
                      policySelection.policy?.requiredStages.includes(stage) ??
                      false
                    }
                  />
                  {stage}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="form-grid">
            <label className="checkbox-label form-span">
              <input
                name="depositRequired"
                type="checkbox"
                defaultChecked={
                  policySelection.policy?.depositRequired ?? false
                }
              />
              A deposit is required to hold a seat
            </label>
            <label>
              Deposit amount (optional)
              <input
                name="depositAmount"
                inputMode="decimal"
                pattern="\d+(\.\d+)?"
                maxLength={16}
                defaultValue={policySelection.policy?.depositAmount ?? ""}
              />
            </label>
            <label>
              Deposit currency (optional)
              <input
                name="depositCurrency"
                maxLength={3}
                autoCapitalize="characters"
                spellCheck={false}
                defaultValue={policySelection.policy?.depositCurrency ?? ""}
              />
            </label>
            <label className="form-span">
              Seat reservation duration in seconds
              <input
                name="reservationDurationSeconds"
                type="number"
                min={minimumReservationSeconds}
                max={maximumReservationSeconds}
                step="1"
                required
                defaultValue={
                  policySelection.policy?.reservationDurationSeconds ?? ""
                }
              />
              <small>
                Between {minimumReservationSeconds.toLocaleString()} seconds and
                one year.
              </small>
            </label>
          </div>
          <FormFeedback
            canMutate={canManage}
            csrfAvailable={csrfAvailable}
            error={policyError}
            message={policyMessage}
            permissionNotice="Your current membership cannot manage admissions policies."
          />
          <div className="form-actions">
            <button
              className="button"
              type="submit"
              disabled={!canManage || !csrfAvailable || policySaving}
            >
              {policySaving ? "Saving…" : "Save admissions policy"}
            </button>
          </div>
        </form>
      ) : null}

      <form className="form-card" onSubmit={(event) => void loadQuota(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Admission quota</p>
            <h2>Choose a program, intake, and seat category</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Quota program
            <select name="quotaProgramId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a program"
                resources={programs}
              />
            </select>
          </label>
          <label>
            Quota intake term
            <select name="quotaIntakeId" required defaultValue="">
              <ResourceOptions
                placeholder="Select an intake term"
                resources={terms}
              />
            </select>
          </label>
          <label className="form-span">
            Quota seat category
            <input name="quotaSeatCategory" required maxLength={64} />
          </label>
        </div>
        {quotaLoadError ? (
          <p className="inline-alert" role="alert">
            {quotaLoadError}
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={quotaLoading || choicesUnavailable}
          >
            {quotaLoading ? "Loading quota…" : "Load admission quota"}
          </button>
        </div>
      </form>
      {quotaSelection ? (
        <form
          className="form-card"
          key={`quota:${quotaSelection.revision}`}
          onSubmit={(event) => void saveQuota(event)}
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">
                {describePair(
                  quotaSelection.programId,
                  quotaSelection.intakeId,
                )}{" "}
                · {quotaSelection.seatCategory}
              </p>
              <h2>
                {quotaSelection.quota
                  ? "Edit the admission quota"
                  : "Configure the admission quota"}
              </h2>
            </div>
            <span className="status-pill">
              {quotaSelection.quota ? "configured" : "not configured"}
            </span>
          </div>
          {!quotaSelection.quota ? (
            <p className="inline-notice">
              No quota exists for this seat category. Saving creates it with a
              new stable identifier.
            </p>
          ) : null}
          <div className="form-grid">
            <label className="form-span">
              Seat capacity
              <input
                name="capacity"
                type="number"
                min="1"
                step="1"
                required
                defaultValue={quotaSelection.quota?.capacity ?? ""}
              />
            </label>
          </div>
          <FormFeedback
            canMutate={canManage}
            csrfAvailable={csrfAvailable}
            error={quotaError}
            message={quotaMessage}
            permissionNotice="Your current membership cannot manage admission quotas."
          />
          <div className="form-actions">
            <button
              className="button"
              type="submit"
              disabled={!canManage || !csrfAvailable || quotaSaving}
            >
              {quotaSaving ? "Saving…" : "Save admission quota"}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
