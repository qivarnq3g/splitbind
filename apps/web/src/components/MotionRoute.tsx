import { PropsWithChildren, useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useLocation } from "react-router-dom";

gsap.registerPlugin(useGSAP);

function getWorkflowStageRank(pathname: string): number {
  if (pathname.startsWith("/issue") || pathname.startsWith("/verify")) return 1;
  if (pathname.startsWith("/jobs/")) return 2;
  if (pathname.startsWith("/issuances/") || pathname.startsWith("/verifications/")) return 3;
  return 0;
}

export function MotionRoute({ children }: PropsWithChildren) {
  const root = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const previousStageRef = useRef<number | null>(null);

  useGSAP(
    () => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
        gsap.set(root.current, { autoAlpha: 1, clearProps: "transform,opacity,visibility" });
        return;
      }

      const currentStage = getWorkflowStageRank(location.pathname);
      const prevStage = previousStageRef.current;
      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      if (prefersReduced) {
        gsap.fromTo(
          root.current,
          { autoAlpha: 0 },
          { autoAlpha: 1, duration: 0.08, clearProps: "transform,opacity,visibility" }
        );
        previousStageRef.current = currentStage;
        return;
      }

      const media = gsap.matchMedia();

      media.add("(prefers-reduced-motion: no-preference)", () => {
        let deltaX = 0;
        let deltaY = 6;

        if (prevStage !== null && prevStage !== 0 && currentStage !== 0) {
          if (currentStage > prevStage) {
            deltaX = 12;
            deltaY = 0;
          } else if (currentStage < prevStage) {
            deltaX = -12;
            deltaY = 0;
          }
        }

        const tl = gsap.timeline({
          onComplete: () => {
            if (root.current) {
              gsap.set(root.current, { clearProps: "transform,opacity,visibility" });
            }
          },
        });

        tl.fromTo(
          root.current,
          { autoAlpha: 0, x: deltaX, y: deltaY },
          {
            autoAlpha: 1,
            x: 0,
            y: 0,
            duration: 0.28,
            ease: "power2.out",
            clearProps: "transform,opacity,visibility",
          }
        );

        const innerElements = root.current?.querySelectorAll(
          ".page-heading, .workbench, .status-board, .login-panel, .login-intro, .verification-seal-construction, .issuance-chamber"
        );
        if (innerElements && innerElements.length > 0) {
          const innerX = deltaX !== 0 ? (deltaX > 0 ? 8 : -8) : 0;
          const innerY = deltaX === 0 ? 4 : 0;

          tl.fromTo(
            innerElements,
            { autoAlpha: 0, x: innerX, y: innerY },
            {
              autoAlpha: 1,
              x: 0,
              y: 0,
              duration: 0.24,
              stagger: 0.05,
              ease: "power2.out",
              clearProps: "transform,opacity,visibility",
            },
            "-=0.18"
          );
        }
      });

      previousStageRef.current = currentStage;
      return () => media.revert();
    },
    { scope: root, dependencies: [location.pathname], revertOnUpdate: true }
  );

  return (
    <div
      ref={root}
      className="route-stage"
      data-motion-page
      data-stage-rank={getWorkflowStageRank(location.pathname)}
    >
      {children}
    </div>
  );
}
