"use client";

import { ArrowUpRight, Pause, Play } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { feature } from "topojson-client";
import land from "world-atlas/land-110m.json";
import type { Topology } from "topojson-specification";

import type { Live, World } from "../lib/api";

const R = 10; // the globe's radius, in scene units
const REGIONS: Record<string, [number, number]> = {
  World: [10, 25],
  Europe: [12, 50],
  Asia: [112, 25],
  Americas: [-80, 15],
  Africa: [20, 0],
};

type Hover = { key: string; name: string; country: string | null; calls: number | null; now: number; x: number; y: number };

/** A point on the globe for a latitude and longitude, matching three's sphere texture. */
function at(lat: number, lon: number, radius: number) {
  const phi = ((90 - lat) * Math.PI) / 180;
  const theta = ((lon + 180) * Math.PI) / 180;
  return [-radius * Math.sin(phi) * Math.cos(theta), radius * Math.cos(phi), radius * Math.sin(phi) * Math.sin(theta)];
}

function token(name: string, fallback: string) {
  const value = getComputedStyle(document.querySelector(".console") ?? document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** The land of the world drawn on a canvas, for the globe's surface. */
function surface(width: number, height: number) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const pen = canvas.getContext("2d")!;
  pen.fillStyle = token("--chart-sea", "#e4f0f7");
  pen.fillRect(0, 0, width, height);
  pen.strokeStyle = token("--chart-grid", "#c9dbe9");
  pen.lineWidth = 1;
  for (let lon = -180; lon <= 180; lon += 30) {
    const px = ((lon + 180) / 360) * width;
    pen.beginPath();
    pen.moveTo(px, 0);
    pen.lineTo(px, height);
    pen.stroke();
  }
  for (let lat = -60; lat <= 60; lat += 30) {
    const py = ((90 - lat) / 180) * height;
    pen.beginPath();
    pen.moveTo(0, py);
    pen.lineTo(width, py);
    pen.stroke();
  }
  const topology = land as unknown as Topology;
  const shape = feature(topology, topology.objects.land) as unknown as GeoJSON.FeatureCollection;
  pen.fillStyle = document.documentElement.dataset.theme === "dark" ? "#1f3a35" : "#d1ded0";
  for (const item of shape.features) {
    const geometry = item.geometry as GeoJSON.MultiPolygon | GeoJSON.Polygon;
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
    for (const polygon of polygons) {
      pen.beginPath();
      for (const ring of polygon) {
        let before: number | null = null;
        ring.forEach(([lon, lat], n) => {
          const px = ((lon + 180) / 360) * width;
          const py = ((90 - lat) / 180) * height;
          // A ring that crosses the date line starts again on the other side.
          if (n === 0 || (before !== null && Math.abs(lon - before) > 180)) pen.moveTo(px, py);
          else pen.lineTo(px, py);
          before = lon;
        });
        pen.closePath();
      }
      pen.fill("evenodd");
    }
  }
  return canvas;
}

/** The world's ports on a globe that turns, with cargo ships moored where live AIS
 * positions show ships in port now. Without WebGL, `fallback` is shown instead. */
export function PortGlobe({ world, live, fallback }: { world: World; live: Live | null; fallback: React.ReactNode }) {
  const router = useRouter();
  const host = useRef<HTMLDivElement>(null);
  const controls = useRef({ paused: false, focus: "World", stamp: 0 });
  const [hover, setHover] = useState<Hover | null>(null);
  const [paused, setPaused] = useState(false);
  const [focus, setFocus] = useState("World");
  const [unavailable, setUnavailable] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    Promise.all([import("three"), import("three/examples/jsm/utils/BufferGeometryUtils.js")])
      .then(([T, { mergeGeometries }]) => {
        const element = host.current;
        if (!element || disposed) return;
        let renderer: InstanceType<typeof T.WebGLRenderer>;
        try {
          renderer = new T.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
        } catch {
          setUnavailable(true);
          return;
        }
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
        renderer.outputColorSpace = T.SRGBColorSpace;
        element.appendChild(renderer.domElement);
        renderer.domElement.setAttribute("aria-hidden", "true");
        const scene = new T.Scene();
        const camera = new T.PerspectiveCamera(32, 1, 0.1, 200);
        let distance = 36;
        camera.position.set(0, 0, distance);
        scene.add(new T.HemisphereLight(0xffffff, 0x6f8f88, 2.6));
        const sun = new T.DirectionalLight(0xfff5dd, 1.5);
        sun.position.set(-20, 18, 30);
        scene.add(sun);

        const globe = new T.Group();
        scene.add(globe);
        const disposables: { dispose: () => void }[] = [];

        // The earth and a thin halo.
        const texture = new T.CanvasTexture(surface(2048, 1024));
        texture.colorSpace = T.SRGBColorSpace;
        texture.anisotropy = 4;
        const earthMaterial = new T.MeshStandardMaterial({ map: texture, roughness: 0.95, metalness: 0 });
        const earthGeometry = new T.SphereGeometry(R, 96, 64);
        const earth = new T.Mesh(earthGeometry, earthMaterial);
        globe.add(earth);
        const haloGeometry = new T.SphereGeometry(R * 1.035, 64, 48);
        const haloMaterial = new T.MeshBasicMaterial({ color: token("--sky", "#397c76"), transparent: true, opacity: 0.07, side: T.BackSide });
        scene.add(new T.Mesh(haloGeometry, haloMaterial));
        disposables.push(texture, earthMaterial, earthGeometry, haloGeometry, haloMaterial);

        // Ports: one instanced dot each, sized by the day's port calls.
        const ports = world.ports.filter((port) => Number.isFinite(port[4]) && Number.isFinite(port[5]));
        const dotGeometry = new T.SphereGeometry(1, 10, 8);
        const dotMaterial = new T.MeshBasicMaterial({ color: 0xffffff });
        const dots = new T.InstancedMesh(dotGeometry, dotMaterial, ports.length);
        const usual = new T.Color(token("--sky", "#397c76"));
        const unusual = new T.Color(token("--coral", "#b14b26"));
        const matrix = new T.Matrix4();
        const place = new T.Vector3();
        // A port with ships in port now shows its ships instead of a dot.
        const shipped = new Set(Object.entries(live?.ports ?? {}).filter(([, c]) => c.now > 0).map(([key]) => key));
        const sizes = ports.map(([key, , , , , , calls]) => (shipped.has(key) ? 0 : 0.045 + Math.sqrt(calls ?? 0) * 0.012));
        const spots = ports.map(([, , , , lat, lon]) => at(lat, lon, R + 0.03) as [number, number, number]);
        // Dots keep about the same size on screen at any zoom.
        const scaleDots = (zoom: number) => {
          sizes.forEach((base, n) => {
            const size = base * zoom;
            matrix.makeScale(size, size, size).setPosition(place.set(...spots[n]));
            dots.setMatrixAt(n, matrix);
          });
          dots.instanceMatrix.needsUpdate = true;
          dots.computeBoundingSphere();
        };
        scaleDots(1);
        ports.forEach((port, n) => dots.setColorAt(n, port[0] in world.unusual ? unusual : usual));
        globe.add(dots);
        disposables.push(dotGeometry, dotMaterial);

        // A cargo ship: hull, containers, bridge, and funnel, as one coloured shape.
        const part = (geometry: InstanceType<typeof T.BufferGeometry>, color: string) => {
          const flat = geometry.index ? geometry.toNonIndexed() : geometry;
          flat.deleteAttribute("uv");
          const tint = new T.Color(color);
          const colors = new Float32Array(flat.attributes.position.count * 3);
          for (let i = 0; i < colors.length; i += 3) colors.set([tint.r, tint.g, tint.b], i);
          flat.setAttribute("color", new T.BufferAttribute(colors, 3));
          return flat;
        };
        const outline = new T.Shape();
        outline.moveTo(-0.5, -0.11);
        outline.lineTo(0.32, -0.11);
        outline.quadraticCurveTo(0.56, 0, 0.32, 0.11);
        outline.lineTo(-0.5, 0.11);
        outline.lineTo(-0.5, -0.11);
        const hull = new T.ExtrudeGeometry(outline, { depth: 0.09, bevelEnabled: false });
        hull.rotateX(-Math.PI / 2); // lie flat: length along x, beam along z, height along y
        const pieces = [part(hull, "#7a2e1d")];
        const deckColors = ["#c9573a", "#2f6f8f", "#e3b04b", "#3f8a5c", "#8a5fb0", "#c9573a"];
        deckColors.forEach((color, n) => {
          const box = new T.BoxGeometry(0.1, 0.07, 0.17);
          box.translate(-0.3 + n * 0.11, 0.125, 0);
          pieces.push(part(box, color));
        });
        const bridge = new T.BoxGeometry(0.1, 0.16, 0.18);
        bridge.translate(-0.43, 0.17, 0);
        pieces.push(part(bridge, "#f2efe6"));
        const funnel = new T.CylinderGeometry(0.025, 0.03, 0.08, 8);
        funnel.translate(-0.43, 0.29, 0);
        pieces.push(part(funnel, "#2b2b2b"));
        const shipGeometry = mergeGeometries(pieces as Parameters<typeof mergeGeometries>[0])!;
        shipGeometry.computeVertexNormals();
        [hull, ...pieces].forEach((geometry) => geometry.dispose());

        // One ship at each port with ships in port now, two at the busiest; bigger for more.
        type Vector = InstanceType<typeof T.Vector3>;
        const moored: { key: string; at: Vector; heading: Vector; normal: Vector; side: Vector; size: number; phase: number }[] = [];
        const byKey = new Map(ports.map((port) => [port[0], port]));
        for (const [key, counts] of Object.entries(live?.ports ?? {})) {
          const port = byKey.get(key);
          if (!port || counts.now <= 0) continue;
          const [, , , , lat, lon] = port;
          const ships = counts.now >= 50 ? 2 : 1;
          const size = 0.32 + Math.min(1, Math.sqrt(counts.now) / 18) * 0.22;
          const normal = new T.Vector3(...(at(lat, lon, 1) as [number, number, number])).normalize();
          const east = new T.Vector3(0, 1, 0).cross(normal).normalize();
          const north = normal.clone().cross(east).normalize();
          let seed = 0;
          for (const char of key) seed = (seed * 31 + char.charCodeAt(0)) % 997;
          for (let s = 0; s < ships; s++) {
            const angle = (seed / 997) * Math.PI * 2 + s * 2.1;
            const offset = east.clone().multiplyScalar(Math.cos(angle) * 0.18 * s).add(north.clone().multiplyScalar(Math.sin(angle) * 0.18 * s));
            const position = normal.clone().multiplyScalar(R + 0.05).add(offset);
            const heading = east.clone().multiplyScalar(Math.cos(angle + 1.2)).add(north.clone().multiplyScalar(Math.sin(angle + 1.2)));
            const side = normal.clone().cross(heading).normalize().negate();
            moored.push({ key, at: position, heading, normal, side, size, phase: seed + s });
          }
        }
        const shipMaterial = new T.MeshStandardMaterial({ vertexColors: true, roughness: 0.6, metalness: 0.1 });
        const fleet = new T.InstancedMesh(shipGeometry, shipMaterial, Math.max(moored.length, 1));
        fleet.count = moored.length;
        globe.add(fleet);
        disposables.push(shipGeometry, shipMaterial);

        // Turning, dragging, zooming, and pointing.
        const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
        const target = { lon: REGIONS.World[0], lat: REGIONS.World[1] };
        const view = { lon: target.lon, lat: target.lat };
        let dragging: { x: number; y: number; lon: number; lat: number } | null = null;
        let moved = false;
        const pointer = new T.Vector2();
        const ray = new T.Raycaster();
        const aim = () => {
          // The globe turns so that `view` faces the camera.
          globe.rotation.set((view.lat * Math.PI) / 180, (-(view.lon + 90) * Math.PI) / 180, 0, "XYZ");
        };
        const pick = (event: PointerEvent) => {
          const rect = renderer.domElement.getBoundingClientRect();
          pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
          const key = picked();
          const port = key ? byKey.get(key) : null;
          if (!port) return setHover(null);
          setHover({
            key: port[0],
            name: port[1] ?? port[0],
            country: port[3],
            calls: port[6],
            now: live?.ports[port[0]]?.now ?? 0,
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
          });
        };
        // The port or ship under the pointer, on the side of the globe that faces us.
        const picked = () => {
          ray.setFromCamera(pointer, camera);
          const ground = ray.intersectObject(earth)[0]?.distance ?? Infinity;
          const near = (hits: { distance: number }[]) => hits.find((hit) => hit.distance < ground + 0.3);
          const ship = near(ray.intersectObject(fleet)) as { instanceId?: number } | undefined;
          if (ship) return moored[ship.instanceId ?? 0]?.key ?? null;
          const dot = near(ray.intersectObject(dots)) as { instanceId?: number } | undefined;
          return dot ? (ports[dot.instanceId ?? 0]?.[0] ?? null) : null;
        };
        const down = (event: PointerEvent) => {
          dragging = { x: event.clientX, y: event.clientY, lon: view.lon, lat: view.lat };
          moved = false;
          renderer.domElement.setPointerCapture(event.pointerId);
        };
        const move = (event: PointerEvent) => {
          if (dragging) {
            const dx = event.clientX - dragging.x;
            const dy = event.clientY - dragging.y;
            if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
            view.lon = target.lon = dragging.lon - dx * 0.25;
            view.lat = target.lat = Math.max(-70, Math.min(75, dragging.lat + dy * 0.25));
          } else pick(event);
        };
        const up = (event: PointerEvent) => {
          dragging = null;
          if (!moved) {
            const rect = renderer.domElement.getBoundingClientRect();
            pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
            const key = picked();
            if (key) router.push(`/ports/${encodeURIComponent(key)}`);
          }
        };
        const wheel = (event: WheelEvent) => {
          event.preventDefault();
          distance = Math.max(18, Math.min(52, distance + event.deltaY * 0.02));
        };
        const leave = () => setHover(null);
        renderer.domElement.addEventListener("pointerdown", down);
        renderer.domElement.addEventListener("pointermove", move);
        renderer.domElement.addEventListener("pointerup", up);
        renderer.domElement.addEventListener("pointerleave", leave);
        renderer.domElement.addEventListener("wheel", wheel, { passive: false });

        const resize = new ResizeObserver(() => {
          const { width, height } = element.getBoundingClientRect();
          renderer.setSize(width, height, false);
          camera.aspect = width / Math.max(height, 1);
          camera.updateProjectionMatrix();
        });
        resize.observe(element);

        // A change of theme redraws the surface and recolours the ports and the halo.
        const paint = () => {
          texture.image = surface(2048, 1024);
          texture.needsUpdate = true;
          haloMaterial.color.set(token("--sky", "#397c76"));
          usual.set(token("--sky", "#397c76"));
          unusual.set(token("--coral", "#b14b26"));
          ports.forEach((port, n) => dots.setColorAt(n, port[0] in world.unusual ? unusual : usual));
          if (dots.instanceColor) dots.instanceColor.needsUpdate = true;
        };
        const theme = new MutationObserver(() => requestAnimationFrame(paint));
        theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

        let frame = 0;
        let dotZoom = 1;
        let stamp = controls.current.stamp;
        const pose = new T.Matrix4();
        const scale = new T.Vector3();
        const spot = new T.Vector3();
        const render = (time: number) => {
          if (controls.current.stamp !== stamp) {
            stamp = controls.current.stamp;
            [target.lon, target.lat] = REGIONS[controls.current.focus];
          }
          if (!dragging && !controls.current.paused && !motion.matches) target.lon += 0.02;
          view.lon += (target.lon - view.lon) * 0.06;
          view.lat += (target.lat - view.lat) * 0.06;
          aim();
          camera.position.z += (distance - camera.position.z) * 0.12;
          // Dots keep their size on screen; ships grow a little as you zoom in, and bob on the water.
          const zoom = (camera.position.z - R) / (36 - R);
          if (Math.abs(zoom - dotZoom) > 0.01) scaleDots((dotZoom = zoom));
          const still = motion.matches || controls.current.paused;
          moored.forEach((ship, n) => {
            const lift = still ? 0 : Math.sin(time / 700 + ship.phase) * 0.012 * ship.size;
            const size = ship.size * zoom ** 0.6;
            spot.copy(ship.normal).multiplyScalar(lift).add(ship.at);
            pose.makeBasis(ship.heading, ship.normal, ship.side).scale(scale.set(size, size, size)).setPosition(spot);
            fleet.setMatrixAt(n, pose);
          });
          fleet.instanceMatrix.needsUpdate = true;
          renderer.render(scene, camera);
          frame = requestAnimationFrame(render);
        };
        aim();
        frame = requestAnimationFrame(render);
        setReady(true);

        cleanup = () => {
          cancelAnimationFrame(frame);
          resize.disconnect();
          theme.disconnect();
          renderer.domElement.removeEventListener("pointerdown", down);
          renderer.domElement.removeEventListener("pointermove", move);
          renderer.domElement.removeEventListener("pointerup", up);
          renderer.domElement.removeEventListener("pointerleave", leave);
          renderer.domElement.removeEventListener("wheel", wheel);
          dots.dispose();
          fleet.dispose();
          disposables.forEach((item) => item.dispose());
          renderer.dispose();
          renderer.forceContextLoss();
          renderer.domElement.remove();
        };
      })
      .catch(() => {
        if (!disposed) setUnavailable(true);
      });
    return () => {
      disposed = true;
      cleanup();
    };
  }, [world, live, router]);

  if (unavailable) return <>{fallback}</>;
  const liveCount = Object.values(live?.ports ?? {}).filter((port) => port.now > 0).length;
  return (
    <div className="port-globe">
      <div className="port-globe-bar">
        <div className="port-globe-regions" role="group" aria-label="Turn the globe to">
          {Object.keys(REGIONS).map((name) => (
            <button
              key={name}
              type="button"
              aria-pressed={focus === name}
              onClick={() => {
                setFocus(name);
                controls.current.focus = name;
                controls.current.stamp += 1;
              }}
            >
              {name}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="port-globe-pause"
          aria-label={paused ? "Turn the globe" : "Stop the globe turning"}
          onClick={() => {
            controls.current.paused = !paused;
            setPaused(!paused);
          }}
        >
          {paused ? <Play size={14} /> : <Pause size={14} />}
        </button>
      </div>
      <div className="port-globe-stage" ref={host} data-ready={ready || undefined}>
        {!ready ? <p className="port-globe-loading">Drawing the globe…</p> : null}
        {hover ? (
          <div className="port-globe-tip" style={{ left: hover.x, top: hover.y }} role="status">
            <strong>{hover.name}</strong>
            <span>{hover.country}</span>
            <span>
              {hover.now ? `${hover.now} cargo ships & tankers in port now · ` : ""}
              {hover.calls ?? "—"} port calls a day
            </span>
          </div>
        ) : null}
        <div className="port-globe-legend" aria-hidden>
          <span>
            <i className="dot" /> Port, by daily calls
          </span>
          <span>
            <i className="dot unusual" /> Unusual day
          </span>
          {liveCount ? (
            <span>
              <i className="ship" /> Ships in port now, live
            </span>
          ) : null}
        </div>
      </div>
      <p className="port-globe-note">
        Drag to turn, scroll to zoom, select a port to open it. Daily calls from IMF PortWatch
        {world.newest_day ? ` (${world.newest_day})` : ""}
        {liveCount ? `; ships in port now from live AIS at ${liveCount} ports.` : "."}
        {" "}
        <Link href="/sources" className="link">
          Sources <ArrowUpRight size={11} aria-hidden />
        </Link>
      </p>
    </div>
  );
}
