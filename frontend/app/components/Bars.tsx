import type { Day } from "../lib/api";

/** Port calls by day, as bars; the tallest bar is the busiest day of the range. */
export function Bars({ days }: { days: Day[] }) {
  const most = Math.max(1, ...days.map((d) => d.calls ?? 0));
  const width = 720;
  const height = 160;
  const step = width / Math.max(days.length, 1);
  return (
    <svg viewBox={`0 0 ${width} ${height + 20}`} className="bars" role="img" aria-label="Port calls by day">
      {days.map((d, i) => {
        const h = ((d.calls ?? 0) / most) * height;
        return (
          <g key={d.day}>
            <rect x={i * step + 1} y={height - h} width={Math.max(step - 2, 1)} height={h} className="bar">
              <title>{`${d.day}: ${d.calls ?? 0} port calls`}</title>
            </rect>
            {i % Math.ceil(days.length / 6) === 0 ? (
              <text x={i * step} y={height + 14} className="bar-label">
                {d.day.slice(5)}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}
