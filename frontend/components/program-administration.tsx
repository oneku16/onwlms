"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceList } from "@/components/resource-list";
import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import {
  programEducationModes,
  type ProgramEducationMode,
} from "@/lib/api/academics";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  appendResource,
  parseCreatedResource,
  type ResourceCollection,
  type ResourceSummary,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { textValue } from "@/lib/forms";

export const programEducationModeLabels: Readonly<
  Record<ProgramEducationMode, string>
> = {
  fixed_curriculum: "Fixed curriculum",
  flexible_selection: "Flexible selection",
  hybrid: "Hybrid",
};

export function ProgramAdministration({
  canManage,
  departments,
  initialPrograms,
  organizationId,
}: {
  readonly canManage: boolean;
  readonly departments: readonly ResourceSummary[];
  readonly initialPrograms: ResourceCollection;
  readonly organizationId: string;
}) {
  const [programs, setPrograms] = useState(initialPrograms);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createProgram(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const created = await clientApiRequest(
        "/api/v1/academics/programs",
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            department_id: textValue(form.get("departmentId")),
            code: textValue(form.get("code")),
            name: textValue(form.get("name")),
            education_mode: textValue(form.get("educationMode")),
            credit_unit_label: textValue(form.get("creditUnitLabel")),
          },
        },
      );
      setPrograms((current) => appendResource(current, created));
      setMessage(`Program “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The program could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {programs.items.length > 0 ? (
        <ResourceList collection={programs} />
      ) : (
        <EmptyState message="No programs are available." />
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createProgram(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Academic structure</p>
            <h2>Create a program</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Department
            <select name="departmentId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a department"
                resources={departments}
              />
            </select>
          </label>
          <label>
            Program code
            <input name="code" required maxLength={64} spellCheck={false} />
          </label>
          <label>
            Program name
            <input name="name" required maxLength={255} />
          </label>
          <label>
            Education mode
            <select name="educationMode" required defaultValue="">
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
          <label>
            Credit unit label
            <input
              name="creditUnitLabel"
              required
              maxLength={64}
              defaultValue="credits"
            />
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage the academic structure."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canManage ||
              !csrfAvailable ||
              submitting ||
              departments.length === 0
            }
          >
            {submitting ? "Creating…" : "Create program"}
          </button>
        </div>
      </form>
    </div>
  );
}
