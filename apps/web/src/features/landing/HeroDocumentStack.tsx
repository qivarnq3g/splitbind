import { useCallback, useEffect, useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

const SHEETS = [0, 1, 2, 3, 4];

type Pose = {
  x: number;
  y: number;
  z: number;
  rotationZ: number;
  rotationY: number;
};

const SPAN = 5;

const pose = (i: number, tilt: number, rise: number): Pose => {
  const t = (i - (SPAN - 1) / 2) / ((SPAN - 1) / 2);
  return {
    x: 0,
    y: -rise,
    z: i * 14,
    rotationZ: t * tilt,
    rotationY: 0,
  };
};

const fanned = (i: number): Pose => pose(i, 11, 6);
const spread = (i: number): Pose => pose(i, 24, 34);
const thrown = (i: number): Pose => pose(i, 32, 48);

export function HeroDocumentStack() {
  const scene = useRef<HTMLDivElement>(null);
  const lean = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const loop = useRef<gsap.core.Timeline | null>(null);
  const open = useRef(false);
  const idle = useRef<number | null>(null);

  useGSAP(
    () => {
      if (typeof window.matchMedia !== "function") return;
      const media = gsap.matchMedia();
      media.add("(prefers-reduced-motion: no-preference)", () => {
        const sheets = gsap.utils.toArray<HTMLElement>(
          ".doc-sheet",
          scene.current,
        );
        const seal = scene.current?.querySelector<HTMLElement>(".doc-seal");

        gsap.set(stage.current, { rotationY: -22 });
        const spin = gsap.to(stage.current, {
          rotationY: 22,
          duration: 18,
          ease: "sine.inOut",
          repeat: -1,
          yoyo: true,
        });

        sheets.forEach((sheet, i) => {
          gsap.set(sheet, { ...spread(i), opacity: 0 });
        });

        const intro = gsap.timeline();
        sheets.forEach((sheet, i) => {
          intro.to(
            sheet,
            { opacity: 1, duration: 0.5, ease: "none" },
            i * 0.09,
          );
          intro.to(
            sheet,
            { ...fanned(i), duration: 1.35, ease: "power3.out" },
            i * 0.09,
          );
        });

        const cycle = gsap.timeline({
          repeat: -1,
          repeatDelay: 1.8,
          delay: 2.4,
        });
        sheets.forEach((sheet, i) => {
          cycle.to(
            sheet,
            { ...spread(i), duration: 1.9, ease: "sine.inOut" },
            i * 0.08,
          );
          cycle.to(
            sheet,
            { ...fanned(i), duration: 2.1, ease: "sine.inOut" },
            3.5 + i * 0.09,
          );
        });
        if (seal) {
          cycle.to(
            seal,
            { scale: 1.24, duration: 0.5, ease: "power2.out" },
            5.4,
          );
          cycle.to(seal, { scale: 1, duration: 1.1, ease: "power2.out" }, 5.9);
        }

        loop.current = cycle;

        return () => {
          intro.kill();
          cycle.kill();
          spin.kill();
          loop.current = null;
        };
      });
      return () => media.revert();
    },
    { scope: scene },
  );

  const toggle = useCallback(() => {
    const root = scene.current;
    if (!root || typeof window.matchMedia !== "function") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const sheets = gsap.utils.toArray<HTMLElement>(".doc-sheet", root);
    if (sheets.length === 0) return;
    const seal = root.querySelector<HTMLElement>(".doc-seal");

    loop.current?.pause();
    if (idle.current !== null) window.clearTimeout(idle.current);

    open.current = !open.current;
    const target = open.current ? thrown : fanned;
    const duration = open.current ? 0.9 : 1.45;
    const ease = open.current ? "power3.out" : "power2.inOut";

    sheets.forEach((sheet, i) => {
      gsap.to(sheet, {
        ...target(i),
        duration,
        ease,
        delay: i * 0.045,
        overwrite: "auto",
      });
    });
    if (seal && !open.current) {
      gsap.fromTo(
        seal,
        { scale: 1.3 },
        {
          scale: 1,
          duration: 1.1,
          delay: 0.5,
          ease: "power2.out",
          overwrite: "auto",
        },
      );
    }

    idle.current = window.setTimeout(() => {
      open.current = false;
      sheets.forEach((sheet, i) => {
        gsap.to(sheet, {
          ...fanned(i),
          duration: 1.5,
          ease: "power2.inOut",
          delay: i * 0.05,
          overwrite: "auto",
          onComplete:
            i === sheets.length - 1 ? () => loop.current?.play(0) : undefined,
        });
      });
    }, 6500);
  }, []);

  useEffect(() => {
    const root = scene.current;
    const target = lean.current;
    if (!root || !target || typeof window.matchMedia !== "function") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches)
      return;

    let frame = 0;
    let tx = 0;
    let ty = 0;
    let x = 0;
    let y = 0;

    const step = () => {
      x += (tx - x) * 0.16;
      y += (ty - y) * 0.16;
      target.style.transform = `rotateY(${(x * 26).toFixed(2)}deg) rotateX(${(-y * 16).toFixed(2)}deg)`;
      frame =
        Math.abs(tx - x) + Math.abs(ty - y) > 0.0004
          ? requestAnimationFrame(step)
          : 0;
    };

    const onMove = (event: PointerEvent) => {
      tx = event.clientX / window.innerWidth - 0.5;
      ty = event.clientY / window.innerHeight - 0.5;
      if (frame === 0) frame = requestAnimationFrame(step);
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      if (frame !== 0) cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div className="doc-scene" ref={scene}>
      <button
        type="button"
        className="doc-hit"
        onPointerDown={toggle}
        aria-label="Phát lại hoạt cảnh cấp phát tài liệu"
      />
      <div className="doc-lean" ref={lean} aria-hidden="true">
        <div className="doc-stage" ref={stage}>
          {SHEETS.map((index) => (
            <div className="doc-sheet" key={index} data-sheet={index}>
              <span className="doc-rule doc-rule-lead" />
              <span className="doc-rule" />
              <span className="doc-rule" />
              <span className="doc-rule doc-rule-short" />
              {index === 4 ? <span className="doc-seal" /> : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
