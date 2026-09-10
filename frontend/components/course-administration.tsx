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
  appendResource,
  parseCreatedResource,
  type ResourceCollection,
  type ResourceSummary,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { decimalValue, textValue } from "@/lib/forms";

export function CourseAdministration({
  canManage,
  departments,
  initialCourses,
  organizationId,
}: {
  readonly canManage: boolean;
  readonly departments: readonly ResourceSummary[];
  readonly initialCourses: ResourceCollection;
  readonly organizationId: string;
}) {
  const [courses, setCourses] = useState(initialCourses);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function createCourse(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setMessage(null);
    setError(null);
    const credits = decimalValue(form.get("credits"));
    if (!credits) {
      setError("Enter credits as a positive decimal number.");
      return;
    }
    setSubmitting(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/academics/courses",
        parseCreatedResource,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            department_id: textValue(form.get("departmentId")),
            code: textValue(form.get("code")),
            title: textValue(form.get("title")),
            credits,
          },
        },
      );
      setCourses((current) => appendResource(current, created));
      setMessage(`Course “${created.title}” was created.`);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The course could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {courses.items.length > 0 ? (
        <ResourceList collection={courses} />
      ) : (
        <EmptyState message="No courses are available." />
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createCourse(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Course catalog</p>
            <h2>Create a course</h2>
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
            Course code
            <input name="code" required maxLength={64} spellCheck={false} />
          </label>
          <label>
            Course title
            <input name="title" required maxLength={255} />
          </label>
          <label>
            Credits
            <input
              name="credits"
              required
              inputMode="decimal"
              pattern="\d+(\.\d+)?"
              maxLength={12}
            />
            <small>
              Sent as a decimal string so the backend keeps precision.
            </small>
          </label>
        </div>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage the course catalog."
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
            {submitting ? "Creating…" : "Create course"}
          </button>
        </div>
      </form>
    </div>
  );
}
