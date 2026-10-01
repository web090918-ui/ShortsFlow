import type { NextConfig } from "next";

// The browser calls the API through the same origin (/api/*) so the HttpOnly
// session cookie is first-party. API_PROXY_TARGET is the Cloud Run URL in
// production and the local FastAPI server in development.
const apiProxyTarget = (process.env.API_PROXY_TARGET ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiProxyTarget}/:path*` }];
  },
};

export default nextConfig;
