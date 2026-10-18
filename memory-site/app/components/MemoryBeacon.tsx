"use client";

import { useEffect, useRef, useState } from "react";
import { Mark } from "./Brand";
import type { BufferGeometry } from "three";

/** A small, lazy-loaded Three.js scene. Text and controls stay in accessible HTML. */
export function MemoryBeacon({
  paused,
  mode,
}: {
  paused: boolean;
  mode: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const settings = useRef({ paused, mode });
  const wake = useRef(() => {});
  const [ready, setReady] = useState(false);

  useEffect(() => {
    settings.current = { paused, mode };
    wake.current();
  }, [paused, mode]);

  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    void import("three")
      .then((T) => {
        const element = host.current;
        if (!element || disposed) return;
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("webgl2", {
          alpha: true,
          antialias: true,
          powerPreference: "low-power",
        });
        if (!context) return;
        let renderer: InstanceType<typeof T.WebGLRenderer>;
        try {
          renderer = new T.WebGLRenderer({
            canvas,
            context,
            antialias: true,
            alpha: true,
          });
        } catch {
          return;
        }
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
        renderer.outputColorSpace = T.SRGBColorSpace;
        renderer.toneMapping = T.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.35;
        canvas.setAttribute("aria-hidden", "true");
        element.appendChild(canvas);
        const scene = new T.Scene();
        const camera = new T.OrthographicCamera(-5, 5, 4, -4, 0.1, 80);
        const world = new T.Group();
        scene.add(world);
        world.position.y = -0.5;
        scene.add(new T.HemisphereLight(0xffe7c8, 0x392333, 2.7));
        const key = new T.DirectionalLight(0xffe3b3, 4);
        key.position.set(-4, 7, 5);
        scene.add(key);
        const rim = new T.DirectionalLight(0xdc7850, 3);
        rim.position.set(5, 3, -5);
        scene.add(rim);
        const materials = new Map<
          string,
          InstanceType<typeof T.MeshStandardMaterial>
        >();
        function material(color: string, metalness = 0.25) {
          if (!materials.has(color))
            materials.set(
              color,
              new T.MeshStandardMaterial({ color, roughness: 0.4, metalness }),
            );
          return materials.get(color)!;
        }
        function mesh(
          geometry: BufferGeometry,
          color: string,
          parent = world,
        ) {
          const shape = new T.Mesh(geometry, material(color));
          parent.add(shape);
          return shape;
        }
        function disc(
          radius: number,
          height: number,
          y: number,
          color: string,
          segments = 6,
        ) {
          const shape = mesh(
            new T.CylinderGeometry(radius, radius, height, segments),
            color,
          );
          shape.position.y = y;
          shape.rotation.y = Math.PI / 6;
          const edges = new T.LineSegments(
            new T.EdgesGeometry(shape.geometry),
            new T.LineBasicMaterial({
              color: 0xf0b788,
              transparent: true,
              opacity: 0.4,
            }),
          );
          shape.add(edges);
          return shape;
        }
        const core = new T.Group();
        world.add(core);
        const plates = [
          disc(1.32, 0.13, -0.3, "#62414a"),
          disc(1.18, 0.13, -0.04, "#9b6450"),
          disc(1.04, 0.13, 0.22, "#d69b70"),
        ];
        const tower = new T.Group();
        core.add(tower);
        const body = mesh(
          new T.CylinderGeometry(0.23, 0.43, 1.4, 8),
          "#f4d7b0",
          tower,
        );
        body.position.y = 1.02;
        const band = mesh(
          new T.CylinderGeometry(0.326, 0.357, 0.2, 8),
          "#af4e2d",
          tower,
        );
        band.position.y = 0.92;
        const foot = mesh(
          new T.CylinderGeometry(0.49, 0.52, 0.13, 8),
          "#f6dab2",
          tower,
        );
        foot.position.y = 0.35;
        for (const y of [0.63, 1.25]) {
          const window = mesh(
            new T.BoxGeometry(0.12, 0.18, 0.08),
            "#432c35",
            tower,
          );
          window.position.set(0, y, 0.3);
        }
        const lantern = new T.Mesh(
          new T.CylinderGeometry(0.31, 0.31, 0.34, 12),
          new T.MeshStandardMaterial({
            color: 0xffdf9e,
            emissive: 0xffab4d,
            emissiveIntensity: 1.3,
            roughness: 0.2,
          }),
        );
        lantern.position.y = 1.88;
        tower.add(lantern);
        for (const y of [1.69, 2.07]) {
          const ring = mesh(
            new T.CylinderGeometry(0.4, 0.4, 0.07, 12),
            "#c47c50",
            tower,
          );
          ring.position.y = y;
        }
        for (let i = 0; i < 8; i++) {
          const angle = (i * Math.PI) / 4;
          const bar = mesh(
            new T.CylinderGeometry(0.017, 0.017, 0.32, 5),
            "#664135",
            tower,
          );
          bar.position.set(
            Math.cos(angle) * 0.31,
            1.88,
            Math.sin(angle) * 0.31,
          );
        }
        const roof = mesh(new T.ConeGeometry(0.48, 0.3, 8), "#c66940", tower);
        roof.position.y = 2.25;
        const tip = mesh(new T.SphereGeometry(0.06, 10, 8), "#ffe0a6", tower);
        tip.position.y = 2.44;
        const lamp = new T.PointLight(0xffb45d, 5, 8);
        lamp.position.set(0, 1.88, 0);
        tower.add(lamp);
        // Light beams: soft cones from the lamp, brightest at the lamp and in the middle,
        // fading toward the far end and the edges.
        const beamMaterial = new T.ShaderMaterial({
          uniforms: { color: { value: new T.Color(0xffc27a) } },
          vertexShader: `varying float along; varying float facing;
            void main() {
              along = uv.y;
              vec4 view = modelViewMatrix * vec4(position, 1.0);
              vec3 toCamera = isOrthographic ? vec3(0.0, 0.0, 1.0) : normalize(-view.xyz);
              facing = abs(dot(normalize(normalMatrix * normal), toCamera));
              gl_Position = projectionMatrix * view;
            }`,
          fragmentShader: `uniform vec3 color; varying float along; varying float facing;
            void main() { gl_FragColor = vec4(color, pow(along, 1.4) * pow(facing, 2.0) * 0.5); }`,
          transparent: true,
          depthWrite: false,
          side: T.DoubleSide,
          blending: T.AdditiveBlending,
          toneMapped: false,
        });
        const beams = new T.Group();
        beams.position.y = 1.88;
        tower.add(beams);
        for (const direction of [1, -1]) {
          const beam = new T.Mesh(
            new T.ConeGeometry(0.62, 3.4, 32, 1, true),
            beamMaterial,
          );
          // The tip sits in the lamp; the cone opens outward.
          beam.rotation.z = (direction * Math.PI) / 2;
          beam.position.x = (direction * 3.4) / 2;
          beams.add(beam);
        }
        const halo = document.createElement("canvas");
        halo.width = halo.height = 64;
        const paint = halo.getContext("2d")!;
        const gradient = paint.createRadialGradient(32, 32, 0, 32, 32, 32);
        gradient.addColorStop(0, "rgba(255,226,170,1)");
        gradient.addColorStop(0.35, "rgba(255,178,96,0.45)");
        gradient.addColorStop(1, "rgba(255,150,70,0)");
        paint.fillStyle = gradient;
        paint.fillRect(0, 0, 64, 64);
        const glowTexture = new T.CanvasTexture(halo);
        const glow = new T.Sprite(
          new T.SpriteMaterial({
            map: glowTexture,
            blending: T.AdditiveBlending,
            depthWrite: false,
            transparent: true,
            toneMapped: false,
          }),
        );
        glow.scale.setScalar(1.7);
        glow.position.y = 1.88;
        tower.add(glow);
        // A soft shadow grounds the base.
        const shade = document.createElement("canvas");
        shade.width = shade.height = 64;
        const shadePaint = shade.getContext("2d")!;
        const shadow = shadePaint.createRadialGradient(32, 32, 0, 32, 32, 32);
        shadow.addColorStop(0, "rgba(20,10,18,0.55)");
        shadow.addColorStop(1, "rgba(20,10,18,0)");
        shadePaint.fillStyle = shadow;
        shadePaint.fillRect(0, 0, 64, 64);
        const shadowTexture = new T.CanvasTexture(shade);
        const ground = new T.Mesh(
          new T.PlaneGeometry(3.6, 3.6),
          new T.MeshBasicMaterial({
            map: shadowTexture,
            transparent: true,
            depthWrite: false,
            toneMapped: false,
          }),
        );
        ground.rotation.x = -Math.PI / 2;
        ground.position.y = -0.42;
        world.add(ground);
        const orbits: InstanceType<typeof T.Mesh>[] = [];
        for (let i = 0; i < 3; i++) {
          const ring = new T.Mesh(
            new T.TorusGeometry(2.05 + i * 0.55, 0.012, 6, 96),
            new T.MeshBasicMaterial({
              color: i === 1 ? 0xf6ba83 : 0x9e6c58,
              transparent: true,
              opacity: i === 1 ? 0.65 : 0.4,
            }),
          );
          ring.rotation.set(Math.PI / 2 + i * 0.17, 0.12 * i, 0.3 * i);
          ring.position.y = 0.15 + i * 0.18;
          world.add(ring);
          orbits.push(ring);
        }
        const dots: InstanceType<typeof T.Mesh>[] = [];
        const dotGeometry = new T.SphereGeometry(0.045, 10, 8);
        const dotMaterial = new T.MeshBasicMaterial({ color: 0xffd2a0 });
        for (let i = 0; i < 16; i++) {
          const dot = new T.Mesh(dotGeometry, dotMaterial);
          world.add(dot);
          dots.push(dot);
        }
        const satellites: InstanceType<typeof T.Group>[] = [];
        for (let i = 0; i < 3; i++) {
          const group = new T.Group();
          world.add(group);
          satellites.push(group);
          for (let layer = 0; layer < 3; layer++) {
            const plate = mesh(
              new T.BoxGeometry(0.5, 0.065, 0.38),
              layer === 2 ? "#ebc39a" : "#8a5950",
              group,
            );
            plate.position.y = layer * 0.12;
            const edge = new T.LineSegments(
              new T.EdgesGeometry(plate.geometry),
              new T.LineBasicMaterial({
                color: 0xf8c692,
                transparent: true,
                opacity: 0.4,
              }),
            );
            plate.add(edge);
          }
        }
        const positions = new Float32Array(18);
        const connections = new T.BufferGeometry();
        connections.setAttribute(
          "position",
          new T.BufferAttribute(positions, 3),
        );
        world.add(
          new T.LineSegments(
            connections,
            new T.LineBasicMaterial({
              color: 0xf5b681,
              transparent: true,
              opacity: 0.23,
            }),
          ),
        );
        const media = matchMedia("(prefers-reduced-motion: reduce)");
        let frame = 0,
          elapsed = 0,
          last = performance.now(),
          visible = true,
          first = true;
        let pointerX = 0,
          pointerY = 0;
        function pose() {
          const accent = [0xffac68, 0xffd79a, 0xdca6a4][settings.current.mode];
          lamp.color.setHex(accent);
          dotMaterial.color.setHex(accent);
          core.position.y = Math.sin(elapsed * 0.8) * 0.07;
          tower.rotation.y = -0.1 + Math.sin(elapsed * 0.3) * 0.15;
          plates.forEach((plate, i) => {
            plate.position.y =
              -0.3 + i * 0.26 + Math.sin(elapsed * 0.8 + i * 0.5) * 0.035;
            plate.rotation.y =
              Math.PI / 6 + Math.sin(elapsed * 0.3 + i * 0.4) * 0.07;
          });
          beams.rotation.y = elapsed * 0.65;
          orbits.forEach((ring, i) => {
            ring.rotation.z = 0.3 * i + elapsed * (0.04 + i * 0.015);
          });
          dots.forEach((dot, i) => {
            const angle =
              elapsed * (0.15 + (i % 3) * 0.06) + (i * Math.PI * 2) / 16;
            const radius = 2.05 + (i % 3) * 0.55;
            dot.position.set(
              Math.cos(angle) * radius,
              0.15 + (i % 3) * 0.18 + Math.sin(angle) * 0.28,
              Math.sin(angle) * radius,
            );
          });
          satellites.forEach((satellite, i) => {
            const angle = elapsed * 0.1 + (i * Math.PI * 2) / 3 + 0.4;
            satellite.position.set(
              Math.cos(angle) * 2.8,
              0.45 + Math.sin(elapsed * 0.7 + i) * 0.16,
              Math.sin(angle) * 2.8,
            );
            satellite.rotation.y = -angle;
            positions.set(
              [
                0,
                0.6,
                0,
                satellite.position.x,
                satellite.position.y,
                satellite.position.z,
              ],
              i * 6,
            );
          });
          connections.attributes.position.needsUpdate = true;
          camera.position.set(6.3 + pointerX * 0.6, 4.9 + pointerY * 0.35, 8.5);
          camera.lookAt(0, 0.65, 0);
        }
        function draw(at: number) {
          frame = 0;
          if (disposed) return;
          const running =
            !settings.current.paused &&
            !media.matches &&
            visible &&
            !document.hidden;
          if (running) elapsed += Math.min((at - last) / 1000, 0.06);
          last = at;
          pose();
          renderer.render(scene, camera);
          if (first) {
            first = false;
            setReady(true);
          }
          if (running) frame = requestAnimationFrame(draw);
        }
        function resume() {
          if (!disposed && !frame) {
            last = performance.now();
            frame = requestAnimationFrame(draw);
          }
        }
        wake.current = resume;
        const resize = new ResizeObserver(() => {
          const width = element.clientWidth,
            height = element.clientHeight;
          if (!width || !height) return;
          renderer.setSize(width, height, false);
          // A narrow frame zooms out so the orbits stay in view.
          const halfHeight = 3 * Math.max(1, 1.6 / (width / height));
          camera.left = (-halfHeight * width) / height;
          camera.right = -camera.left;
          camera.top = halfHeight;
          camera.bottom = -halfHeight;
          camera.updateProjectionMatrix();
          resume();
        });
        resize.observe(element);
        const observer = new IntersectionObserver(
          ([entry]) => {
            visible = entry.isIntersecting;
            if (visible) resume();
          },
          { rootMargin: "80px" },
        );
        observer.observe(element);
        const stage = element.parentElement;
        function move(event: PointerEvent) {
          const bounds = element!.getBoundingClientRect();
          pointerX = (event.clientX - bounds.left) / bounds.width - 0.5;
          pointerY = (event.clientY - bounds.top) / bounds.height - 0.5;
        }
        function leave() {
          pointerX = 0;
          pointerY = 0;
        }
        function lost(event: Event) {
          event.preventDefault();
          if (frame) cancelAnimationFrame(frame);
          frame = 0;
          setReady(false);
        }
        function restored() {
          first = true;
          resume();
        }
        stage?.addEventListener("pointermove", move);
        stage?.addEventListener("pointerleave", leave);
        canvas.addEventListener("webglcontextlost", lost);
        canvas.addEventListener("webglcontextrestored", restored);
        media.addEventListener("change", resume);
        document.addEventListener("visibilitychange", resume);
        resume();
        cleanup = () => {
          if (frame) cancelAnimationFrame(frame);
          wake.current = () => {};
          resize.disconnect();
          observer.disconnect();
          stage?.removeEventListener("pointermove", move);
          stage?.removeEventListener("pointerleave", leave);
          media.removeEventListener("change", resume);
          document.removeEventListener("visibilitychange", resume);
          canvas.removeEventListener("webglcontextlost", lost);
          canvas.removeEventListener("webglcontextrestored", restored);
          const geometries = new Set<InstanceType<typeof T.BufferGeometry>>();
          const surfaces = new Set<InstanceType<typeof T.Material>>();
          scene.traverse((object) => {
            if (
              object instanceof T.Mesh ||
              object instanceof T.Line ||
              object instanceof T.LineSegments
            ) {
              geometries.add(object.geometry);
              for (const surface of Array.isArray(object.material)
                ? object.material
                : [object.material])
                surfaces.add(surface);
            }
          });
          geometries.forEach((geometry) => geometry.dispose());
          surfaces.forEach((surface) => surface.dispose());
          glowTexture.dispose();
          glow.material.dispose();
          shadowTexture.dispose();
          renderer.dispose();
          canvas.remove();
        };
      })
      .catch(() => {
        /* The illustration remains usable if graphics cannot load. */
      });
    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  return (
    <div
      ref={host}
      className="beacon-scene"
      data-ready={ready}
      role="img"
      aria-label="Animated 3D lighthouse with versioned memory layers, orbiting evidence, and a rotating signal"
    >
      <div className="beacon-fallback" aria-hidden>
        <div className="fallback-halo" />
        <div className="fallback-platform">
          <Mark size={74} />
          <i />
          <i />
          <i />
        </div>
      </div>
    </div>
  );
}
