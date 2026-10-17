import createMDX from "@next/mdx";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The image ships the server and the packages it uses, not every package.
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  async redirects() {
    return [{ source: "/docs/:path*", destination: `${process.env.NEXT_PUBLIC_LIGHTHOUSE_DOCS_URL ?? "http://localhost:3002"}/:path*`, permanent: false }];
  },
  // The documentation is written in MDX, as pages of its own.
  pageExtensions: ["ts", "tsx", "mdx"],
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

// Tables in the documentation (GitHub's markdown), and an id on each heading to link to.
const withMDX = createMDX({
  options: {
    remarkPlugins: ["remark-gfm"],
    rehypePlugins: ["rehype-slug"],
  },
});

export default withMDX(nextConfig);
