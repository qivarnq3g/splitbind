import { RefObject } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(useGSAP);
if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
  gsap.registerPlugin(ScrollTrigger);
}

const STILL_SECTIONS = new Set(["01"]);

export function useScrollReveal(scope: RefObject<HTMLElement | null>) {
  useGSAP(
    () => {
      if (typeof window.matchMedia !== "function") return;
      const root = scope.current;
      if (!root) return;
      const media = gsap.matchMedia();
      media.add("(prefers-reduced-motion: no-preference)", () => {
        const hero = root.querySelector<HTMLElement>(
          '[data-landing-section="01"]',
        );
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

        const tweens: gsap.core.Tween[] = [];

        const revealed = gsap.utils
          .toArray<HTMLElement>(root.querySelectorAll("[data-landing-section]"))
          .filter(
            (section) =>
              !STILL_SECTIONS.has(section.dataset.landingSection ?? ""),
          );

        for (const section of revealed) {
          const items = gsap.utils.toArray<HTMLElement>(
            section.querySelectorAll("[data-reveal-item]"),
          );
          if (items.length > 1) {
            gsap.set(items, { opacity: 0, y: 22 });
            tweens.push(
              gsap.to(items, {
                opacity: 1,
                y: 0,
                duration: 0.62,
                ease: "power2.out",
                stagger: 0.15,
                clearProps: "opacity,transform",
                scrollTrigger: {
                  trigger: section,
                  start: "top 82%",
                  once: true,
                },
              }),
            );
            continue;
          }
          const body = section.querySelector<HTMLElement>(
            ".landing-section-body",
          );
          const parts = gsap.utils.toArray<HTMLElement>(
            (body ?? section).children,
          );
          if (parts.length === 0) continue;
          gsap.set(parts, { opacity: 0, y: 18 });
          tweens.push(
            gsap.to(parts, {
              opacity: 1,
              y: 0,
              duration: 0.62,
              ease: "power2.out",
              stagger: 0.15,
              clearProps: "opacity,transform",
              scrollTrigger: { trigger: section, start: "top 82%", once: true },
            }),
          );
        }

        const layers = gsap.utils.toArray<HTMLElement>(
          root.querySelectorAll("[data-parallax]"),
        );
        for (const layer of layers) {
          const depth = Number(layer.dataset.parallax) || 12;
          tweens.push(
            gsap.to(layer, {
              yPercent: depth,
              ease: "none",
              scrollTrigger: {
                trigger: root,
                start: "top top",
                end: "bottom bottom",
                scrub: 0.6,
              },
            }),
          );
        }

        return () => {
          tweens.forEach((tween) => {
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
