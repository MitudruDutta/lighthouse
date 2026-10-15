import type { MDXComponents } from "mdx/types";
import Link from "next/link";

// How the documentation's markdown looks: the type and colours of the rest of the site.
const components: MDXComponents = {
  h1: (props) => <h1 className="serif mb-3 text-4xl leading-tight" {...props} />,
  h2: (props) => <h2 className="serif mt-12 mb-3 scroll-mt-6 text-[26px] leading-snug" {...props} />,
  h3: (props) => <h3 className="mt-8 mb-2 scroll-mt-6 text-lg font-semibold" {...props} />,
  p: (props) => <p className="my-3 leading-relaxed" {...props} />,
  ul: (props) => <ul className="my-3 grid list-disc gap-1.5 pl-5 leading-relaxed marker:text-[var(--ink-3)]" {...props} />,
  ol: (props) => <ol className="my-3 grid list-decimal gap-1.5 pl-5 leading-relaxed marker:text-[var(--ink-3)]" {...props} />,
  a: ({ href = "", ...props }) =>
    href.startsWith("/") || href.startsWith("#") ? (
      <Link href={href} className="link underline decoration-[var(--rule)] underline-offset-3" {...props} />
    ) : (
      <a href={href} className="link underline decoration-[var(--rule)] underline-offset-3" target="_blank" rel="noreferrer" {...props} />
    ),
  blockquote: (props) => (
    <blockquote className="my-4 rounded-r border-l-2 px-4 py-2 text-[15px]" style={{ borderColor: "var(--light)", background: "var(--panel)" }} {...props} />
  ),
  table: (props) => (
    <div className="my-4 overflow-x-auto">
      <table className="grid" {...props} />
    </div>
  ),
  pre: (props) => (
    <pre className="my-4 overflow-x-auto rounded-md px-4 py-3 font-mono text-[13px] leading-relaxed" style={{ background: "var(--button)", color: "var(--button-ink)" }} {...props} />
  ),
  code: (props) => <code className="font-mono text-[0.9em]" {...props} />,
  hr: () => <hr className="my-10" style={{ borderColor: "var(--rule)" }} />,
};

export function useMDXComponents(): MDXComponents {
  return components;
}
