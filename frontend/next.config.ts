import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // Next 16 blocks dev HMR/hydration from non-localhost origins; allow the
  // 127.0.0.1 spelling used by the API and Playwright when localhost is not.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
