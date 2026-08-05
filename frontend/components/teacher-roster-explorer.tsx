"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { ResourceList } from "@/components/resource-list";
import { EmptyState } from "@/components/states";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseResourceCollection,
  type ResourceCollection,
} from "@/lib/api/resources";

export function TeacherRosterExplorer({
  initialSections,
  organizationId,
}: {
  readonly initialSections: ResourceCollection;
  readonly organizationId: string;
}) {
  const [roster, setRoster] = useState<ResourceCollection | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadRoster(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const sectionId = String(form.get("sectionId") ?? "").trim();
    if (!sectionId) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setRoster(
        await clientApiRequest(
          `/api/v1/self-service/teacher/assigned-sections/${encodeURIComponent(sectionId)}/students`,
          parseResourceCollection,
          { organizationId },
        ),
      );
    } catch (caught) {
      setRoster(null);
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The assigned-section roster could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }

  if (initialSections.items.length === 0) {
    return <EmptyState message="No sections are assigned to you." />;
  }

  return (
    <div className="notification-layout">
      <form className="form-card" onSubmit={(event) => void loadRoster(event)}>
        <div className="form-grid">
          <label className="form-span">
            Assigned section
            <select name="sectionId" required defaultValue="">
              <option value="" disabled>
                Select an assigned section
              </option>
              {initialSections.items.map((section) => (
                <option key={section.id} value={section.id}>
                  {section.title}
                  {section.subtitle ? ` — ${section.subtitle}` : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
        {error ? (
          <p className="inline-alert" role="alert">
            {error}
          </p>
        ) : null}
        <div className="form-actions">
          <button className="button" type="submit" disabled={loading}>
            {loading ? "Loading roster…" : "View student list"}
          </button>
        </div>
      </form>
      {roster ? (
        roster.items.length === 0 ? (
          <EmptyState message="This assigned section has no active students." />
        ) : (
          <ResourceList collection={roster} />
        )
      ) : null}
    </div>
  );
}
