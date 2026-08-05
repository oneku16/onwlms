"use client";

export default function GlobalError({
  reset,
}: {
  readonly error: Error & { digest?: string };
  readonly reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <main className="standalone-state">
          <section className="state-panel state-error" role="alert">
            <p className="state-kicker">Unexpected failure</p>
            <h1>OwnSIS could not render this page</h1>
            <p>
              No changes were made. Retry, or contact support if this continues.
            </p>
            <button className="button" type="button" onClick={reset}>
              Retry
            </button>
          </section>
        </main>
      </body>
    </html>
  );
}
