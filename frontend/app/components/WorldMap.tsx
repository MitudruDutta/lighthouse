import type { World } from "../lib/api";

// Latitudes with ports: the polar seas are left out.
const TOP = 80;
const BOTTOM = -60;
const W = 1000;
const H = Math.round((W * (TOP - BOTTOM)) / 360);

/** Ports of the world on a plain map: longitude across, latitude up. Each dot is a port,
 * as large as its port calls on the last day; ports that are unusual now are marked. The
 * ports themselves draw the coasts. */
export function WorldMap({ world }: { world: World }) {
  const x = (lon: number) => ((lon + 180) / 360) * W;
  const y = (lat: number) => ((TOP - lat) / (TOP - BOTTOM)) * H;
  const lines = [];
  for (let lon = -150; lon <= 150; lon += 30) lines.push(<line key={`m${lon}`} x1={x(lon)} x2={x(lon)} y1={0} y2={H} />);
  for (let lat = -30; lat <= 60; lat += 30) lines.push(<line key={`p${lat}`} x1={0} x2={W} y1={y(lat)} y2={y(lat)} />);
  const ports = [...world.ports].sort((a, b) => (b[6] ?? 0) - (a[6] ?? 0));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="map" role="img" aria-label="Ports of the world by port calls">
      <rect width={W} height={H} className="map-sea" />
      <g className="map-grid">{lines}</g>
      {ports.map(([key, name, , country, lat, lon, calls]) => {
        const unusual = key in world.unusual;
        const r = 1.2 + Math.sqrt(calls ?? 0) * 0.55;
        return (
          <a key={key} href={`/ports/${encodeURIComponent(key)}`}>
            <circle cx={x(lon)} cy={y(lat)} r={unusual ? Math.max(r, 4) : r} className={unusual ? "map-unusual" : "map-port"}>
              <title>{`${name ?? key}, ${country ?? ""}: ${calls ?? 0} port calls${unusual ? " (unusual)" : ""}`}</title>
            </circle>
          </a>
        );
      })}
    </svg>
  );
}
