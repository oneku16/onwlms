import type { NextConfig } from "next";

import { createSecurityHeaders } from "./lib/security-headers";

const securityHeaders = createSecurityHeaders(process.env.NODE_ENV);

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // TypeScript 7 has no programmatic API. The build script first runs its native
  // CLI, then Next uses the official side-by-side TypeScript 6 compatibility API
  // for framework type generation.
  experimental: {
    useTypeScriptCli: false,
  },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
