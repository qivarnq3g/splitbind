import { useEffect, useRef } from "react";
import * as THREE from "three";

const RINGS = 30;
const SPOKES = 72;
const DISC_RADIUS = 2.85;
const INNER_RADIUS = 0.2;
const NODE_RING_STEP = 3;
const NODE_SPOKE_STEP = 4;

const surfaceChunk = `
uniform float uTime;
uniform float uAmp;

float lift(vec2 plane) {
  float radius = length(plane);
  float angle = atan(plane.y, plane.x);
  float envelope = smoothstep(0.0, 0.95, radius) * smoothstep(3.0, 1.35, radius);
  float ripple = sin(radius * 2.55 - uTime * 1.05);
  float harmonic = 0.46 * sin(radius * 4.8 - uTime * 0.68 + angle * 2.0);
  float drift = 0.3 * sin(angle * 3.0 + uTime * 0.34) * smoothstep(2.9, 0.9, radius);
  return (ripple + harmonic + drift) * 0.52 * envelope * uAmp;
}
`;

const gridVertex = `
${surfaceChunk}
uniform float uScale;

varying float vCrest;
varying float vRadius;

void main() {
  vec2 plane = position.xz;
  float height = lift(plane);
  vec4 viewed = modelViewMatrix * vec4(position.x, height, position.z, 1.0);

  vCrest = height / uAmp;
  vRadius = length(plane);

  gl_Position = projectionMatrix * viewed;
  gl_PointSize = (0.016 + max(vCrest, 0.0) * 0.05) * uScale / -viewed.z;
}
`;

const gridFragment = `
uniform vec3 uLow;
uniform vec3 uHigh;
uniform float uOpacity;

varying float vCrest;
varying float vRadius;

void main() {
  float crest = smoothstep(-0.2, 0.62, vCrest);
  float fade = smoothstep(3.0, 1.0, vRadius);
  gl_FragColor = vec4(mix(uLow, uHigh, crest), (0.12 + crest * 0.78) * uOpacity * fade);
}
`;

const nodeFragment = `
uniform vec3 uLow;
uniform vec3 uHigh;
uniform float uOpacity;

varying float vCrest;
varying float vRadius;

void main() {
  vec2 offset = gl_PointCoord - 0.5;
  float radius = length(offset) * 2.0;
  if (radius > 1.0) discard;
  float falloff = pow(1.0 - radius, 2.4);
  float crest = smoothstep(-0.05, 0.7, vCrest);
  float fade = smoothstep(3.0, 1.0, vRadius);
  gl_FragColor = vec4(mix(uLow, uHigh, crest), falloff * (0.2 + crest) * uOpacity * fade);
}
`;

const plateVertex = `
${surfaceChunk}
varying float vCrest;
varying float vRadius;

void main() {
  vec2 plane = position.xz;
  float height = lift(plane);
  vCrest = height / uAmp;
  vRadius = length(plane);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position.x, height, position.z, 1.0);
}
`;

const plateFragment = `
uniform vec3 uDeep;
uniform vec3 uShallow;

varying float vCrest;
varying float vRadius;

void main() {
  float crest = smoothstep(-0.55, 0.8, vCrest);
  float fade = smoothstep(3.0, 1.15, vRadius);
  gl_FragColor = vec4(mix(uDeep, uShallow, crest * crest), fade * (0.34 + crest * 0.66));
}
`;

type Lattice = {
  points: Float32Array;
  triangles: number[];
  lines: number[];
  nodes: Float32Array;
};

function buildLattice(): Lattice {
  const vertexCount = (RINGS + 1) * SPOKES + 1;
  const points = new Float32Array(vertexCount * 3);
  const span = DISC_RADIUS - INNER_RADIUS;

  for (let ring = 0; ring <= RINGS; ring += 1) {
    const radius = INNER_RADIUS + span * Math.pow(ring / RINGS, 1.04);
    for (let spoke = 0; spoke < SPOKES; spoke += 1) {
      const angle = (spoke / SPOKES) * Math.PI * 2;
      const slot = (ring * SPOKES + spoke) * 3;
      points[slot] = Math.cos(angle) * radius;
      points[slot + 1] = 0;
      points[slot + 2] = Math.sin(angle) * radius;
    }
  }
  const centre = (RINGS + 1) * SPOKES;
  points[centre * 3] = 0;
  points[centre * 3 + 1] = 0;
  points[centre * 3 + 2] = 0;

  const triangles: number[] = [];
  for (let ring = 0; ring < RINGS; ring += 1) {
    for (let spoke = 0; spoke < SPOKES; spoke += 1) {
      const next = (spoke + 1) % SPOKES;
      const a = ring * SPOKES + spoke;
      const b = ring * SPOKES + next;
      const c = (ring + 1) * SPOKES + spoke;
      const d = (ring + 1) * SPOKES + next;
      triangles.push(a, c, b, b, c, d);
    }
  }
  for (let spoke = 0; spoke < SPOKES; spoke += 1) {
    triangles.push(centre, spoke, (spoke + 1) % SPOKES);
  }

  const lines: number[] = [];
  for (let ring = 0; ring <= RINGS; ring += 1) {
    for (let spoke = 0; spoke < SPOKES; spoke += 1) {
      const next = (spoke + 1) % SPOKES;
      lines.push(ring * SPOKES + spoke, ring * SPOKES + next);
    }
  }
  for (let ring = 0; ring < RINGS; ring += 1) {
    for (let spoke = 0; spoke < SPOKES; spoke += 1) {
      lines.push(ring * SPOKES + spoke, (ring + 1) * SPOKES + spoke);
    }
  }

  const picked: number[] = [];
  for (let ring = 0; ring <= RINGS; ring += NODE_RING_STEP) {
    for (let spoke = 0; spoke < SPOKES; spoke += NODE_SPOKE_STEP) {
      const slot = (ring * SPOKES + spoke) * 3;
      picked.push(
        points[slot] ?? 0,
        points[slot + 1] ?? 0,
        points[slot + 2] ?? 0,
      );
    }
  }

  return { points, triangles, lines, nodes: new Float32Array(picked) };
}

