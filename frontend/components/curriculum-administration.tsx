"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { FormFeedback } from "@/components/form-feedback";
import { ResourceOptions } from "@/components/resource-options";
import {
  curriculumCourseKinds,
  parseCurriculum,
  type CurriculumCourseKind,
  type CurriculumCourseView,
} from "@/lib/api/academics";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  resourceLabel,
  resourceTitle,
  type ResourceSummary,
} from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import { decimalValue, textValue } from "@/lib/forms";

const maximumCurriculumRows = 100;

interface CurriculumRow {
  readonly key: number;
  readonly courseId: string;
  readonly kind: CurriculumCourseKind;
  readonly credits: string;
  readonly prerequisiteCourseIds: readonly string[];
}

interface LoadedCurriculum {
  readonly id: string;
  readonly programId: string;
  readonly academicYearId: string;
  /** False when the backend reported no curriculum and saving will create one. */
  readonly persisted: boolean;
  readonly rows: readonly CurriculumRow[];
}

function rowsFromCourses(
  courses: readonly CurriculumCourseView[],
): readonly CurriculumRow[] {
  return courses.map((course, index) => ({
    key: index,
    courseId: course.courseId,
    kind: course.kind,
    credits: course.credits,
    prerequisiteCourseIds: course.prerequisiteCourseIds,
  }));
}

function isCurriculumCourseKind(value: string): value is CurriculumCourseKind {
  return curriculumCourseKinds.some((kind) => kind === value);
}

