import { RefObject } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(useGSAP);
if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
  gsap.registerPlugin(ScrollTrigger);
}

const STILL_SECTIONS = new Set(["01", "05"]);

export function useScrollReveal(scope: RefObject<HTMLElement | null>) {
  useGSAP(
    () => {
      if (typeof window.matchMedia !== "function") return;
      const root = scope.current;
      if (!root) return;
      const media = gsap.matchMedia();
      media.add("(prefers-reduced-motion: no-preference)", () => {
        const hero = root.querySelector<HTMLElement>('[data-landing-section="01"]');
        if (hero) {
          const lines = hero.querySelectorAll<HTMLElement>("[data-hero-line]");
          gsap.set(lines, { opacity: 0, y: 14 });
          gsap.to(lines, {
            opacity: 1,
            y: 0,
            duration: 0.52,
            ease: "power2.out",
            stagger: 0.08,
            clearProps: "opacity,transform",
          });
        }
        const revealed = gsap.utils
          .toArray<HTMLElement>(root.querySelectorAll("[data-landing-section]"))
          .filter((section) => !STILL_SECTIONS.has(section.dataset.landingSection ?? ""));
        const triggers = revealed.map((section) => {
          gsap.set(section, { opacity: 0, y: 18 });
          return gsap.to(section, {
            opacity: 1,
            y: 0,
            duration: 0.62,
            ease: "power2.out",
            clearProps: "opacity,transform",
            scrollTrigger: {
              trigger: section,
              start: "top 82%",
              once: true,
            },
          });
        });
        return () => {
          triggers.forEach((tween) => {
            tween.scrollTrigger?.kill();
            tween.kill();
          });
        };
      });
      return () => media.revert();
    },
    { scope },
  );
}
