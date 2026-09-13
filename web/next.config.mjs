/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloudflare Pages: a fully static export needs no adapter, no edge-runtime
  // annotations and no wrangler. All data access happens in the browser against
  // Supabase, and anything that must stay secret (birthdates) lives behind a
  // SECURITY DEFINER Postgres function rather than in a Node server.
  output: 'export',
  images: { unoptimized: true },
  trailingSlash: true,
  reactStrictMode: true,
};

export default nextConfig;
