"use client";

export default function PortalError({
  reset,
}: {
  readonly error: Error & { digest?: string };
  readonly reset: () => void;
}) {
  return (
    <section className="state-panel state-error" role="alert">
      <p className="state-kicker">Page unavailable</p>
      <h1>This OwnSIS page could not be loaded</h1>
      <p>No changes were made. Retry the page when the service is available.</p>
      <button className="button" type="button" onClick={reset}>
        Retry
      </button>
    </section>
  );
}
