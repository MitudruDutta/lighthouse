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
  // A wide table scrolls in its frame: a keyboard reaches it through the frame itself.
  // No landmark: a page has several tables, and every landmark needs a name of its own.
  table: (props) => (
    <div className="table-wrap" tabIndex={0}>
      <table {...props} />
    </div>
  ),
};
export function useMDXComponents(): MDXComponents {
  return components;
}
