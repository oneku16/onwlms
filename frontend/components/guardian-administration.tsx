"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceList } from "@/components/resource-list";
import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseGuardianRelationship,
  type GuardianRelationshipView,
} from "@/lib/api/people";
import {
  resourceTitle,
  type ResourceCollection,
  type ResourceSummary,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { textValue } from "@/lib/forms";

export function GuardianAdministration({
  canManage,
  initialGuardians,
  organizationId,
  students,
}: {
  readonly canManage: boolean;
  readonly initialGuardians: ResourceCollection;
  readonly organizationId: string;
  readonly students: readonly ResourceSummary[];
}) {
  const [relationships, setRelationships] = useState<
    readonly GuardianRelationshipView[]
  >([]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();
  const guardians = initialGuardians.items;

  function describeRelationship(
    relationship: GuardianRelationshipView,
  ): string {
    return `${resourceTitle(guardians, relationship.guardianProfileId, "Guardian")} → ${resourceTitle(students, relationship.studentProfileId, "Student")}`;
  }

  async function linkGuardian(
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
        "/api/v1/guardian-relationships",
        parseGuardianRelationship,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            guardian_profile_id: textValue(form.get("guardianProfileId")),
            student_profile_id: textValue(form.get("studentProfileId")),
            relationship_label: textValue(form.get("relationshipLabel")),
          },
        },
      );
      setRelationships((current) => [...current, created]);
      setMessage(
        `${describeRelationship(created)} was linked as “${created.relationshipLabel}”.`,
      );
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The guardian relationship could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {guardians.length > 0 ? (
        <ResourceList collection={initialGuardians} />
      ) : (
        <EmptyState message="No guardians are available." />
      )}
      <form
        className="form-card"
        onSubmit={(event) => void linkGuardian(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Authorized access</p>
            <h2>Link a guardian to a student</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Guardian profile
            <select name="guardianProfileId" required defaultValue="">
              <ResourceOptions
                includeIdentifier
                placeholder="Select a guardian profile"
                resources={guardians}
              />
            </select>
          </label>
          <label>
            Student profile
            <select name="studentProfileId" required defaultValue="">
              <ResourceOptions
                includeIdentifier
                placeholder="Select a student profile"
                resources={students}
              />
            </select>
          </label>
          <label className="form-span">
            Relationship label
            <input name="relationshipLabel" required maxLength={80} />
            <small>For example mother, father, or legal guardian.</small>
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage guardian relationships."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canManage ||
              !csrfAvailable ||
              submitting ||
              guardians.length === 0 ||
              students.length === 0
            }
          >
            {submitting ? "Linking…" : "Link guardian"}
          </button>
        </div>
      </form>
      {relationships.length > 0 ? (
        <section aria-labelledby="guardian-links-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Created in this session</p>
              <h2 id="guardian-links-heading">Guardian relationships</h2>
            </div>
          </div>
          <div className="resource-grid">
            {relationships.map((relationship) => (
              <article className="resource-card" key={relationship.id}>
                <div className="resource-card-heading">
                  <div>
                    <h2>{describeRelationship(relationship)}</h2>
                  </div>
                  <span className="status-pill">
                    {relationship.relationshipLabel}
                  </span>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
