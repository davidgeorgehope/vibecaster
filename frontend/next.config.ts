import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // In development: proxy /api requests to backend
  // In production: nginx handles the proxying
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8001/api/:path*",
      },
    ];
  },
};

export default nextConfig;
