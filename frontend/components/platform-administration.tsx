"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import {
  parsePlatformAdministrator,
  type PlatformAdministratorView,
} from "@/lib/api/administration";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";

const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function PlatformAdministration({
  initialAdministrators,
}: {
  readonly initialAdministrators: readonly PlatformAdministratorView[];
}) {
  const [administrators, setAdministrators] = useState(initialAdministrators);
  const [pendingSubjectId, setPendingSubjectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  function store(updated: PlatformAdministratorView): void {
    setAdministrators((current) => {
      const exists = current.some(
        (administrator) => administrator.subjectId === updated.subjectId,
      );
      return exists
        ? current.map((administrator) =>
            administrator.subjectId === updated.subjectId
              ? updated
              : administrator,
          )
        : [...current, updated];
    });
  }

  async function mutate(
    subjectId: string,
    action: "assign" | "revoke",
  ): Promise<void> {
    if (
      action === "revoke" &&
      !window.confirm(
        "Revoke this platform administrator? OwnSIS will reject removal of the final active administrator.",
      )
    ) {
      return;
    }
    setError(null);
    setPendingSubjectId(subjectId);
    try {
      store(
        await clientApiRequest(
          `/api/v1/platform/administrators/${encodeURIComponent(subjectId)}/${action}`,
          parsePlatformAdministrator,
          { method: "POST" },
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The platform-administrator change could not be saved.",
      );
    } finally {
      setPendingSubjectId(null);
    }
  }

  async function assign(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget;
    const subjectId = String(new FormData(form).get("subjectId") ?? "").trim();
    if (!uuidPattern.test(subjectId)) {
      setError("Enter a valid existing OwnID subject identifier.");
      return;
    }
    await mutate(subjectId, "assign");
    form.reset();
  }

  return (
    <>
      <form className="form-card" onSubmit={(event) => void assign(event)}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">Global privilege</p>
            <h2>Assign a platform administrator</h2>
          </div>
        </div>
        <div className="form-grid">
          <label className="form-span">
            Existing OwnID subject identifier
            <input name="subjectId" required autoComplete="off" />
            <small>
              Assignment grants platform governance only; it does not grant
              tenant academic access.
            </small>
          </label>
        </div>
        <div className="form-actions">
          <button
            className="button"
            disabled={!csrfAvailable || pendingSubjectId !== null}
            type="submit"
          >
            Assign administrator
          </button>
        </div>
      </form>
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      <section aria-labelledby="platform-administrators-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Governed assignments</p>
            <h2 id="platform-administrators-heading">
              Platform administrators
            </h2>
          </div>
        </div>
        <div className="resource-grid">
          {administrators.map((administrator) => (
            <article className="resource-card" key={administrator.subjectId}>
              <div className="resource-card-heading">
                <div>
                  <h2>Subject {administrator.subjectId.slice(0, 8)}</h2>
                  <p>{administrator.subjectId}</p>
                </div>
                <span className="status-pill">
                  {administrator.active ? "active" : "revoked"}
                </span>
              </div>
              <div className="button-row">
                <button
                  className="button button-secondary"
                  disabled={!csrfAvailable || pendingSubjectId !== null}
                  onClick={() =>
                    void mutate(
                      administrator.subjectId,
                      administrator.active ? "revoke" : "assign",
                    )
                  }
                  type="button"
                >
                  {administrator.active ? "Revoke" : "Reactivate"}
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
