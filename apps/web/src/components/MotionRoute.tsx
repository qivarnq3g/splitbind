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
      if (typeof window.matchMedia !== "function") return;
      window.scrollTo({ top: 0, behavior: "instant" });
      const heading = root.current?.querySelector<HTMLElement>("h1");
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      }
      const media = gsap.matchMedia();
      media.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.fromTo(
          root.current,
          { opacity: 0.6 },
          {
            opacity: 1,
            duration: 0.18,
            ease: "power2.out",
            clearProps: "opacity",
          },
        );
      });
      return () => media.revert();
    },
    { scope: root, dependencies: [location.pathname], revertOnUpdate: true },
  );
  const rank = location.pathname.startsWith("/jobs/")
    ? 2
    : /^\/(issuances|verifications)\//.test(location.pathname)
      ? 3
      : 1;
  return (
    <div
      ref={root}
      className="route-stage"
      data-motion-page
      data-stage-rank={rank}
    >
      {children}
    </div>
  );
}
