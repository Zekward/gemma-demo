import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Pin the workspace root to this project so env files and module resolution
  // don't get pulled to a stray lockfile in the home directory.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
