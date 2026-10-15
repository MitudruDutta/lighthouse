import Link from "next/link";
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <path d="M13 12h6l3 17H10l3-17Z" fill="currentColor" />
      <path
        d="M12 7h8v5h-8zM11 7l5-4 5 4M3 5l6 3M29 5l-6 3M2 13h6M24 13h6"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M14 18h4M13 24h6"
        stroke="var(--mark-cut,#fff)"
        strokeWidth="2"
      />
    </svg>
  );
}
export function Brand() {
  return (
    <Link href="/" className="brand">
      <Mark />
      <span>
        Lighthouse<span className="brand-sub">Memory</span>
      </span>
    </Link>
  );
}
