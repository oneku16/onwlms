import "server-only";

export interface ServerEnvironment {
  readonly backendUrl: URL;
}

let validatedEnvironment: ServerEnvironment | undefined;

function parseBackendUrl(rawValue: string | undefined): URL {
  const value = rawValue ?? "http://localhost:8000";
  let parsed: URL;

  try {
    parsed = new URL(value);
  } catch {
    throw new Error("BACKEND_URL must be an absolute http(s) URL.");
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("BACKEND_URL must use http or https.");
  }
  if (parsed.username || parsed.password) {
    throw new Error("BACKEND_URL must not contain credentials.");
  }
  if (parsed.search || parsed.hash) {
    throw new Error("BACKEND_URL must not contain a query or fragment.");
  }
  if (parsed.pathname !== "/") {
    throw new Error("BACKEND_URL must be an origin without a path.");
  }

  return parsed;
}

export function getServerEnvironment(): ServerEnvironment {
  validatedEnvironment ??= Object.freeze({
    backendUrl: parseBackendUrl(process.env.BACKEND_URL),
  });
  return validatedEnvironment;
}
