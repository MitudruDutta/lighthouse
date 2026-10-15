import type { Day } from "../lib/api";

// As the Port Watcher judges a day: against the median of up to 28 days before it, with at
// least 14 of them, at a port that usually has at least 6 port calls a day.
const BASELINE = 28;
const LEAST_DAYS = 14;
const MIN_USUAL = 6;

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** What was usual before each day, and whether the day was unusual, from the days given. */
export function judged(days: Day[]) {
  return days.map((d, i) => {
    const before = days.slice(Math.max(0, i - BASELINE), i).flatMap((b) => (b.calls == null ? [] : [b.calls]));
    const usual = before.length >= LEAST_DAYS ? median(before) : null;
    const calls = d.calls;
    const unusual = calls != null && usual !== null && usual >= MIN_USUAL && (calls <= usual / 2 || calls >= usual * 2);
    return { ...d, usual, unusual };
  });
}

/** Port calls by day, the last `shown` of `days`: one bar a day, the usual level as a
 * dashed line, unusual days in the colour of a light. Each bar names its day on hover. */
export function Bars({ days, shown = 60 }: { days: Day[]; shown?: number }) {
  const all = judged(days);
  const bars = all.slice(-shown);
  const W = 960;
  const H = 220;
  const top = 18;
  const bottom = 22;
  const left = 34;
  const plot = H - top - bottom;
  const most = Math.max(4, ...bars.map((d) => Math.max(d.calls ?? 0, d.usual ?? 0)));
  const ticks = [0, Math.round(most / 2), Math.round(most)];
  const step = (W - left) / Math.max(bars.length, 1);
  const y = (v: number) => top + plot - (v / most) * plot;
  const usualPath = bars
    .map((d, i) => (d.usual === null ? null : `${i === 0 || bars[i - 1].usual === null ? "M" : "L"}${left + i * step} ${y(d.usual)} H${left + (i + 1) * step}`))
    .filter(Boolean)
    .join(" ");
  const lastUsual = bars.at(-1)?.usual;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="bars" role="img" aria-label={`Port calls by day, the last ${bars.length} days`}>
      <g>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={left} x2={W} y1={y(t)} y2={y(t)} stroke="var(--rule-soft)" />
            <text x={left - 6} y={y(t) + 4} textAnchor="end" className="bar-label">
              {t}
            </text>
          </g>
        ))}
      </g>
      {bars.map((d, i) => {
        const v = d.calls ?? 0;
        const h = Math.max((v / most) * plot, v ? 2 : 0);
        const x = left + i * step + 1;
        const w = Math.max(step - 2, 1);
        const r = Math.min(4, w / 2, h);
        return (
          <g key={d.day} className="bar-group">
            <rect x={left + i * step} y={top} width={step} height={plot} fill="transparent" />
            <path
              d={`M${x} ${y(0)} V${y(0) - h + r} Q${x} ${y(0) - h} ${x + r} ${y(0) - h} H${x + w - r} Q${x + w} ${y(0) - h} ${x + w} ${y(0) - h + r} V${y(0)} Z`}
              className={d.unusual ? "bar bar-unusual" : "bar"}
            />
            <text x={Math.min(Math.max(x + w / 2, left + 50), W - 50)} y={top - 5} textAnchor="middle" className="bar-tip">
              {`${d.day}: ${d.calls == null ? "no observation" : `${v} port calls`}${d.usual !== null ? `, usual ${d.usual}` : ""}${d.unusual ? ", unusual" : ""}`}
            </text>
            {d.calls == null ? <circle cx={x + w / 2} cy={y(0) - 3} r={2} fill="none" stroke="var(--ink-3)" /> : null}
            {i % Math.ceil(bars.length / 8) === 0 ? (
              <text x={x} y={H - 6} className="bar-label">
                {d.day.slice(5)}
              </text>
            ) : null}
          </g>
        );
      })}
      {usualPath ? <path d={usualPath} fill="none" stroke="var(--ink)" strokeWidth={1.5} strokeDasharray="4 3" /> : null}
      {lastUsual != null ? (
        <text x={W - 2} y={y(lastUsual) - 6} textAnchor="end" className="bar-usual">
          usual {lastUsual}
        </text>
      ) : null}
    </svg>
  );
}
