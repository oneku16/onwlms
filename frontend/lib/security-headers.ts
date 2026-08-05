export interface SecurityHeader {
  readonly key: string;
  readonly value: string;
}

export function createSecurityHeaders(
  nodeEnvironment: string | undefined,
): SecurityHeader[] {
  const scriptSources = ["'self'", "'unsafe-inline'"];
  if (nodeEnvironment === "development") {
    scriptSources.push("'unsafe-eval'");
  }

  return [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    {
      key: "Permissions-Policy",
      value: "camera=(), microphone=(), geolocation=(), payment=()",
    },
    {
      key: "Content-Security-Policy",
      value: [
        "default-src 'self'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "img-src 'self' data: https:",
        "font-src 'self' data:",
        `script-src ${scriptSources.join(" ")}`,
        "style-src 'self' 'unsafe-inline'",
        "connect-src 'self'",
        "object-src 'none'",
      ].join("; "),
    },
  ];
}
