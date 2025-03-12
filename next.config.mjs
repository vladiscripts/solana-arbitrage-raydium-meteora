/** @type {import('next').NextConfig} */
const nextConfig = {
    output: "export",
    productionBrowserSourceMaps: true,
    webpack: (config) => {
      config.resolve.fallback = {
        fs: false,
      };
      return config;
    },
    async rewrites() {
      return [
        {
          source: '/meteoras',         // Public URL path (visible to users)
          destination: '/pages/meteoras', // Internal Next.js path
        },
        // Add more rewrites here as needed
      ];
    },
};

export default nextConfig;
