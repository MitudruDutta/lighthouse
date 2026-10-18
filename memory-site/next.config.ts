import type { NextConfig } from "next";

// Where the Memory API runs, when the site is built to serve it under its own address
// (on Vercel). The Docker build leaves it unset: there the API has its own port.
const api = process.env.MEMORY_API;

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    if (!api) return [];
    return ["/v1/:path*", "/mcp", "/mcp/:path*", "/docs", "/openapi.json"].map((source) => ({
      source,
      destination: `${api}${source}`,
    }));
  },
};
export default config;
