import { useEffect, useRef } from "react";
import * as THREE from "three";

const COUNT_WIDE = 900;
const COUNT_NARROW = 420;
const SPREAD = 34;
const POINTER_RADIUS = 13;
const POINTER_PULL = 0.42;
const POINTER_SWIRL = 0.28;

const vertexShader = `
uniform float uTime;
uniform float uScale;
uniform float uSpread;
uniform vec3 uPointer;
uniform float uPointerPull;
uniform float uPointerSwirl;
uniform float uPointerRadius;
uniform float uViewDepth;

attribute float aSeed;
attribute float aSize;
attribute float aDrift;

varying float vGlow;
varying float vHeat;

void main() {
  vec3 raw = position;
  float lift = raw.y + uTime * aDrift + uSpread * 0.5;
  raw.y = mod(lift, uSpread) - uSpread * 0.5;
  raw.x += sin(uTime * 0.21 + aSeed * 6.2831) * 0.7;
  raw.z += cos(uTime * 0.17 + aSeed * 4.7123) * 0.4;

  vec3 reach = uPointer - raw;
  float gap = length(reach);
  float grip = exp(-(gap * gap) / (uPointerRadius * uPointerRadius));
  raw.xy += vec2(-reach.y, reach.x) * grip * uPointerSwirl;
  raw += reach * grip * uPointerPull;

  vec4 viewed = modelViewMatrix * vec4(raw, 1.0);
  gl_Position = projectionMatrix * viewed;

  float twinkle = 0.66 + 0.34 * sin(uTime * 1.15 + aSeed * 9.4248);
  float depth = 0.34 + 0.66 * smoothstep(uViewDepth + uSpread * 0.45, uViewDepth - uSpread * 0.45, -viewed.z);

  vHeat = grip;
  vGlow = twinkle * depth * (1.0 + grip * 1.9);
  gl_PointSize = aSize * (1.0 + grip * 0.85) * uScale / -viewed.z;
}
`;

const fragmentShader = `
uniform vec3 uCalm;
uniform vec3 uLive;
uniform float uOpacity;

varying float vGlow;
varying float vHeat;

void main() {
  vec2 offset = gl_PointCoord - 0.5;
  float radius = length(offset) * 2.0;
  if (radius > 1.0) discard;

  float falloff = 1.0 - radius;
  float core = pow(falloff, 3.2);
  float halo = pow(falloff, 1.1) * 0.32;

  vec3 tone = mix(uCalm, uLive, clamp(core * 0.8 + vHeat, 0.0, 1.0));
  gl_FragColor = vec4(tone, (core + halo) * uOpacity * vGlow);
}
`;

export default function ParticleField() {
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
        antialias: false,
        powerPreference: "low-power",
      });
    } catch {
      return;
    }

    const count = window.innerWidth < 1100 ? COUNT_NARROW : COUNT_WIDE;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    mount.appendChild(canvas);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(52, 1, 0.1, 200);
    camera.position.z = 46;

    const positions = new Float32Array(count * 3);
    const seeds = new Float32Array(count);
    const sizes = new Float32Array(count);
    const drifts = new Float32Array(count);
    for (let i = 0; i < count; i += 1) {
      positions[i * 3] = (Math.random() - 0.5) * SPREAD * 1.7;
      positions[i * 3 + 1] = (Math.random() - 0.5) * SPREAD;
      positions[i * 3 + 2] = (Math.random() - 0.5) * SPREAD * 0.55;
      seeds[i] = Math.random();
      sizes[i] = 0.055 + Math.pow(Math.random(), 3.0) * 0.17;
      drifts[i] = 0.12 + Math.random() * 0.5;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
    geometry.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
    geometry.setAttribute("aDrift", new THREE.BufferAttribute(drifts, 1));
    geometry.boundingSphere = new THREE.Sphere(
      new THREE.Vector3(),
      SPREAD * 1.6,
    );

    const uniforms = {
      uTime: { value: 0 },
      uScale: { value: 300 },
      uSpread: { value: SPREAD },
      uPointer: { value: new THREE.Vector3(0, 0, 0) },
      uPointerPull: { value: 0 },
      uPointerSwirl: { value: 0 },
      uPointerRadius: { value: POINTER_RADIUS },
      uViewDepth: { value: camera.position.z },
      uCalm: { value: new THREE.Color("#a7b6bb") },
      uLive: { value: new THREE.Color("#14515f") },
      uOpacity: { value: 0.4 },
    };

    const material = new THREE.ShaderMaterial({
      uniforms,
      vertexShader,
      fragmentShader,
      transparent: true,
      depthWrite: false,
      depthTest: false,
    });
    const points = new THREE.Points(geometry, material);
    points.frustumCulled = false;
    scene.add(points);

    let tx = 0;
    let ty = 0;
    let px = 0;
    let py = 0;
    let pointerSeen = false;
    const onMove = (event: PointerEvent) => {
      tx = event.clientX / window.innerWidth - 0.5;
      ty = event.clientY / window.innerHeight - 0.5;
      pointerSeen = true;
    };

    const resize = () => {
      const rect = mount.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      renderer.setSize(rect.width, rect.height, false);
      camera.aspect = rect.width / rect.height;
      camera.updateProjectionMatrix();
      uniforms.uScale.value = renderer.domElement.height * 0.5;
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(mount);
    window.addEventListener("pointermove", onMove, { passive: true });

    let raf = 0;
    let running = true;
    const timer = new THREE.Timer();
    timer.connect(document);
    const pointerWorld = new THREE.Vector3();

    const tick = () => {
      if (!running) return;
      timer.update();
      const dt = Math.min(timer.getDelta(), 0.05);
      uniforms.uTime.value = timer.getElapsed();
      px += (tx - px) * 0.06;
      py += (ty - py) * 0.06;

      points.rotation.y += dt * 0.028;
      points.rotation.x = -py * 0.24;
      camera.position.x = px * 7;
      camera.position.y = -py * 4;
      camera.lookAt(0, 0, 0);
      camera.updateMatrixWorld();
      points.updateMatrixWorld();

      pointerWorld.set(px * 2, -py * 2, 0.5).unproject(camera);
      pointerWorld.sub(camera.position).normalize();
      const reach = -camera.position.z / pointerWorld.z;
      pointerWorld.multiplyScalar(reach).add(camera.position);
      points.worldToLocal(pointerWorld);
      uniforms.uPointer.value.copy(pointerWorld);

      const engage = pointerSeen ? 1 : 0;
      uniforms.uPointerPull.value +=
        (engage * POINTER_PULL - uniforms.uPointerPull.value) * 0.06;
      uniforms.uPointerSwirl.value +=
        (engage * POINTER_SWIRL - uniforms.uPointerSwirl.value) * 0.06;

      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };

    const onVisibility = () => {
      if (document.hidden) {
        running = false;
        if (raf !== 0) cancelAnimationFrame(raf);
        raf = 0;
      } else if (raf === 0) {
        running = true;
        raf = requestAnimationFrame(tick);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    raf = requestAnimationFrame(tick);

    return () => {
      running = false;
      if (raf !== 0) cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onMove);
      observer.disconnect();
      timer.dispose();
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      canvas.remove();
    };
  }, []);

  return <div className="particle-field" ref={host} aria-hidden="true" />;
}
