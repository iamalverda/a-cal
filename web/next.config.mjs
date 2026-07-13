/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.A_CAL_API_URL || 'http://127.0.0.1:8000'}/api/:path*`,
      },
      {
        source: '/health',
        destination: `${process.env.A_CAL_API_URL || 'http://127.0.0.1:8000'}/health`,
      },
    ];
  },
};

export default nextConfig;
