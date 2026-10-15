import type { MDXComponents } from "mdx/types";
import Link from "next/link";
import { CodeBlock } from "./components/code-block";

const components: MDXComponents = {
  pre: CodeBlock,
  a: ({ href = "", ...props }) =>
    href.startsWith("/") || href.startsWith("#") ? (
      <Link href={href} className="link" {...props} />
    ) : (
      <a
        href={href}
        className="link"
        target="_blank"
        rel="noreferrer"
        {...props}
      />
    ),
  table: (props) => (
    <div className="table-wrap">
      <table {...props} />
    </div>
  ),
};
export function useMDXComponents(): MDXComponents {
  return components;
}
