import { describe, expect, it } from "vitest";

import { createSecurityHeaders } from "@/lib/security-headers";

function contentSecurityPolicy(nodeEnvironment: string | undefined): string {
  const header = createSecurityHeaders(nodeEnvironment).find(
    ({ key }) => key === "Content-Security-Policy",
  );
  expect(header).toBeDefined();
  return header?.value ?? "";
}

describe("createSecurityHeaders", () => {
  it("allows React development debugging", () => {
    expect(contentSecurityPolicy("development")).toContain(
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    );
  });

  it.each(["production", "test", "unexpected", undefined])(
    "omits unsafe-eval outside development (%s)",
    (nodeEnvironment) => {
      expect(contentSecurityPolicy(nodeEnvironment)).not.toContain(
        "'unsafe-eval'",
      );
    },
  );
});
