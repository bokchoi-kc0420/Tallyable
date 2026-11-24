/** Static export: the site is plain HTML/CSS/JS, hosted free on GitHub Pages (.github/workflows/pages.yml). */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  // GitHub Pages serves the site under /Tallyable/; local builds leave this empty.
  basePath: process.env.NEXT_BASE_PATH || "",
};
export default nextConfig;
