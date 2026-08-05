"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseNoContent,
  parseTeacherAvailabilityWindow,
  type TeacherAvailabilityWindow,
} from "@/lib/api/availability";
import type { ResourceCollection } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";

function asUtc(value: FormDataEntryValue | null): string {
  return `${String(value ?? "").trim()}:00Z`;
}

export function TeacherAvailabilityPanel({
  canEdit,
  initialWindows,
  organizationId,
  teachers,
  timezone,
}: {
  readonly canEdit: boolean;
  readonly initialWindows: readonly TeacherAvailabilityWindow[];
  readonly organizationId: string;
  readonly teachers: ResourceCollection;
  readonly timezone: string;
}) {
  const [windows, setWindows] = useState(initialWindows);
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();
  const editable = canEdit && csrfAvailable && pending === null;
  const teacherNames = new Map(
    teachers.items.map((teacher) => [teacher.id, teacher.title]),
  );
  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    timeZone: timezone,
    dateStyle: "medium",
    timeStyle: "short",
  });

  async function createWindow(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setPending("create");
    setMessage(null);
    setError(null);
    try {
      const created = await clientApiRequest(
        "/api/v1/scheduling/teacher-availability",
        parseTeacherAvailabilityWindow,
        {
          method: "POST",
          organizationId,
          body: {
            teacher_id: String(form.get("teacherId") ?? ""),
            starts_at: asUtc(form.get("startsAt")),
            ends_at: asUtc(form.get("endsAt")),
          },
        },
      );
      setWindows((current) =>
        [...current, created].sort((left, right) =>
          left.startsAt.localeCompare(right.startsAt),
        ),
      );
      setMessage("Teacher availability saved.");
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Teacher availability could not be saved.",
      );
    } finally {
      setPending(null);
    }
  }

  async function deleteWindow(
    window: TeacherAvailabilityWindow,
  ): Promise<void> {
    setPending(window.id);
    setMessage(null);
    setError(null);
    try {
      await clientApiRequest(
        `/api/v1/scheduling/teacher-availability/${encodeURIComponent(window.id)}`,
        parseNoContent,
        { method: "DELETE", organizationId },
      );
      setWindows((current) =>
        current.filter((candidate) => candidate.id !== window.id),
      );
      setMessage("Teacher availability removed.");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Teacher availability could not be removed.",
      );
    } finally {
      setPending(null);
    }
  }

  return (
    <details className="form-card availability-panel">
      <summary>Teacher availability</summary>
      <p>
        Configure authoritative UTC windows before placing or generating
        teacher-attached sessions. Times below are displayed in {timezone}.
      </p>
      {windows.length > 0 ? (
        <ul className="availability-list">
          {windows.map((window) => (
            <li key={window.id}>
              <span>
                <strong>
                  {teacherNames.get(window.teacherId) ??
                    `Teacher ${window.teacherId}`}
                </strong>
                <small>
                  {dateFormatter.format(new Date(window.startsAt))} –{" "}
                  {dateFormatter.format(new Date(window.endsAt))}
                </small>
              </span>
              {canEdit ? (
                <button
                  className="button button-secondary button-small"
                  type="button"
                  disabled={!editable}
                  onClick={() => void deleteWindow(window)}
                >
                  {pending === window.id ? "Removing…" : "Remove"}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="inline-notice">
          No availability windows exist in this scheduling horizon.
        </p>
      )}
      <form onSubmit={(event) => void createWindow(event)}>
        <div className="form-grid">
          <label className="form-span">
            Teacher profile
            <select name="teacherId" required defaultValue="">
              <option value="" disabled>
                Select a tenant teacher
              </option>
              {teachers.items.map((teacher) => (
                <option key={teacher.id} value={teacher.id}>
                  {teacher.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Starts at (UTC)
            <input name="startsAt" type="datetime-local" required />
          </label>
          <label>
            Ends at (UTC)
            <input name="endsAt" type="datetime-local" required />
          </label>
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
        {!canEdit ? (
          <p className="inline-notice">
            Your permissions allow availability viewing but not editing.
          </p>
        ) : !csrfAvailable ? (
          <p className="inline-notice">
            Editing is unavailable because the session has no CSRF token.
          </p>
        ) : null}
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={!editable || teachers.items.length === 0}
          >
            {pending === "create" ? "Saving…" : "Add availability"}
          </button>
        </div>
      </form>
    </details>
  );
}
