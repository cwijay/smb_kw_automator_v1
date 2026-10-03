import type { NextConfig } from "next";

// Same-origin API: the browser only ever talks to this app; /api/* is proxied to the FastAPI backend.
// No CORS, and the session cookie stays first-party.
const API = process.env.KEEL_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
