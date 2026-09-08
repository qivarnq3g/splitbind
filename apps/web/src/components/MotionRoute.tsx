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

      if (typeof window !== "undefined") {
        window.scrollTo({ left: 0, top: 0, behavior: "instant" });
      }

      const currentStage = getWorkflowStageRank(location.pathname);
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
        const deltaY = 6;

        const tl = gsap.timeline({
          onComplete: () => {
            if (root.current) {
              gsap.set(root.current, { clearProps: "transform,opacity,visibility" });
            }
          },
        });

        tl.fromTo(
          root.current,
          { autoAlpha: 0, y: deltaY },
          {
            autoAlpha: 1,
            y: 0,
            duration: 0.26,
            ease: "power2.out",
            clearProps: "transform,opacity,visibility",
          }
        );

        const innerElements = root.current?.querySelectorAll(
          ".page-heading, .workbench, .status-board, .login-panel, .login-intro, .verification-seal-construction, .issuance-chamber"
        );
        if (innerElements && innerElements.length > 0) {
          tl.fromTo(
            innerElements,
            { autoAlpha: 0, y: 4 },
            {
              autoAlpha: 1,
              y: 0,
              duration: 0.22,
              stagger: 0.04,
              ease: "power2.out",
              clearProps: "transform,opacity,visibility",
            },
            "-=0.16"
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
