"use client";

import type { DragEvent, FormEvent } from "react";
import { useMemo, useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  parseScheduleConflicts,
  parseScheduleSession,
  type ScheduleConflict,
  type ScheduleSession,
} from "@/lib/api/schedule";
import { useCsrfProtection } from "@/lib/api/use-csrf";

const timeSlots = ["08:00", "09:30", "11:00", "13:00", "14:30", "16:00"];

interface TimetableBoardProps {
  readonly canEdit: boolean;
  readonly initialSessions: readonly ScheduleSession[];
  readonly organizationId: string;
  readonly weekStart: string;
  readonly timezone: string;
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function weekDates(weekStart: string): readonly string[] {
  const start = new Date(`${weekStart}T00:00:00Z`);
  return Array.from({ length: 5 }, (_, offset) => {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + offset);
    return isoDate(date);
  });
}

function displayDay(date: string): { weekday: string; date: string } {
  const parsed = new Date(`${date}T12:00:00Z`);
  return {
    weekday: new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(
      parsed,
    ),
    date: new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    }).format(parsed),
  };
}

function dateTimeParts(
  isoValue: string,
  timezone: string,
): { date: string; time: string } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(isoValue));
  const part = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((entry) => entry.type === type)?.value ?? "";
  return {
    date: `${part("year")}-${part("month")}-${part("day")}`,
    time: `${part("hour")}:${part("minute")}`,
  };
}

function movedDateTimes(
  session: ScheduleSession,
  date: string,
  time: string,
  timezone: string,
): { startsAt: string; endsAt: string } {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(
    `${date}T${time}`,
  );
  if (!match) {
    throw new Error("The timetable target is invalid.");
  }
  const desired = {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
  };
  const desiredAsUtc = Date.UTC(
    desired.year,
    desired.month - 1,
    desired.day,
    desired.hour,
    desired.minute,
  );
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  let candidate = desiredAsUtc;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const parts = formatter.formatToParts(new Date(candidate));
    const part = (type: Intl.DateTimeFormatPartTypes): number =>
      Number(parts.find((entry) => entry.type === type)?.value ?? Number.NaN);
    const representedAsUtc = Date.UTC(
      part("year"),
      part("month") - 1,
      part("day"),
      part("hour"),
      part("minute"),
    );
    candidate += desiredAsUtc - representedAsUtc;
  }
  const represented = Object.fromEntries(
    formatter
      .formatToParts(new Date(candidate))
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, Number(part.value)]),
  );
  if (
    represented.year !== desired.year ||
    represented.month !== desired.month ||
    represented.day !== desired.day ||
    represented.hour !== desired.hour ||
    represented.minute !== desired.minute
  ) {
    throw new Error("The timetable target does not exist in this timezone.");
  }
  const startsAt = new Date(candidate);
  const duration =
    new Date(session.endsAt).getTime() - new Date(session.startsAt).getTime();
  const endsAt = new Date(startsAt.getTime() + Math.max(duration, 30 * 60_000));
  return { startsAt: startsAt.toISOString(), endsAt: endsAt.toISOString() };
}

function replaceSession(
  sessions: readonly ScheduleSession[],
  updated: ScheduleSession,
): readonly ScheduleSession[] {
  return sessions.map((session) =>
    session.id === updated.id ? updated : session,
  );
}

function TimetableSessionCard({
  session,
  editable,
  timezone,
  onDragStart,
  onSelect,
}: {
  readonly session: ScheduleSession;
  readonly editable: boolean;
  readonly timezone: string;
  readonly onDragStart: (event: DragEvent<HTMLElement>, id: string) => void;
  readonly onSelect: (id: string) => void;
}) {
  const start = dateTimeParts(session.startsAt, timezone).time;
  const end = dateTimeParts(session.endsAt, timezone).time;
  return (
    <article
      className="session-card"
      draggable={editable}
      onDragStart={(event) => onDragStart(event, session.id)}
      data-session-id={session.id}
    >
      <div className="session-time">
        {start}–{end}
      </div>
      <h3>{session.title}</h3>
      <p>{[session.group, session.room].filter(Boolean).join(" · ")}</p>
      {session.teacher ? <small>{session.teacher}</small> : null}
      {session.locked ? <span className="status-pill">Locked</span> : null}
      <button
        className="session-select"
        type="button"
        disabled={!editable}
        onClick={() => onSelect(session.id)}
      >
        Select to move
      </button>
    </article>
  );
}

