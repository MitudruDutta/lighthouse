import createMDX from "@next/mdx";
import type { NextConfig } from "next";

const config: NextConfig = {
  pageExtensions: ["ts", "tsx", "mdx"],
  turbopack: { rules: { "*.css": { loaders: ["@tailwindcss/turbopack"], as: "*.css" } } },
};

export default createMDX({ options: { remarkPlugins: ["remark-gfm"], rehypePlugins: ["rehype-slug"] } })(config);
