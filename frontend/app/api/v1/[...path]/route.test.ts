import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/env", () => ({
  getServerEnvironment: () => ({
    backendUrl: new URL("http://backend.test"),
  }),
}));

import { GET } from "@/app/api/v1/[...path]/route";

describe("same-origin API proxy", () => {
  it("forwards callback redirects and every Set-Cookie header", async () => {
    const callbackCookies = [
      "ownsis_session_pending=; Path=/api/v1/auth/callback; Max-Age=0; HttpOnly; SameSite=lax",
      "ownsis_session=session-value; Path=/; HttpOnly; SameSite=lax",
      "ownsis_csrf=csrf-value; Path=/; SameSite=strict",
    ];
    const upstreamHeaders = new Headers({
      location: "http://localhost:3000/dashboard",
    });
    for (const cookie of callbackCookies) {
      upstreamHeaders.append("set-cookie", cookie);
    }
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, {
        status: 303,
        headers: upstreamHeaders,
      }),
    );

    const response = await GET(
      new Request(
        "http://localhost:3000/api/v1/auth/callback?code=development.test&state=state-value",
        {
          headers: {
            cookie:
              "ownsis_session_pending=pending-value; unrelated=browser-value",
          },
        },
      ),
      {
        params: Promise.resolve({ path: ["auth", "callback"] }),
      },
    );

    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(
      "http://localhost:3000/dashboard",
    );
    expect(response.headers.getSetCookie()).toEqual(callbackCookies);
    expect(fetchMock).toHaveBeenCalledOnce();
    const fetchCall = fetchMock.mock.calls[0];
    expect(fetchCall).toBeDefined();
    if (!fetchCall) {
      throw new Error("Expected the proxy to call the backend once.");
    }
    const [upstreamUrl, requestInit] = fetchCall;
    expect(upstreamUrl.toString()).toBe(
      "http://backend.test/api/v1/auth/callback?code=development.test&state=state-value",
    );
    expect(requestInit?.redirect).toBe("manual");
    expect(new Headers(requestInit?.headers).get("cookie")).toBe(
      "ownsis_session_pending=pending-value; unrelated=browser-value",
    );
  });
});
