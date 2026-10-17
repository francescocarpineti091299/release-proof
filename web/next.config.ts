import type { NextConfig } from "next";

const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // gzip in Next buffers proxied text/event-stream responses (live run events). Caddy compresses in production.
  compress: false,
  async rewrites() {
    // In production Caddy routes /api/* to the API container (same origin).
    // In dev, or when API_ORIGIN is set at build time, proxy through Next.
    if (process.env.NODE_ENV !== "development" && !process.env.API_ORIGIN) return [];
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
};

export default nextConfig;
