/** Static export: the site is plain HTML/CSS/JS, so it can be hosted free (Vercel, Netlify, GitHub Pages). */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};
export default nextConfig;
