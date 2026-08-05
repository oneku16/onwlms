import "server-only";

import { cookies, headers } from "next/headers";

import { ApiError, failureFromPayload } from "@/lib/api/errors";
import { getServerEnvironment } from "@/lib/env";

const requestTimeoutMilliseconds = 10_000;

export interface ServerApiRequestOptions extends RequestInit {
  readonly organizationId?: string;
}

function assertApiPath(path: string): void {
  if (!path.startsWith("/api/v1/") || path.includes("\\")) {
    throw new Error("Server API requests must use an /api/v1/ path.");
  }
}

async function safeJson(response: Response): Promise<unknown> {
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

export async function serverApiRequest<T>(
  path: string,
  parse: (value: unknown) => T,
  options: ServerApiRequestOptions = {},
): Promise<T> {
  assertApiPath(path);
  const environment = getServerEnvironment();
  const cookieStore = await cookies();
  const incomingHeaders = await headers();
  const cookieHeader = cookieStore
    .getAll()
    .map(({ name, value }) => `${name}=${value}`)
    .join("; ");
  const correlationId =
    incomingHeaders.get("x-request-id") ?? crypto.randomUUID();
  const { organizationId, ...init } = options;
  const requestHeaders = new Headers(init.headers);
  requestHeaders.set("accept", "application/json");
  requestHeaders.set("x-request-id", correlationId);
  if (cookieHeader) {
    requestHeaders.set("cookie", cookieHeader);
  }
  if (organizationId) {
    requestHeaders.set("x-organization-id", organizationId);
  }

  let response: Response;
  try {
    response = await fetch(new URL(path, environment.backendUrl), {
      ...init,
      cache: "no-store",
      headers: requestHeaders,
      redirect: "manual",
      signal: AbortSignal.timeout(requestTimeoutMilliseconds),
    });
  } catch {
    throw new ApiError({
      status: 503,
      code: "backend_unavailable",
      message: "OwnSIS is temporarily unable to reach the application service.",
      correlationId,
    });
  }

  const value = await safeJson(response);
  if (!response.ok) {
    throw new ApiError(
      failureFromPayload(
        response.status,
        value,
        response.headers.get("x-request-id") ?? correlationId,
      ),
    );
  }

  try {
    return parse(value);
  } catch {
    throw new ApiError({
      status: 502,
      code: "invalid_backend_response",
      message:
        "OwnSIS received an unsupported response from the application service.",
      correlationId,
    });
  }
}
