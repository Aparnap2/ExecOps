import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/generative_ui/:path*",
        destination: "http://localhost:8000/generative_ui/:path*",
      },
      {
        source: "/api/canvas/:path*",
        destination: "http://localhost:8000/api/canvas/:path*",
      },
    ];
  },
};

export default nextConfig;
