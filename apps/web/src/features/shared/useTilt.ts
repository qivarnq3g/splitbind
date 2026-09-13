import { RefObject, useEffect } from "react";

type TiltOptions = {
  maxDeg?: number;
  lift?: number;
  stiffness?: number;
};

type TiltNode = {
  el: HTMLElement;
  x: number;
  y: number;
  tx: number;
  ty: number;
  on: number;
  ton: number;
};

const SETTLE = 0.0004;

export function useTilt(
  scope: RefObject<HTMLElement | null>,
  selector: string,
  { maxDeg = 6, lift = 6, stiffness = 0.14 }: TiltOptions = {},
) {
  useEffect(() => {
    const root = scope.current;
    if (!root || typeof window.matchMedia !== "function") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;

    const nodes: TiltNode[] = Array.from(
      root.querySelectorAll<HTMLElement>(selector),
    ).map((el) => ({ el, x: 0, y: 0, tx: 0, ty: 0, on: 0, ton: 0 }));
    if (nodes.length === 0) return;

    let frame = 0;

    const step = () => {
      let moving = false;
      for (const node of nodes) {
        node.x += (node.tx - node.x) * stiffness;
        node.y += (node.ty - node.y) * stiffness;
        node.on += (node.ton - node.on) * stiffness;
        const delta =
          Math.abs(node.tx - node.x) +
          Math.abs(node.ty - node.y) +
          Math.abs(node.ton - node.on);
        if (delta > SETTLE) moving = true;
        node.el.style.transform =
          `perspective(900px) rotateX(${(-node.y * maxDeg).toFixed(3)}deg) ` +
          `rotateY(${(node.x * maxDeg).toFixed(3)}deg) ` +
          `translate3d(0, ${(-node.on * lift).toFixed(2)}px, 0)`;
      }
      frame = moving ? requestAnimationFrame(step) : 0;
    };

    const wake = () => {
      if (frame === 0) frame = requestAnimationFrame(step);
    };

    const onMove = (event: PointerEvent) => {
      for (const node of nodes) {
        const rect = node.el.getBoundingClientRect();
        const inside =
          event.clientX >= rect.left &&
          event.clientX <= rect.right &&
          event.clientY >= rect.top &&
          event.clientY <= rect.bottom;
        if (inside) {
          node.tx = (event.clientX - rect.left) / rect.width - 0.5;
          node.ty = (event.clientY - rect.top) / rect.height - 0.5;
          node.ton = 1;
        } else if (node.ton !== 0) {
          node.tx = 0;
          node.ty = 0;
          node.ton = 0;
        }
      }
      wake();
    };

    const rest = () => {
      for (const node of nodes) {
        node.tx = 0;
        node.ty = 0;
        node.ton = 0;
      }
      wake();
    };

    for (const node of nodes) node.el.style.willChange = "transform";
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerleave", rest, { passive: true });
    window.addEventListener("blur", rest);

    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerleave", rest);
      window.removeEventListener("blur", rest);
      if (frame !== 0) cancelAnimationFrame(frame);
      for (const node of nodes) {
        node.el.style.willChange = "";
        node.el.style.transform = "";
      }
    };
  }, [scope, selector, maxDeg, lift, stiffness]);
}