export function CurriculumAdministration({
  academicYears,
  canManage,
  courses,
  organizationId,
  programs,
}: {
  readonly academicYears: readonly ResourceSummary[];
  readonly canManage: boolean;
  readonly courses: readonly ResourceSummary[];
  readonly organizationId: string;
  readonly programs: readonly ResourceSummary[];
}) {
  const [curriculum, setCurriculum] = useState<LoadedCurriculum | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function loadCurriculum(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const programId = textValue(form.get("programId"));
    const academicYearId = textValue(form.get("academicYearId"));
    setLoading(true);
    setLoadError(null);
    setMessage(null);
    setError(null);
    setCurriculum(null);
    const query = new URLSearchParams({
      program_id: programId,
      academic_year_id: academicYearId,
    });
    try {
      const loaded = await clientApiRequest(
        `/api/v1/academics/curricula?${query.toString()}`,
        parseCurriculum,
        { organizationId },
      );
      setCurriculum({
        id: loaded.id,
        programId: loaded.programId,
        academicYearId: loaded.academicYearId,
        persisted: true,
        rows: rowsFromCourses(loaded.courses),
      });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        setCurriculum({
          id: crypto.randomUUID(),
          programId,
          academicYearId,
          persisted: false,
          rows: [],
        });
      } else {
        setLoadError(
          caught instanceof ApiError
            ? caught.message
            : "The curriculum could not be loaded.",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  function addRow(): void {
    setCurriculum((current) => {
      if (!current || current.rows.length >= maximumCurriculumRows) {
        return current;
      }
      const nextKey = Math.max(...current.rows.map((row) => row.key), -1) + 1;
      return {
        ...current,
        rows: [
          ...current.rows,
          {
            key: nextKey,
            courseId: "",
            kind: "required",
            credits: "",
            prerequisiteCourseIds: [],
          },
        ],
      };
    });
  }

  function removeRow(key: number): void {
    setCurriculum((current) =>
      current
        ? { ...current, rows: current.rows.filter((row) => row.key !== key) }
        : current,
    );
  }

  async function saveCurriculum(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    if (!curriculum) {
      return;
    }
    const form = new FormData(event.currentTarget);
    setMessage(null);
    setError(null);
    const courseBodies: {
      course_id: string;
      kind: CurriculumCourseKind;
      credits: string;
      prerequisite_course_ids: string[];
    }[] = [];
    for (const row of curriculum.rows) {
      const courseId = textValue(form.get(`courseId-${row.key}`));
      const kind = textValue(form.get(`kind-${row.key}`));
      const credits = decimalValue(form.get(`credits-${row.key}`));
      if (!courseId || !isCurriculumCourseKind(kind) || !credits) {
        setError(
          "Select a course, kind, and decimal credit value for every row.",
        );
        return;
      }
      courseBodies.push({
        course_id: courseId,
        kind,
        credits,
        prerequisite_course_ids: form
          .getAll(`prerequisites-${row.key}`)
          .map(String)
          .filter((candidate) => candidate !== courseId),
      });
    }
    setSaving(true);
    try {
      const saved = await clientApiRequest(
        `/api/v1/academics/curricula/${encodeURIComponent(curriculum.id)}`,
        parseCurriculum,
        {
          method: "PUT",
          organizationId,
          body: {
            program_id: curriculum.programId,
            academic_year_id: curriculum.academicYearId,
            courses: courseBodies,
          },
        },
      );
      setCurriculum({
        id: saved.id,
        programId: saved.programId,
        academicYearId: saved.academicYearId,
        persisted: true,
        rows: rowsFromCourses(saved.courses),
      });
      setMessage(
        `Curriculum saved with ${saved.courses.length.toLocaleString()} course${saved.courses.length === 1 ? "" : "s"}.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The curriculum could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="notification-layout">
      <form
        className="form-card"
        onSubmit={(event) => void loadCurriculum(event)}
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">Program curriculum</p>
            <h2>Choose a program and academic year</h2>
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
            Academic year
            <select name="academicYearId" required defaultValue="">
              <ResourceOptions
                placeholder="Select an academic year"
                resources={academicYears}
              />
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
            disabled={
              loading || programs.length === 0 || academicYears.length === 0
            }
          >
            {loading ? "Loading curriculum…" : "Load curriculum"}
          </button>
        </div>
      </form>
      {curriculum ? (
        <form
          className="form-card"
          key={`${curriculum.id}:${curriculum.persisted ? "saved" : "new"}`}
          onSubmit={(event) => void saveCurriculum(event)}
        >
          <div className="section-heading">
            <div>
              <p className="eyebrow">
                {resourceTitle(programs, curriculum.programId, "Program")} ·{" "}
                {resourceTitle(
                  academicYears,
                  curriculum.academicYearId,
                  "Academic year",
                )}
              </p>
              <h2>
                {curriculum.persisted
                  ? "Edit curriculum courses"
                  : "Create the curriculum"}
              </h2>
            </div>
            <span className="status-pill">
              {curriculum.persisted ? "configured" : "not configured"}
            </span>
          </div>
          {!curriculum.persisted ? (
            <p className="inline-notice">
              No curriculum is configured for this program and academic year.
              Saving creates it.
            </p>
          ) : null}
          <fieldset disabled={saving}>
            <legend>Courses (up to {maximumCurriculumRows})</legend>
            {curriculum.rows.length === 0 ? (
              <p className="inline-notice">
                No courses are listed. Add a course row to begin.
              </p>
            ) : null}
            {curriculum.rows.map((row, index) => (
              <div className="form-grid" key={row.key}>
                <label>
                  Course {index + 1}
                  <select
                    name={`courseId-${row.key}`}
                    required
                    defaultValue={row.courseId}
                  >
                    <ResourceOptions
                      placeholder="Select a course"
                      resources={courses}
                    />
                  </select>
                </label>
                <label>
                  Kind {index + 1}
                  <select
                    name={`kind-${row.key}`}
                    required
                    defaultValue={row.kind}
                  >
                    {curriculumCourseKinds.map((kind) => (
                      <option key={kind} value={kind}>
                        {kind}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Credits {index + 1}
                  <input
                    name={`credits-${row.key}`}
                    required
                    inputMode="decimal"
                    pattern="\d+(\.\d+)?"
                    maxLength={12}
                    defaultValue={row.credits}
                  />
                </label>
                <label>
                  Prerequisites {index + 1}
                  <select
                    name={`prerequisites-${row.key}`}
                    multiple
                    size={4}
                    defaultValue={[...row.prerequisiteCourseIds]}
                  >
                    {courses.map((course) => (
                      <option key={course.id} value={course.id}>
                        {resourceLabel(course)}
                      </option>
                    ))}
                  </select>
                  <small>
                    Select none, one, or several prerequisite courses.
                  </small>
                </label>
                <div className="form-actions">
                  <button
                    className="button button-secondary button-small"
                    type="button"
                    onClick={() => removeRow(row.key)}
                  >
                    Remove course {index + 1}
                  </button>
                </div>
              </div>
            ))}
            <div className="button-row">
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={
                  courses.length === 0 ||
                  curriculum.rows.length >= maximumCurriculumRows
                }
                onClick={addRow}
              >
                Add course row
              </button>
            </div>
          </fieldset>
          <FormFeedback
            canMutate={canManage}
            csrfAvailable={csrfAvailable}
            error={error}
            message={message}
            permissionNotice="Your current membership cannot manage curricula."
          />
          <div className="form-actions">
            <button
              className="button"
              type="submit"
              disabled={!canManage || !csrfAvailable || saving}
            >
              {saving ? "Saving…" : "Save curriculum"}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
