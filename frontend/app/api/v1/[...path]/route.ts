import { getServerEnvironment } from "@/lib/env";

const forwardedRequestHeaders = [
  "accept",
  "content-type",
  "cookie",
  "x-csrf-token",
  "x-organization-id",
  "if-match",
  "idempotency-key",
] as const;

const forwardedResponseHeaders = [
  "content-type",
  "etag",
  "location",
  "retry-after",
  "www-authenticate",
] as const;

interface RouteContext {
  readonly params: Promise<{ readonly path: readonly string[] }>;
}

function correlationId(request: Request): string {
  const supplied = request.headers.get("x-request-id");
  return supplied && /^[a-zA-Z0-9._:-]{1,128}$/.test(supplied)
    ? supplied
    : crypto.randomUUID();
}

async function proxy(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const { path } = await context.params;
  if (
    path.length === 0 ||
    path.some((segment) => !segment || segment === "." || segment === "..")
  ) {
    return Response.json(
      { error: { code: "invalid_api_path", message: "Invalid API path." } },
      { status: 400 },
    );
  }

  const requestCorrelationId = correlationId(request);
  const environment = getServerEnvironment();
  const upstreamUrl = new URL(
    `/api/v1/${path.map(encodeURIComponent).join("/")}`,
    environment.backendUrl,
  );
  upstreamUrl.search = new URL(request.url).search;
  const upstreamHeaders = new Headers();
  for (const name of forwardedRequestHeaders) {
    const value = request.headers.get(name);
    if (value) {
      upstreamHeaders.set(name, value);
    }
  }
  upstreamHeaders.set("x-request-id", requestCorrelationId);

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: upstreamHeaders,
      cache: "no-store",
      redirect: "manual",
      ...(hasBody ? { body: await request.arrayBuffer() } : {}),
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "backend_unavailable",
          message: "OwnSIS cannot reach the application service right now.",
        },
      },
      {
        status: 502,
        headers: {
          "cache-control": "no-store",
          "x-request-id": requestCorrelationId,
        },
      },
    );
  }

  const responseHeaders = new Headers({
    "cache-control": "no-store",
    "x-request-id":
      upstream.headers.get("x-request-id") ?? requestCorrelationId,
  });
  for (const name of forwardedResponseHeaders) {
    const value = upstream.headers.get(name);
    if (value) {
      responseHeaders.set(name, value);
    }
  }
  const cookieHeaders = (
    upstream.headers as Headers & { getSetCookie?: () => readonly string[] }
  ).getSetCookie?.();
  if (cookieHeaders) {
    for (const cookie of cookieHeaders) {
      responseHeaders.append("set-cookie", cookie);
    }
  } else {
    const cookie = upstream.headers.get("set-cookie");
    if (cookie) {
      responseHeaders.append("set-cookie", cookie);
    }
  }

  return new Response(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  return proxy(request, context);
}

export function POST(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  return proxy(request, context);
}

export function PUT(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  return proxy(request, context);
}

export function PATCH(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  return proxy(request, context);
}

export function DELETE(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  return proxy(request, context);
}
