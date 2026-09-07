import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import {
  activeOrganizationCookieName,
  csrfCookieName,
} from "@/lib/api/cookies";
import { parseOrganization } from "@/lib/api/session";
import { serverApiRequest } from "@/lib/api/server";
import { asRecord, asString } from "@/lib/api/validation";

const organizationIdPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function POST(request: Request): Promise<Response> {
  const cookieStore = await cookies();
  const cookieToken = cookieStore.get(csrfCookieName)?.value;
  const headerToken = request.headers.get("x-csrf-token");
  if (!cookieToken || !headerToken || cookieToken !== headerToken) {
    return Response.json(
      {
        error: {
          code: "csrf_invalid",
          message: "The organization context could not be changed safely.",
        },
      },
      { status: 403 },
    );
  }

  let payload: unknown;
  try {
    payload = (await request.json()) as unknown;
  } catch {
    payload = null;
  }
  const organizationId = asString(asRecord(payload)?.organizationId);
  if (!organizationId || !organizationIdPattern.test(organizationId)) {
    return Response.json(
      {
        error: {
          code: "organization_invalid",
          message: "Choose a valid organization.",
        },
      },
      { status: 400 },
    );
  }

  await serverApiRequest("/api/v1/organization", parseOrganization, {
    organizationId,
  });
  const response = NextResponse.json({ organization_id: organizationId });
  response.cookies.set(activeOrganizationCookieName, organizationId, {
    httpOnly: true,
    maxAge: 60 * 60 * 24 * 30,
    path: "/",
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
  });
  return response;
}
