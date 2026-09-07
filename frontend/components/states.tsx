import Link from "next/link";

interface ErrorStateProps {
  readonly title?: string;
  readonly message: string;
  readonly correlationId?: string | undefined;
}

export function ErrorState({
  title = "This information is unavailable",
  message,
  correlationId,
}: ErrorStateProps) {
  return (
    <section className="state-panel state-error" role="alert">
      <p className="state-kicker">Request not completed</p>
      <h2>{title}</h2>
      <p>{message}</p>
      {correlationId ? (
        <p className="correlation">Reference: {correlationId}</p>
      ) : null}
    </section>
  );
}

export function EmptyState({ message }: { readonly message: string }) {
  return (
    <section className="state-panel">
      <p className="state-kicker">No records</p>
      <h2>Nothing to show yet</h2>
      <p>{message}</p>
    </section>
  );
}

export function UnavailableState({ reason }: { readonly reason: string }) {
  return (
    <section className="state-panel state-unavailable">
      <p className="state-kicker">Not included in this release</p>
      <h2>Capability unavailable</h2>
      <p>{reason}</p>
      <p>No placeholder values or inferred records are displayed.</p>
    </section>
  );
}

export function AccessDenied() {
  return (
    <section className="state-panel state-error" role="alert">
      <p className="state-kicker">Access denied</p>
      <h1>This capability is not available to you</h1>
      <p>
        Your current organization, roles, permissions, or entitlements do not
        allow this page. OwnSIS has not attempted to load its records.
      </p>
      <Link className="button button-secondary" href="/dashboard">
        Return to dashboard
      </Link>
    </section>
  );
}

export function LoadingState() {
  return (
    <section
      className="loading-grid"
      aria-label="Loading page"
      aria-busy="true"
    >
      <div className="loading-line loading-line-wide" />
      <div className="loading-line" />
      <div className="loading-card" />
      <div className="loading-card" />
      <span className="visually-hidden">Loading</span>
    </section>
  );
}
