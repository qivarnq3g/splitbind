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
        const stage = root.current;
        if (!stage) return;
        const timeline = gsap.timeline();
        timeline.fromTo(
          stage,
          { opacity: 0, y: 8 },
          {
            opacity: 1,
            y: 0,
            duration: 0.26,
            ease: "power2.out",
            clearProps: "opacity,transform",
          },
        );
        const blocks = gsap.utils.toArray<HTMLElement>(
          stage.querySelectorAll("[data-motion-block]"),
        );
        if (blocks.length > 0) {
          timeline.fromTo(
            blocks,
            { opacity: 0, y: 10 },
            {
              opacity: 1,
              y: 0,
              duration: 0.3,
              ease: "power2.out",
              stagger: 0.045,
              clearProps: "opacity,transform",
            },
            "-=0.14",
          );
        }
        return () => timeline.kill();
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
