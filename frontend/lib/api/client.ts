"use client";

import { ApiError, failureFromPayload } from "@/lib/api/errors";
import { csrfCookieName } from "@/lib/api/cookies";

export interface ClientRequestOptions {
  readonly method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  readonly body?: unknown;
  readonly organizationId?: string | null;
  readonly idempotencyKey?: string;
  readonly signal?: AbortSignal;
  /** Only unauthenticated endpoints such as OIDC login initiation may opt out. */
  readonly csrfProtection?: "required" | "not-applicable";
}

export function readCsrfCookie(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const prefix = `${csrfCookieName}=`;
  for (const part of document.cookie.split(";")) {
    const candidate = part.trim();
    if (candidate.startsWith(prefix)) {
      try {
        const value = decodeURIComponent(candidate.slice(prefix.length));
        return value === "" ? null : value;
      } catch {
        return null;
      }
    }
  }
  return null;
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

export async function clientApiRequest<T>(
  path: string,
  parse: (value: unknown) => T,
  options: ClientRequestOptions = {},
): Promise<T> {
  if (!path.startsWith("/api/v1/") || path.startsWith("//")) {
    throw new Error(
      "Client API requests must use the same-origin /api/v1 proxy.",
    );
  }
  const method = options.method ?? "GET";
  const isMutation = method !== "GET";
  const requiresCsrf =
    isMutation && options.csrfProtection !== "not-applicable";
  const csrfToken = requiresCsrf ? readCsrfCookie() : null;
  if (requiresCsrf && !csrfToken) {
    throw new ApiError({
      status: 403,
      code: "csrf_unavailable",
      message:
        "Editing is unavailable because this session is missing CSRF protection.",
    });
  }

  const headers = new Headers({ accept: "application/json" });
  if (options.body !== undefined) {
    headers.set("content-type", "application/json");
  }
  if (csrfToken) {
    headers.set("x-csrf-token", csrfToken);
  }
  if (options.organizationId) {
    headers.set("x-organization-id", options.organizationId);
  }
  if (options.idempotencyKey) {
    headers.set("idempotency-key", options.idempotencyKey);
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      ...(options.body === undefined
        ? {}
        : { body: JSON.stringify(options.body) }),
      ...(options.signal === undefined ? {} : { signal: options.signal }),
    });
  } catch {
    throw new ApiError({
      status: 503,
      code: "network_unavailable",
      message:
        "The request could not reach OwnSIS. Check your connection and retry.",
    });
  }

  const value = await parseJson(response);
  if (!response.ok) {
    throw new ApiError(
      failureFromPayload(
        response.status,
        value,
        response.headers.get("x-request-id") ?? undefined,
      ),
    );
  }
  return parse(value);
}
