"use client";

import { Globe2, Map } from "lucide-react";
import { useState } from "react";

import type { Live, World } from "../lib/api";
import { PortGlobe } from "./PortGlobe";
import { WorldMap } from "./WorldMap";

/** The ports of the world as a globe with live ships, or as the flat map. */
export function PortMaps({ world, live }: { world: World; live: Live | null }) {
  const [view, setView] = useState<"globe" | "flat">("globe");
  const flat = <WorldMap world={world} />;
  return (
    <section className="card port-maps">
      <header className="card-heading mb-3">
        <h2 className="text-[15px] font-semibold">Port activity around the world</h2>
        <div className="port-maps-switch" role="tablist" aria-label="Map view">
          <button type="button" role="tab" aria-selected={view === "globe"} onClick={() => setView("globe")}>
            <Globe2 size={14} aria-hidden /> Globe
          </button>
          <button type="button" role="tab" aria-selected={view === "flat"} onClick={() => setView("flat")}>
            <Map size={14} aria-hidden /> Flat map
          </button>
        </div>
      </header>
      {view === "globe" ? <PortGlobe world={world} live={live} fallback={flat} /> : flat}
    </section>
  );
}
