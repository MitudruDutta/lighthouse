/** The mark of Lighthouse: a light, and the beam it sends over the sea. */
export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="logo-beam" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#ddf78a" stopOpacity="0.9" />
          <stop offset="1" stopColor="#ddf78a" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="#22433b" stroke="#527064" />
      <path d="M13 11 L30 5 L30 17 Z" fill="url(#logo-beam)" />
      <path d="M11 25 L12.4 12 H15.6 L17 25 Z" fill="#e8eef7" />
      <rect x="11.6" y="8.6" width="4.8" height="3.6" rx="1" fill="#ddf78a" />
      <path d="M7 25.5 H21" stroke="#8fbaa5" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