export function TimetableBoard({
  canEdit,
  initialSessions,
  organizationId,
  weekStart,
  timezone,
}: TimetableBoardProps) {
  const [sessions, setSessions] = useState(initialSessions);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState(initialSessions[0]?.id ?? "");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<readonly ScheduleConflict[]>([]);
  const [saving, setSaving] = useState(false);
  const csrfAvailable = useCsrfProtection();
  const dates = useMemo(() => weekDates(weekStart), [weekStart]);
  const editable = canEdit && csrfAvailable && !saving;

  async function toggleSelectedLock(): Promise<void> {
    const current = sessions.find((session) => session.id === selectedId);
    if (!current || !csrfAvailable) {
      return;
    }
    setSaving(true);
    setConflicts([]);
    try {
      const updated = await clientApiRequest(
        `/api/v1/scheduling/sessions/${encodeURIComponent(current.id)}/lock`,
        parseScheduleSession,
        {
          method: "PATCH",
          organizationId,
          body: { locked: current.locked !== true, version: current.version },
        },
      );
      setSessions((latest) => replaceSession(latest, updated));
      setFeedback(
        `${updated.title} ${updated.locked ? "locked" : "unlocked"} successfully.`,
      );
    } catch (caught) {
      setFeedback(
        caught instanceof ApiError
          ? caught.message
          : "The session lock could not be changed.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function moveSession(
    sessionId: string,
    targetDate: string,
    targetTime: string,
  ): Promise<void> {
    const current = sessions.find((session) => session.id === sessionId);
    if (!current || !csrfAvailable) {
      return;
    }
    const previous = sessions;
    let moved: { startsAt: string; endsAt: string };
    try {
      moved = movedDateTimes(current, targetDate, targetTime, timezone);
    } catch {
      setFeedback(
        "That local timetable slot cannot be represented in the organization timezone.",
      );
      return;
    }
    const optimistic: ScheduleSession = {
      ...current,
      startsAt: moved.startsAt,
      endsAt: moved.endsAt,
    };
    setSessions(replaceSession(sessions, optimistic));
    setFeedback(`Saving ${current.title}…`);
    setConflicts([]);
    setSaving(true);
    try {
      const updated = await clientApiRequest(
        `/api/v1/scheduling/sessions/${encodeURIComponent(current.id)}`,
        (value) => (value === null ? optimistic : parseScheduleSession(value)),
        {
          method: "PATCH",
          organizationId,
          body: {
            starts_at: moved.startsAt,
            ends_at: moved.endsAt,
            version: current.version,
          },
        },
      );
      setSessions((latest) => replaceSession(latest, updated));
      setFeedback(`${current.title} moved successfully.`);
    } catch (caught) {
      setSessions(previous);
      if (caught instanceof ApiError && caught.status === 409) {
        const reported = parseScheduleConflicts(caught.details);
        setConflicts(
          reported.length > 0
            ? reported
            : [{ code: caught.code, message: caught.message }],
        );
        setFeedback(`${current.title} was not moved.`);
      } else {
        setFeedback(
          caught instanceof ApiError
            ? caught.message
            : "The timetable change could not be saved.",
        );
      }
    } finally {
      setSaving(false);
      setDraggingId(null);
    }
  }

  function startDrag(event: DragEvent<HTMLElement>, id: string): void {
    setDraggingId(id);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", id);
  }

  function drop(
    event: DragEvent<HTMLDivElement>,
    date: string,
    time: string,
  ): void {
    event.preventDefault();
    const sessionId =
      event.dataTransfer.getData("text/plain") || draggingId || "";
    if (sessionId) {
      void moveSession(sessionId, date, time);
    }
  }

  function keyboardMove(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const date = String(form.get("date") ?? "");
    const time = String(form.get("time") ?? "");
    if (selectedId && dates.includes(date) && timeSlots.includes(time)) {
      void moveSession(selectedId, date, time);
    }
  }

  const offGridSessions = sessions.filter((session) => {
    const parts = dateTimeParts(session.startsAt, timezone);
    return !dates.includes(parts.date) || !timeSlots.includes(parts.time);
  });

  return (
    <div className="timetable-workspace">
      {!canEdit ? (
        <p className="inline-notice">
          Your permissions allow timetable viewing but not timetable editing.
        </p>
      ) : !csrfAvailable ? (
        <p className="inline-notice">
          Timetable editing is unavailable because this session did not provide
          CSRF protection. The schedule remains read-only.
        </p>
      ) : null}

      <section className="form-card timetable-create">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Authoritative context required</p>
            <h2>Manual session creation is unavailable</h2>
          </div>
        </div>
        <p>
          The portal will not accept pasted scheduling identifiers. Manual
          creation remains disabled until an authoritative activity catalog can
          supply the activity, offering, room, teacher, and group choices
          together. Existing sessions can still be moved and locked through the
          verified organization context.
        </p>
      </section>

      <form className="keyboard-move" onSubmit={keyboardMove}>
        <div>
          <strong>Keyboard move</strong>
          <span>Select a session, day, and start time.</span>
        </div>
        <label>
          Session
          <select
            name="session"
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
            disabled={!editable}
          >
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>
                {session.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Day
          <select name="date" disabled={!editable} defaultValue={dates[0]}>
            {dates.map((date) => (
              <option key={date} value={date}>
                {displayDay(date).weekday} {displayDay(date).date}
              </option>
            ))}
          </select>
        </label>
        <label>
          Time
          <select name="time" disabled={!editable} defaultValue={timeSlots[0]}>
            {timeSlots.map((time) => (
              <option key={time} value={time}>
                {time}
              </option>
            ))}
          </select>
        </label>
        <button
          className="button button-small"
          type="submit"
          disabled={!editable || !selectedId}
        >
          Move session
        </button>
        <button
          className="button button-secondary button-small"
          type="button"
          disabled={!editable || !selectedId}
          onClick={() => void toggleSelectedLock()}
        >
          {sessions.find((session) => session.id === selectedId)?.locked
            ? "Unlock session"
            : "Lock session"}
        </button>
      </form>

      <div
        className="timetable-scroll"
        tabIndex={0}
        aria-label="Weekly timetable"
      >
        <div className="timetable-grid" role="grid">
          <div className="timetable-corner" role="columnheader">
            Time
          </div>
          {dates.map((date) => {
            const label = displayDay(date);
            return (
              <div className="timetable-day" role="columnheader" key={date}>
                <strong>{label.weekday}</strong>
                <span>{label.date}</span>
              </div>
            );
          })}
          {timeSlots.flatMap((time) => [
            <div
              className="timetable-time"
              role="rowheader"
              key={`${time}-label`}
            >
              {time}
            </div>,
            ...dates.map((date) => {
              const matching = sessions.filter((session) => {
                const parts = dateTimeParts(session.startsAt, timezone);
                return parts.date === date && parts.time === time;
              });
              const day = displayDay(date);
              return (
                <div
                  className="timetable-cell"
                  role="gridcell"
                  aria-label={`${day.weekday} ${day.date} at ${time}`}
                  key={`${date}-${time}`}
                  onDragOver={(event) => {
                    if (editable) {
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                    }
                  }}
                  onDrop={(event) => drop(event, date, time)}
                >
                  {matching.map((session) => (
                    <TimetableSessionCard
                      key={session.id}
                      session={session}
                      editable={editable}
                      timezone={timezone}
                      onDragStart={startDrag}
                      onSelect={setSelectedId}
                    />
                  ))}
                </div>
              );
            }),
          ])}
        </div>
      </div>

      {offGridSessions.length > 0 ? (
        <section className="off-grid-sessions">
          <h2>Sessions outside this work week or time grid</h2>
          <p>
            They remain unchanged and can be moved with the keyboard controls.
          </p>
          <ul>
            {offGridSessions.map((session) => (
              <li key={session.id}>{session.title}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="timetable-feedback" aria-live="polite">
        {feedback ? <p>{feedback}</p> : null}
      </div>
      {conflicts.length > 0 ? (
        <section className="conflict-panel" role="alert">
          <h2>Schedule conflict</h2>
          <p>
            The backend rejected this change and the timetable was restored.
          </p>
          <ul>
            {conflicts.map((conflict, index) => (
              <li key={`${conflict.code}-${index}`}>{conflict.message}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
