/** The mark of a light on a nautical chart: a magenta flare from the light's position. */
export function Flare({ size = 18, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="-2 -14 16 16" aria-hidden className={className}>
      <path d={FLARE} fill="var(--light)" />
      <circle cx="0" cy="0" r="1.6" fill="var(--ink)" />
    </svg>
  );
}

// A teardrop from (0, 0), leaning up and to the right, as charts draw a light.
export const FLARE = "M0 0 C1.5 -3.5 5 -8.5 8.5 -11 C10.8 -12.6 13.2 -10.3 11.7 -8 C9.6 -4.9 4.4 -1.7 0 0 Z";
