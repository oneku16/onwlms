"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceOptions } from "@/components/resource-options";
import { EmptyState } from "@/components/states";
import {
  parseCourseOffering,
  type CourseOfferingView,
  type MeetingWindowView,
} from "@/lib/api/academics";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { resourceTitle, type ResourceSummary } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { positiveIntegerValue, textValue, timeValue } from "@/lib/forms";

/** ISO weekday labels: the backend contract numbers Monday as 1 and Sunday as 7. */
export const isoWeekdayNames = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

const maximumMeetingWindows = 7;

export function offeringLabel(
  offering: CourseOfferingView,
  courses: readonly ResourceSummary[],
  terms: readonly ResourceSummary[],
): string {
  return `${resourceTitle(courses, offering.courseId, "Course")} · ${resourceTitle(terms, offering.termId, "Term")} · Section ${offering.sectionCode}`;
}

function describeWindow(window: MeetingWindowView): string {
  return `${isoWeekdayNames[window.weekday - 1] ?? `Weekday ${window.weekday}`} ${window.startsAt}–${window.endsAt}`;
}

export function CourseOfferingAdministration({
  campuses,
  canManage,
  courses,
  initialOfferings,
  organizationId,
  terms,
}: {
  readonly campuses: readonly ResourceSummary[];
  readonly canManage: boolean;
  readonly courses: readonly ResourceSummary[];
  readonly initialOfferings: readonly CourseOfferingView[];
  readonly organizationId: string;
  readonly terms: readonly ResourceSummary[];
}) {
  const [offerings, setOfferings] = useState(initialOfferings);
  const [windowKeys, setWindowKeys] = useState<readonly string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  function addWindow(): void {
    setWindowKeys((current) =>
      current.length >= maximumMeetingWindows
        ? current
        : [...current, crypto.randomUUID()],
    );
  }

  function removeWindow(key: string): void {
    setWindowKeys((current) =>
      current.filter((candidate) => candidate !== key),
    );
  }

  async function createOffering(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setMessage(null);
    setError(null);
    const capacity = positiveIntegerValue(form.get("capacity"));
    if (capacity === null) {
      setError("Enter the section capacity as a positive whole number.");
      return;
    }
    const meetingWindows: MeetingWindowView[] = [];
    for (const key of windowKeys) {
      const weekday = positiveIntegerValue(form.get(`weekday-${key}`));
      const startsAt = timeValue(form.get(`startsAt-${key}`));
      const endsAt = timeValue(form.get(`endsAt-${key}`));
      if (weekday === null || weekday > 7 || !startsAt || !endsAt) {
        setError(
          "Complete the weekday, start time, and end time of every meeting window.",
        );
        return;
      }
      meetingWindows.push({ weekday, startsAt, endsAt });
    }
    setSubmitting(true);
    try {
      const created = await clientApiRequest(
        "/api/v1/academics/course-offerings",
        parseCourseOffering,
        {
          method: "POST",
          organizationId,
          idempotencyKey: crypto.randomUUID(),
          body: {
            course_id: textValue(form.get("courseId")),
            term_id: textValue(form.get("termId")),
            campus_id: textValue(form.get("campusId")),
            section_code: textValue(form.get("sectionCode")),
            capacity,
            meeting_windows: meetingWindows.map((window) => ({
              weekday: window.weekday,
              starts_at: window.startsAt,
              ends_at: window.endsAt,
            })),
          },
        },
      );
      setOfferings((current) => [...current, created]);
      setMessage(
        `Course offering “${offeringLabel(created, courses, terms)}” was created.`,
      );
      setWindowKeys([]);
      formElement.reset();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The course offering could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="notification-layout">
      {offerings.length === 0 ? (
        <EmptyState message="No course offerings are available." />
      ) : (
        <section aria-labelledby="course-offerings-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Current records</p>
              <h2 id="course-offerings-heading">
                {offerings.length.toLocaleString()} course offering
                {offerings.length === 1 ? "" : "s"}
              </h2>
            </div>
          </div>
          <div className="resource-grid">
            {offerings.map((offering) => (
              <article className="resource-card" key={offering.id}>
                <div className="resource-card-heading">
                  <div>
                    <h2>{offeringLabel(offering, courses, terms)}</h2>
                    <p>
                      {resourceTitle(campuses, offering.campusId, "Campus")}
                    </p>
                  </div>
                  <span className="status-pill">
                    Capacity {offering.capacity}
                  </span>
                </div>
                <dl className="resource-metadata">
                  <div>
                    <dt>Meeting windows</dt>
                    <dd>
                      {offering.meetingWindows.length === 0
                        ? "None recorded"
                        : offering.meetingWindows
                            .map(describeWindow)
                            .join(", ")}
                    </dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </section>
      )}
      <form
        className="form-card"
        onSubmit={(event) => void createOffering(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Course catalog</p>
            <h2>Create a course offering</h2>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Course
            <select name="courseId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a course"
                resources={courses}
              />
            </select>
          </label>
          <label>
            Term
            <select name="termId" required defaultValue="">
              <ResourceOptions placeholder="Select a term" resources={terms} />
            </select>
          </label>
          <label>
            Campus
            <select name="campusId" required defaultValue="">
              <ResourceOptions
                placeholder="Select a campus"
                resources={campuses}
              />
            </select>
          </label>
          <label>
            Section code
            <input
              name="sectionCode"
              required
              maxLength={64}
              spellCheck={false}
            />
          </label>
          <label>
            Capacity
            <input name="capacity" type="number" min="1" step="1" required />
          </label>
        </div>
        <fieldset disabled={submitting}>
          <legend>
            Meeting windows (optional, up to {maximumMeetingWindows})
          </legend>
          {windowKeys.map((key, index) => (
            <div className="form-grid" key={key}>
              <label>
                Weekday {index + 1}
                <select name={`weekday-${key}`} required defaultValue="1">
                  {isoWeekdayNames.map((name, weekdayIndex) => (
                    <option key={name} value={weekdayIndex + 1}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Start time {index + 1}
                <input name={`startsAt-${key}`} type="time" required />
              </label>
              <label>
                End time {index + 1}
                <input name={`endsAt-${key}`} type="time" required />
              </label>
              <div className="form-actions">
                <button
                  className="button button-secondary button-small"
                  type="button"
                  onClick={() => removeWindow(key)}
                >
                  Remove window {index + 1}
                </button>
              </div>
            </div>
          ))}
          <div className="button-row">
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={windowKeys.length >= maximumMeetingWindows}
              onClick={addWindow}
            >
              Add meeting window
            </button>
          </div>
        </fieldset>
        <FormFeedback
          canMutate={canManage}
          csrfAvailable={csrfAvailable}
          error={error}
          message={message}
          permissionNotice="Your current membership cannot manage course offerings."
        />
        <div className="form-actions">
          <button
            className="button"
            type="submit"
            disabled={
              !canManage ||
              !csrfAvailable ||
              submitting ||
              courses.length === 0 ||
              terms.length === 0 ||
              campuses.length === 0
            }
          >
            {submitting ? "Creating…" : "Create course offering"}
          </button>
        </div>
      </form>
    </div>
  );
}
