"use client";

import Link from "next/link";

/** A link home that, on the landing page already, goes back to the top and drops any #section. */
export function HomeLink({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <Link
      href="/"
      className={className}
      onClick={(event) => {
        if (window.location.pathname !== "/") return;
        event.preventDefault();
        history.replaceState(history.state, "", "/");
        window.scrollTo({ top: 0 });
      }}
    >
      {children}
    </Link>
  );
}
