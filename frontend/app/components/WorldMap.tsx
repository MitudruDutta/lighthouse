"use client";

import { ArrowUpRight, Minus, Plus, RotateCcw, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { feature } from "topojson-client";
import land from "world-atlas/land-110m.json";
import type { Topology } from "topojson-specification";

import type { World, WorldPort } from "../lib/api";


// Latitudes with ports: the polar seas are left out.
const TOP = 80;
const BOTTOM = -60;
const W = 1000;
const H = Math.round((W * (TOP - BOTTOM)) / 360);
const x = (lon: number) => ((lon + 180) / 360) * W;
const y = (lat: number) => ((TOP - lat) / (TOP - BOTTOM)) * H;
/** The land of the world as one SVG path, made once. A ring that crosses the date line
 * starts a new piece there, so no line runs across the map. */
const LAND = (() => {
  const topology = land as unknown as Topology;
  const shape = feature(topology, topology.objects.land) as unknown as GeoJSON.FeatureCollection;
  const parts: string[] = [];
  for (const item of shape.features) {
    const geometry = item.geometry as GeoJSON.MultiPolygon | GeoJSON.Polygon;
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
    for (const polygon of polygons) {
      for (const ring of polygon) {
        let path = "";
        let before: number | null = null;
        for (const [lon, lat] of ring) {
          const jump = before !== null && Math.abs(lon - before) > 180;
          path += `${path === "" || jump ? "M" : "L"}${x(lon).toFixed(1)} ${y(lat).toFixed(1)}`;
          before = lon;
        }
        parts.push(`${path}Z`);
      }
    }
  }
  return parts.join("");
})();

const REGIONS: Record<string, [number, number, number]> = {
  World: [0, 10, 1], Europe: [16, 51, 3.5], Asia: [106, 28, 2.3], Americas: [-85, 20, 2], Africa: [20, 0, 2.5],
};

/** Explore real port activity; source dates remain visible independently of poll times. */
export function WorldMap({ world }: { world: World; beam?: boolean }) {
  const [region, setRegion] = useState("World");
  const [zoom, setZoom] = useState(1);
  const [onlyUnusual, setOnlyUnusual] = useState(false);
  const [selected, setSelected] = useState<WorldPort | null>(null);
  const ports = [...world.ports].sort((a, b) => (b[6] ?? 0) - (a[6] ?? 0));
  const shown = onlyUnusual ? ports.filter(([key]) => key in world.unusual) : ports;
  const [lon, lat, baseZoom] = REGIONS[region];
  const scale = baseZoom * zoom;
  const width = W / scale;
  const height = H / scale;
  const left = Math.max(0, Math.min(W - width, x(lon) - width / 2));
  const top = Math.max(0, Math.min(H - height, y(lat) - height / 2));
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <select aria-label="Map region" value={region} className="!py-1.5 !text-xs" onChange={(event) => { setRegion(event.target.value); setZoom(1); setSelected(null); }}>
            {Object.keys(REGIONS).map((name) => <option key={name}>{name}</option>)}
          </select>
          <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-muted"><input type="checkbox" checked={onlyUnusual} onChange={(event) => { setOnlyUnusual(event.target.checked); setSelected(null); }} />Unusual only</label>
        </div>
        <div className="map-controls">
          <button type="button" aria-label="Zoom out" disabled={zoom <= 1} onClick={() => setZoom((z) => Math.max(1, z / 1.5))}><Minus size={14} aria-hidden /></button>
          <span className="w-8 text-center text-[10px] tabular">{scale.toFixed(1)}×</span>
          <button type="button" aria-label="Zoom in" disabled={zoom >= 3.375} onClick={() => setZoom((z) => Math.min(3.375, z * 1.5))}><Plus size={14} aria-hidden /></button>
          <button type="button" aria-label="Reset map" onClick={() => { setRegion("World"); setZoom(1); setSelected(null); setOnlyUnusual(false); }}><RotateCcw size={13} aria-hidden /></button>
        </div>
      </div>
      <div className="relative overflow-hidden rounded-lg border" style={{ borderColor: "var(--edge)", background: "var(--chart-sea)" }}>
        <svg viewBox={`${left} ${top} ${width} ${height}`} className="map" role="group" aria-label={`Port activity map: ${shown.length} ports. Select a port for details.`}>
          <g className="map-grid">
            {Array.from({ length: 11 }, (_, n) => <line key={`x${n}`} x1={x(-150 + n * 30)} x2={x(-150 + n * 30)} y1={0} y2={H} strokeWidth={0.5 / scale} />)}
            {[-30, 0, 30, 60].map((lat) => <line key={lat} x1={0} x2={W} y1={y(lat)} y2={y(lat)} strokeWidth={0.5 / scale} />)}
          </g>
          <path d={LAND} className="map-land" strokeWidth={0.5 / scale} />
          {shown.map((port) => {
            const [key, name, , country, lat, lon, calls] = port;
            const unusual = key in world.unusual;
            const radius = (1.2 + Math.sqrt(calls ?? 0) * 0.32) / Math.sqrt(scale);
            return (
              <a key={key} href={`/ports/${encodeURIComponent(key)}`} aria-label={`${name ?? key}, ${country ?? ""}: ${calls === null ? "no daily count" : `${calls} port calls`}${unusual ? ", unusual activity" : ""}`} onClick={(event) => { event.preventDefault(); setSelected(port); }}>
                <title>{`${name ?? key} · ${calls ?? "—"} port calls${unusual ? " · Unusual" : ""}`}</title>
                {unusual ? <circle cx={x(lon)} cy={y(lat)} r={radius + 2.2 / scale} fill="none" stroke="var(--coral)" strokeOpacity={0.5} strokeWidth={1 / scale} /> : null}
                <circle cx={x(lon)} cy={y(lat)} r={radius} className={`${unusual ? "map-light" : "map-port"} ${selected?.[0] === key ? "selected-port" : ""}`} />
              </a>
            );
          })}
        </svg>
        {!shown.length ? <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-muted">{world.ports.length ? "No unusual ports in the current data." : "Port activity appears after the first import."}</div> : null}
        <span className="pointer-events-none absolute right-3 bottom-2 rounded px-1.5 py-1 text-[9px] tracking-wide text-faint" style={{ background: "var(--chart-sea)" }}>IMF PORTWATCH / {world.newest_day ?? "AWAITING DATA"}</span>
      </div>
      {selected ? (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border p-3" style={{ borderColor: "var(--edge)", background: "var(--rule-soft)" }} aria-live="polite">
          <div className="min-w-0"><p className="truncate text-sm font-semibold">{selected[1] ?? selected[0]}</p><p className="text-xs text-muted">{selected[3]} · {selected[6] ?? "—"} port calls{selected[0] in world.unusual ? " · Unusual activity" : ""}</p></div>
          <Link href={`/ports/${encodeURIComponent(selected[0])}`} className="link flex shrink-0 items-center gap-1 text-xs font-medium">Port details<ArrowUpRight size={13} aria-hidden /></Link>
          <button type="button" onClick={() => setSelected(null)} aria-label="Close selected port" className="!bg-transparent !p-1 !text-[var(--ink-2)]"><X size={15} aria-hidden /></button>
        </div>
      ) : null}
    </div>
  );
}
