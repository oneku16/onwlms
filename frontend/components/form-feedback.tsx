export function FormFeedback({
  canMutate,
  csrfAvailable,
  error,
  message,
  permissionNotice,
}: {
  readonly canMutate: boolean;
  readonly csrfAvailable: boolean;
  readonly error: string | null;
  readonly message: string | null;
  readonly permissionNotice: string;
}) {
  return (
    <>
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
      {!canMutate ? (
        <p className="inline-notice">{permissionNotice}</p>
      ) : !csrfAvailable ? (
        <p className="inline-notice">
          Editing is unavailable because the session has no CSRF token.
        </p>
      ) : null}
    </>
  );
}