export default function WaveletSurface() {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = host.current;
    if (!mount) return;

    const canvas = document.createElement("canvas");
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        canvas,
        alpha: true,
        antialias: true,
        powerPreference: "low-power",
      });
    } catch {
      return;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    mount.appendChild(canvas);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 60);
    camera.position.set(0, 3.7, 9.4);
    camera.lookAt(0, 0.02, 0);

    const group = new THREE.Group();
    scene.add(group);

    const lattice = buildLattice();
    const clock = { value: 0 };
    const amplitude = { value: 0.84 };
    const pointScale = { value: 300 };

    const plateGeometry = new THREE.BufferGeometry();
    plateGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(lattice.points.slice(), 3),
    );
    plateGeometry.setIndex(lattice.triangles);
    const plateMaterial = new THREE.ShaderMaterial({
      uniforms: {
        uTime: clock,
        uAmp: amplitude,
        uDeep: { value: new THREE.Color("#ccd8da") },
        uShallow: { value: new THREE.Color("#fbfdfd") },
      },
      vertexShader: plateVertex,
      fragmentShader: plateFragment,
      side: THREE.DoubleSide,
      transparent: true,
      depthWrite: true,
      polygonOffset: true,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    });
    const plate = new THREE.Mesh(plateGeometry, plateMaterial);
    group.add(plate);

    const gridGeometry = new THREE.BufferGeometry();
    gridGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(lattice.points.slice(), 3),
    );
    gridGeometry.setIndex(lattice.lines);
    const gridMaterial = new THREE.ShaderMaterial({
      uniforms: {
        uTime: clock,
        uAmp: amplitude,
        uScale: pointScale,
        uLow: { value: new THREE.Color("#a4b7bd") },
        uHigh: { value: new THREE.Color("#0d5566") },
        uOpacity: { value: 0.85 },
      },
      vertexShader: gridVertex,
      fragmentShader: gridFragment,
      transparent: true,
      depthWrite: false,
    });
    const grid = new THREE.LineSegments(gridGeometry, gridMaterial);
    group.add(grid);

    const nodeGeometry = new THREE.BufferGeometry();
    nodeGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(lattice.nodes, 3),
    );
    const nodeMaterial = new THREE.ShaderMaterial({
      uniforms: {
        uTime: clock,
        uAmp: amplitude,
        uScale: pointScale,
        uLow: { value: new THREE.Color("#8fa6ad") },
        uHigh: { value: new THREE.Color("#063f4e") },
        uOpacity: { value: 0.95 },
      },
      vertexShader: gridVertex,
      fragmentShader: nodeFragment,
      transparent: true,
      depthWrite: false,
    });
    const nodes = new THREE.Points(nodeGeometry, nodeMaterial);
    group.add(nodes);

    let tiltX = 0;
    let tiltY = 0;
    let leanX = 0;
    let leanY = 0;
    const onMove = (event: PointerEvent) => {
      const rect = mount.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      tiltY = (event.clientX - rect.left) / rect.width - 0.5;
      tiltX = (event.clientY - rect.top) / rect.height - 0.5;
    };

    const resize = () => {
      const rect = mount.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      renderer.setSize(rect.width, rect.height, false);
      camera.aspect = rect.width / rect.height;
      camera.updateProjectionMatrix();
      pointScale.value = renderer.domElement.height * 0.5;
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);
    window.addEventListener("pointermove", onMove, { passive: true });

    let raf = 0;
    let onScreen = false;
    let awake = true;
    const timer = new THREE.Timer();
    timer.connect(document);

    const tick = () => {
      timer.update();
      const dt = Math.min(timer.getDelta(), 0.05);
      clock.value = timer.getElapsed();

      leanX += (tiltX - leanX) * 0.05;
      leanY += (tiltY - leanY) * 0.05;

      group.rotation.y += dt * 0.13;
      group.rotation.x = leanX * 0.2;
      group.rotation.z = leanY * 0.12;

      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };

    const wake = () => {
      if (raf !== 0 || !onScreen || !awake) return;
      timer.reset();
      raf = requestAnimationFrame(tick);
    };
    const sleep = () => {
      if (raf === 0) return;
      cancelAnimationFrame(raf);
      raf = 0;
    };

    const viewport = new IntersectionObserver(
      (entries) => {
        onScreen = entries.some((entry) => entry.isIntersecting);
        if (onScreen) wake();
        else sleep();
      },
      { rootMargin: "160px" },
    );
    viewport.observe(mount);

    const onVisibility = () => {
      awake = !document.hidden;
      if (awake) wake();
      else sleep();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      sleep();
      viewport.disconnect();
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onMove);
      timer.dispose();
      plateGeometry.dispose();
      plateMaterial.dispose();
      gridGeometry.dispose();
      gridMaterial.dispose();
      nodeGeometry.dispose();
      nodeMaterial.dispose();
      renderer.dispose();
      canvas.remove();
    };
  }, []);

  return <div className="wavelet-stage" ref={host} aria-hidden="true" />;
}
