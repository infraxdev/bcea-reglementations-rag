import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export (HTML/JS/CSS in out/). The app is a thin client: its only backend
  // call is the client-side fetch in lib/api.ts, so no Node server is needed. web/Dockerfile
  // serves out/ with nginx on the EKS cluster (docs/aws-architecture.md §5).
  output: "export",
};

export default nextConfig;
