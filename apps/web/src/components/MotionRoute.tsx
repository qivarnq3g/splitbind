import { PropsWithChildren, useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useLocation } from "react-router-dom";

gsap.registerPlugin(useGSAP);

export function MotionRoute({ children }: PropsWithChildren) {
  const root = useRef<HTMLDivElement>(null);
  const location = useLocation();

  useGSAP(
    () => {
      if (typeof window.matchMedia !== "function") {
        gsap.set(root.current, { autoAlpha: 1 });
        return;
      }

      const media = gsap.matchMedia();

      media.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.fromTo(
          root.current,
          { autoAlpha: 0, y: 10 },
          { autoAlpha: 1, y: 0, duration: 0.38, ease: "power2.out", clearProps: "transform,opacity,visibility" },
        );
      });

      media.add("(prefers-reduced-motion: reduce)", () => {
        gsap.fromTo(root.current, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.12, clearProps: "opacity,visibility" });
      });

      return () => media.revert();
    },
    { scope: root, dependencies: [location.pathname], revertOnUpdate: true },
  );

  return <div ref={root} className="route-stage" data-motion-page>{children}</div>;
}
