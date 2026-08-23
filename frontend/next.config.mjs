/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    const backend =
      process.env.API_PROXY_TARGET ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://localhost:8000";

    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
