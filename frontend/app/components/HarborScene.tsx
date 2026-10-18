"use client";

import { Compass, MoveUpRight, Pause, Play, RotateCcw, Route, Ship } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function HarborScene() {
  const host = useRef<HTMLDivElement>(null);
  const controls = useRef({ paused: false, routes: true, view: "harbor", reset: 0 });
  const [ready, setReady] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [paused, setPaused] = useState(false);
  const [routes, setRoutes] = useState(true);
  const [view, setView] = useState("harbor");

  useEffect(() => {
    let disposed = false;
    let cleanup = () => {};
    void import("three").then((T) => {
      const element = host.current;
      if (!element || disposed) return;
      let renderer: InstanceType<typeof T.WebGLRenderer>;
      try {
        renderer = new T.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
      } catch {
        setUnavailable(true);
        return; // The illustrated fallback remains visible without WebGL.
      }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = T.PCFShadowMap;
      renderer.outputColorSpace = T.SRGBColorSpace;
      renderer.toneMapping = T.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.15;
      element.appendChild(renderer.domElement);
      renderer.domElement.setAttribute("aria-hidden", "true");
      renderer.domElement.dataset.scene = "harbor";
      const scene = new T.Scene();
      const world = new T.Group();
      scene.add(world);
      const camera = new T.PerspectiveCamera(36, 1, .1, 120);
      camera.position.set(20, 23, 28);
      camera.lookAt(0, 0, 0);
      scene.add(new T.HemisphereLight(0xe5ffe5, 0x123b36, 2.1));
      const sun = new T.DirectionalLight(0xfff3cb, 3.2);
      sun.position.set(-8, 22, 10);
      sun.castShadow = true;
      sun.shadow.mapSize.set(1024, 1024);
      Object.assign(sun.shadow.camera, { left: -20, right: 20, top: 20, bottom: -20, near: 1, far: 65 });
      sun.shadow.normalBias = .06;
      scene.add(sun);
      const rim = new T.DirectionalLight(0xa9edd1, 2.4);
      rim.position.set(16, 10, -12);
      scene.add(rim);
      const materials = new Map<string, InstanceType<typeof T.MeshStandardMaterial>>();
      function material(color: string) {
        if (!materials.has(color)) materials.set(color, new T.MeshStandardMaterial({ color, roughness: .72, metalness: .04 }));
        return materials.get(color)!;
      }
      function box(parent: InstanceType<typeof T.Group>, size: number[], at: number[], color: string) {
        const mesh = new T.Mesh(new T.BoxGeometry(...size as [number, number, number]), material(color));
        mesh.position.set(...at as [number, number, number]);
        mesh.castShadow = true; mesh.receiveShadow = true;
        parent.add(mesh);
        return mesh;
      }
      function cylinder(parent: InstanceType<typeof T.Group>, top: number, bottom: number, height: number, at: number[], color: string) {
        const mesh = new T.Mesh(new T.CylinderGeometry(top, bottom, height, 12), material(color));
        mesh.position.set(...at as [number, number, number]); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh);
        return mesh;
      }
      function line(parent: InstanceType<typeof T.Group>, points: number[][], color: string, opacity = 1) {
        const geometry = new T.BufferGeometry().setFromPoints(points.map((p) => new T.Vector3(...p as [number, number, number])));
        const shape = new T.Line(geometry, new T.LineBasicMaterial({ color, transparent: true, opacity }));
        parent.add(shape); return shape;
      }
      const waterMaterial = new T.ShaderMaterial({
        transparent: true, depthWrite: false,
        uniforms: { time: { value: 0 } },
        vertexShader: `varying vec2 vUv; uniform float time; void main(){ vUv=uv; vec3 p=position; p.z+=sin(p.x*.9+time*.6)*.045+cos(p.y*1.2+time*.4)*.035; gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.); }`,
        fragmentShader: `varying vec2 vUv; uniform float time; void main(){ float d=length(vUv-.5); float wave=sin(vUv.x*160.+time*.5+sin(vUv.y*70.+time*.3)*2.); float grain=pow(max(0.,wave),18.)*.055; vec3 base=mix(vec3(.025,.17,.17),vec3(.10,.34,.29),(1.-smoothstep(0.,.6,d))); gl_FragColor=vec4(base+grain,(1.-smoothstep(.38,.5,d))*.95); }`,
      });
      const water = new T.Mesh(new T.CircleGeometry(19, 96), waterMaterial);
      water.rotation.x = -Math.PI / 2; water.position.y = -.04; world.add(water);
      // An L-shaped working harbor: docks, container yards, cranes and a beacon.
      box(world, [5.2, .65, 17], [-8, -.2, -2], "#728d7c");
      box(world, [17, .65, 4.2], [2.6, -.2, -8.4], "#728d7c");
      box(world, [.16, .14, 16.7], [-5.35, .2, -2], "#e2e6c9");
      box(world, [16.8, .14, .16], [2.6, .2, -6.25], "#e2e6c9");
      for (let i = 0; i < 9; i++) {
        cylinder(world, .1, .1, .28, [-5.1, .2, -9 + i * 1.8], "#e2d7a4");
        line(world, [[-10.3, .15, -9 + i * 1.8], [-5.5, .15, -9 + i * 1.8]], "#b9c9ac", .4);
      }
      const palette = ["#d7ee8c", "#b2cbb5", "#c98665", "#e7d5a8", "#458878"];
      function container(parent: InstanceType<typeof T.Group>, x: number, y: number, z: number, color: string, scale = 1) {
        const mesh = box(parent, [.82 * scale, .62 * scale, 1.45 * scale], [x, y, z], color);
        const edges = new T.LineSegments(new T.EdgesGeometry(mesh.geometry), new T.LineBasicMaterial({ color: "#173f35", transparent: true, opacity: .25 }));
        mesh.add(edges);
        for (let rib = 0; rib < 4; rib++) box(parent, [.025 * scale, .56 * scale, .035 * scale], [x - .3 * scale + rib * .2 * scale, y, z + .733 * scale], color);
      }
      for (let row = 0; row < 3; row++) for (let col = 0; col < 4; col++) {
        container(world, -9 + row, .67, -6.4 + col * 1.65, palette[(row + col) % palette.length]);
        if ((row + col) % 3 !== 0) container(world, -9 + row, 1.31, -6.4 + col * 1.65, palette[(row + col + 1) % palette.length]);
      }
      box(world, [4.3, 1.4, 2.2], [7, .8, -8.5], "#b8c8ad");
      box(world, [4.5, .16, 2.4], [7, 1.56, -8.5], "#d8dec2");
      for (let i = 0; i < 4; i++) box(world, [.7, .6, .04], [5.5 + i, .65, -7.36], "#365d50");
      function crane(z: number) {
        const crane = new T.Group(); crane.position.set(-6.7, .2, z); world.add(crane);
        for (const x of [-1.1, 1.1]) for (const depth of [-.6, .6]) box(crane, [.14, 4.8, .14], [x, 2.4, depth], "#d4e58b");
        for (const depth of [-.6, .6]) {
          box(crane, [6.3, .2, .16], [1.15, 4.8, depth], "#d4e58b");
          line(crane, [[-1.1, .1, depth], [1.1, 4.7, depth], [-1.1, 4.7, depth], [1.1, .1, depth]], "#b4cb79");
          line(crane, [[-1.1, 4.8, depth], [.2, 6.1, depth], [4.3, 4.8, depth]], "#d4e58b");
          line(crane, [[3.1, 4.7, depth], [3.1, 2.1, depth]], "#e6edd5");
        }
        box(crane, [.7, .55, 1.3], [2.9, 4.4, 0], "#e3ebc0");
        box(crane, [.6, .08, 1.2], [3.1, 2.05, 0], "#d4e58b");
      }
      crane(-3); crane(-7.1);
      const beacon = new T.Group(); beacon.position.set(-9, .15, 4.5); world.add(beacon);
      cylinder(beacon, .8, .9, .3, [0, .15, 0], "#d4ddbe");
      cylinder(beacon, .42, .62, 3.5, [0, 1.9, 0], "#e5e5ca");
      cylinder(beacon, .6, .6, .2, [0, 3.7, 0], "#274f40");
      const lantern = cylinder(beacon, .43, .43, .6, [0, 4.05, 0], "#dff58f");
      lantern.material = new T.MeshStandardMaterial({ color: "#ddf78a", emissive: "#b7e26d", emissiveIntensity: .6 });
      const roof = new T.Mesh(new T.ConeGeometry(.65, .6, 12), material("#315a48")); roof.position.y = 4.65; beacon.add(roof);
      const beamMaterial = new T.MeshBasicMaterial({ color: "#e4f7a4", transparent: true, opacity: .055, side: T.DoubleSide, depthWrite: false });
      const beam = new T.Mesh(new T.ConeGeometry(3.5, 15, 32, 1, true), beamMaterial);
      beam.rotation.z = Math.PI / 2; beam.position.set(7.5, 4.05, 0); beacon.add(beam);
      function ship(color: string) {
        const ship = new T.Group();
        const hull = new T.Shape();
        hull.moveTo(0, -4.8); hull.quadraticCurveTo(1.25, -3.8, 1.25, -2.6); hull.lineTo(1.25, 3.6); hull.lineTo(-1.25, 3.6); hull.lineTo(-1.25, -2.6); hull.quadraticCurveTo(-1.25, -3.8, 0, -4.8);
        const body = new T.Mesh(new T.ExtrudeGeometry(hull, { depth: .7, bevelEnabled: true, bevelSize: .1, bevelThickness: .1, bevelSegments: 2, steps: 1 }), material(color));
        body.rotation.x = -Math.PI / 2; body.position.y = .08; body.castShadow = true; ship.add(body);
        box(ship, [2.3, .15, 6.8], [0, .83, .1], "#dfdfc2");
        box(ship, [1.95, 1.15, 1.25], [0, 1.48, 2.45], "#eae9ce");
        box(ship, [2.15, .13, 1.45], [0, 2.1, 2.45], "#eeeed5");
        for (let i = 0; i < 5; i++) box(ship, [.27, .28, .035], [-.73 + i * .36, 1.78, 1.8], "#234e48");
        box(ship, [.36, .9, .36], [.47, 2.55, 2.5], "#c98b62");
        cylinder(ship, .035, .035, 1.5, [-.6, 2.75, 2.65], "#e8e6c8");
        for (let row = 0; row < 2; row++) for (let col = 0; col < 3; col++) for (let stack = 0; stack < 2; stack++) container(ship, -.48 + row * .96, 1.22 + stack * .65, -2.6 + col * 1.5, palette[(col + row * 2 + stack) % palette.length]);
        for (const side of [-1, 1]) line(ship, [[side * 1.16, 1.04, -2.9], [side * 1.16, 1.04, 3.4]], "#eeefdb", .7);
        const wake = new T.Group();
        for (const side of [-1, 1]) for (let i = 0; i < 3; i++) line(wake, [[side * 1.05, .04, 3.5 + i * .4], [side * 1.6, .04, 5 + i * .5], [side * 2.3, .04, 7 + i * .5]], "#b1dace", .28 - i * .06);
        ship.add(wake); world.add(ship); return ship;
      }
      const vessel = ship("#264d43"); vessel.position.set(1, .06, 4); vessel.rotation.y = -.57;
      const docked = ship("#a9654e"); docked.scale.setScalar(.55); docked.position.set(3.2, .03, -4.9); docked.rotation.y = Math.PI / 2;
      const routesGroup = new T.Group(); world.add(routesGroup);
      const routeCurve = new T.CatmullRomCurve3([new T.Vector3(10, .12, 11), new T.Vector3(5, .12, 4), new T.Vector3(5.5, .12, -.5), new T.Vector3(1, .12, -5.5)]);
      const routeLine = new T.Line(new T.BufferGeometry().setFromPoints(routeCurve.getPoints(80)), new T.LineDashedMaterial({ color: "#d4ee8a", dashSize: .2, gapSize: .18, transparent: true, opacity: .65 }));
      routeLine.computeLineDistances(); routesGroup.add(routeLine);
      const signal = new T.Mesh(new T.SphereGeometry(.09, 10, 10), new T.MeshBasicMaterial({ color: "#e3ff9f" })); routesGroup.add(signal);
      const ring = new T.Mesh(new T.RingGeometry(1.25, 1.27, 64), new T.MeshBasicMaterial({ color: "#d9ee99", transparent: true, opacity: .2, side: T.DoubleSide })); ring.rotation.x = -Math.PI / 2; ring.position.set(1, .15, 4); world.add(ring);
      let visible = true;
      let frame = 0;
      let last = 0;
      let rendered = false;
      let elapsed = 0;
      let reset = 0;
      const pointer = { x: 0, y: 0 };
      const cameraTarget = new T.Vector3();
      const cameraFocus = new T.Vector3();
      const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
      const move = (event: PointerEvent) => {
        if (event.pointerType === "touch") return;
        const rect = element.getBoundingClientRect();
        pointer.x = ((event.clientX - rect.left) / rect.width - .5) * 2;
        pointer.y = ((event.clientY - rect.top) / rect.height - .5) * 2;
      };
      const leave = () => { pointer.x = 0; pointer.y = 0; };
      element.addEventListener("pointermove", move); element.addEventListener("pointerleave", leave);
      const resize = new ResizeObserver(() => {
        const width = element.clientWidth; const height = element.clientHeight;
        if (!width || !height) return;
        renderer.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix();
      }); resize.observe(element);
      const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }, { rootMargin: "100px" }); intersection.observe(element);
      function render(time: number) {
        frame = requestAnimationFrame(render);
        if (!visible || document.hidden || time - last < 32) return;
        const delta = Math.min((time - last) / 1000, .05); last = time;
        const moving = !controls.current.paused && !motion.matches;
        if (moving) elapsed += delta;
        waterMaterial.uniforms.time.value = elapsed;
        vessel.position.y = .06 + Math.sin(elapsed * .9) * .055;
        vessel.rotation.z = Math.sin(elapsed * .7) * .012;
        docked.position.y = .03 + Math.sin(elapsed * .7 + 1) * .035;
        beam.rotation.y = elapsed * .14;
        signal.position.copy(routeCurve.getPoint((elapsed * .045) % 1));
        routesGroup.visible = controls.current.routes;
        if (reset !== controls.current.reset) { pointer.x = 0; pointer.y = 0; reset = controls.current.reset; }
        const close = controls.current.view === "vessel";
        const focus = cameraFocus.set(close ? 1 : 0, 0, close ? 3 : 0);
        // A narrow frame pulls the camera back so the whole harbour stays in view.
        const fit = Math.max(1, 1.3 / camera.aspect);
        const target = cameraTarget.set(close ? 11 : 20, close ? 12 : 23, close ? 14 : 28).multiplyScalar(fit).add(focus);
        if (moving) { target.x += pointer.x * 2; target.y -= pointer.y * 1.3; }
        camera.position.lerp(target, .045);
        camera.lookAt(focus);
        renderer.render(scene, camera);
        if (!rendered) { rendered = true; setReady(true); }
      }
      frame = requestAnimationFrame(render);
      cleanup = () => {
        cancelAnimationFrame(frame); resize.disconnect(); intersection.disconnect();
        element.removeEventListener("pointermove", move); element.removeEventListener("pointerleave", leave);
        const geometries = new Set<InstanceType<typeof T.BufferGeometry>>();
        const allMaterials = new Set<InstanceType<typeof T.Material>>();
        scene.traverse((object) => {
          if ("geometry" in object) geometries.add((object as InstanceType<typeof T.Mesh>).geometry);
          if ("material" in object) {
            const material = (object as InstanceType<typeof T.Mesh>).material;
            for (const item of Array.isArray(material) ? material : [material]) allMaterials.add(item);
          }
        });
        geometries.forEach((geometry) => geometry.dispose()); allMaterials.forEach((material) => material.dispose());
        renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
      };
    }).catch(() => { if (!disposed) setUnavailable(true); });
    return () => { disposed = true; cleanup(); };
  }, []);

  return <figure className="harbor-scene" aria-label="Harbor illustration with container ships, cranes and a lighthouse">
    <div className="harbor-scene-top"><span><Compass size={13} aria-hidden />A connected world</span><span className="harbor-scene-label">{unavailable ? "Maritime illustration" : "Interactive illustration"}</span></div>
    <div ref={host} className="harbor-viewport" data-ready={ready}>
      {!ready ? <div className="harbor-fallback" aria-hidden><div className="fallback-rings" /><Ship size={130} strokeWidth={.7} /><span>Ships. Ports. Shared intelligence.</span></div> : null}
    </div>
    <div className="harbor-coordinate" aria-hidden>60° 09′ N<br />24° 57′ E</div>
    <div className="harbor-float harbor-float-one"><span className="harbor-float-icon"><Ship size={16} aria-hidden /></span><div><span>Connected operations</span><strong>One graph. Every relationship.</strong></div><MoveUpRight size={13} aria-hidden /></div>
    <div className="harbor-float harbor-float-two"><i /><span>Watch → investigate → remember</span></div>
    <figcaption className="harbor-scene-bottom"><span className="harbor-hint">{unavailable ? "Ships. Ports. Shared intelligence." : "Move your pointer to explore"}</span>{!unavailable ? <div className="harbor-controls">
      <button type="button" aria-label={view === "harbor" ? "Follow vessel" : "Show harbor"} aria-pressed={view === "vessel"} onClick={() => { const value = view === "harbor" ? "vessel" : "harbor"; setView(value); controls.current.view = value; }}><Ship size={15} aria-hidden /></button>
      <button type="button" aria-label="Show shipping route" aria-pressed={routes} onClick={() => { setRoutes(!routes); controls.current.routes = !routes; }}><Route size={15} aria-hidden /></button>
      <button type="button" aria-label={paused ? "Play harbor animation" : "Pause harbor animation"} onClick={() => { setPaused(!paused); controls.current.paused = !paused; }}>{paused ? <Play size={14} aria-hidden /> : <Pause size={14} aria-hidden />}</button>
      <button type="button" aria-label="Reset harbor view" onClick={() => { setView("harbor"); controls.current.view = "harbor"; controls.current.reset++; }}><RotateCcw size={14} aria-hidden /></button>
    </div> : null}</figcaption>
  </figure>;
}
