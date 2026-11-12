import type { NextConfig } from "next";

// Static export for GitHub Pages. The site is served under /<repo>/, so assets and links need
// that prefix; set NEXT_PUBLIC_BASE_PATH="" for local `next dev` at the root.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "/ramp-accessibility-agent";

const config: NextConfig = {
  output: "export",
  basePath,
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default config;
