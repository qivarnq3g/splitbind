import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

gsap.registerPlugin(useGSAP);

export type CryptographicMotifStage =
  | "idle"
  | "hashing"
  | "decomposing"
  | "signing"
  | "verifying"
  | "sealed"
  | "tampered";

export interface CryptographicMotifProps {
  stage?: CryptographicMotifStage;
  className?: string;
  size?: number;
}

export function CryptographicMotif({
  stage = "idle",
  className = "",
  size = 240,
}: CryptographicMotifProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
        return;
      }

      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (prefersReduced) {
        gsap.set(
          ".motif-node, .motif-scan-trace, .motif-core, .motif-seal-geometry, .motif-seal-inner-ring, .motif-wavelet-path, .motif-hash-pip",
          { clearProps: "all" }
        );
        return;
      }

      if (stage === "idle") {
        const tl = gsap.timeline({ repeat: -1, yoyo: true });
        tl.to(".motif-core", { scale: 1.15, duration: 2.4, ease: "sine.inOut" })
          .to(".motif-grid-ring", { opacity: 0.5, duration: 2.4, ease: "sine.inOut" }, "<")
          .to(".motif-wavelet-path", { opacity: 0.8, duration: 2.4, stagger: 0.2, ease: "sine.inOut" }, "<");
        return;
      }

      if (stage === "hashing") {
        const tl = gsap.timeline({ repeat: -1 });
        tl.to(".motif-hash-pip", {
          opacity: 1,
          scale: 1.4,
          stagger: { each: 0.08, repeat: 1, yoyo: true },
          duration: 0.35,
          ease: "power1.inOut",
        });
        tl.to(".motif-core", { rotate: 360, duration: 3.6, ease: "none", repeat: -1 }, 0);
        return;
      }

      if (stage === "decomposing") {
        const tl = gsap.timeline({ repeat: -1, yoyo: true });
        tl.to(".motif-wavelet-ll", { scale: 1.12, transformOrigin: "60px 50px", duration: 1.4, ease: "sine.inOut" })
          .to(".motif-wavelet-hl", { strokeDashoffset: -18, duration: 1.4, ease: "sine.inOut" }, "<")
          .to(".motif-wavelet-lh", { strokeDashoffset: 18, duration: 1.4, ease: "sine.inOut" }, "<")
          .to(".motif-wavelet-hh", { scale: 1.18, transformOrigin: "145px 145px", duration: 1.4, ease: "sine.inOut" }, "<")
          .to(".motif-axes", { opacity: 0.85, duration: 1.4, ease: "sine.inOut" }, "<");
        return;
      }

      if (stage === "signing") {
        const tl = gsap.timeline({ repeat: -1, yoyo: true });
        tl.to(".motif-node-top", { y: 22, duration: 1.2, ease: "power2.inOut" })
          .to(".motif-node-bottom", { y: -22, duration: 1.2, ease: "power2.inOut" }, "<")
          .to(".motif-node-left", { x: 22, duration: 1.2, ease: "power2.inOut" }, "<")
          .to(".motif-node-right", { x: -22, duration: 1.2, ease: "power2.inOut" }, "<")
          .to(".motif-node-tl", { x: 16, y: 16, duration: 1.2, ease: "power2.inOut" }, "<")
          .to(".motif-node-tr", { x: -16, y: 16, duration: 1.2, ease: "power2.inOut" }, "<")
          .to(".motif-node-br", { x: -16, y: -16, duration: 1.2, ease: "power2.inOut" }, "<")
          .to(".motif-node-bl", { x: 16, y: -16, duration: 1.2, ease: "power2.inOut" }, "<")
          .to(".motif-core", { scale: 1.3, duration: 1.2, ease: "power2.inOut" }, "<");
        return;
      }

      if (stage === "verifying") {
        const tl = gsap.timeline({ repeat: -1, yoyo: true });
        tl.fromTo(
          ".motif-scan-trace",
          { y: -55, opacity: 0.2 },
          { y: 55, opacity: 1, duration: 1.4, ease: "power1.inOut" }
        )
        .to(".motif-wavelet-path", { opacity: 0.95, stagger: 0.1, duration: 0.7, ease: "sine.inOut" }, 0);
        return;
      }

      if (stage === "sealed") {
        const tl = gsap.timeline();
        tl.fromTo(
          ".motif-seal-geometry",
          { scale: 0.82, opacity: 0, rotate: -20, transformOrigin: "100px 100px" },
          { scale: 1, opacity: 1, rotate: 0, duration: 0.7, ease: "back.out(1.7)" }
        )
        .fromTo(
          ".motif-seal-inner-ring",
          { scale: 0.7, opacity: 0, transformOrigin: "100px 100px" },
          { scale: 1, opacity: 1, duration: 0.5, ease: "power2.out" },
          "-=0.35"
        )
        .fromTo(
          ".motif-core",
          { scale: 0.75 },
          { scale: 1.1, duration: 0.45, ease: "back.out(2)" },
          "-=0.25"
        );
        return;
      }

      if (stage === "tampered") {
        const tl = gsap.timeline();
        tl.to(".motif-seal-geometry", {
          x: 4,
          y: -3,
          rotate: 3,
          transformOrigin: "100px 100px",
          duration: 0.08,
          repeat: 5,
          yoyo: true,
          ease: "power1.inOut",
        })
        .to(".motif-core", { scale: 0.9, duration: 0.2 })
        .to(".motif-wavelet-hh", { x: 5, opacity: 0.35, duration: 0.2 }, "<");
        return;
      }
    },
    { scope: containerRef, dependencies: [stage], revertOnUpdate: true }
  );

  return (
    <div
      ref={containerRef}
      className={`cryptographic-motif ${className}`.trim()}
      data-stage={stage}
      style={{ width: size, height: size }}
    >
      <svg
        role="img"
        aria-label={`Cryptographic motif: ${stage}`}
        className="cryptographic-motif-svg"
        viewBox="0 0 200 200"
        width={size}
        height={size}
      >
        <rect x="24" y="24" width="152" height="152" rx="8" className="motif-document" />

        <circle cx="100" cy="100" r="76" className="motif-grid-ring" />
        <circle cx="100" cy="100" r="48" className="motif-grid-ring" />

        <g className="motif-axes">
          <line x1="20" y1="100" x2="180" y2="100" className="motif-axis-line" />
          <line x1="100" y1="20" x2="100" y2="180" className="motif-axis-line" />
          <line x1="60" y1="96" x2="60" y2="104" className="motif-axis-line" />
          <line x1="140" y1="96" x2="140" y2="104" className="motif-axis-line" />
          <line x1="96" y1="60" x2="104" y2="60" className="motif-axis-line" />
          <line x1="96" y1="140" x2="104" y2="140" className="motif-axis-line" />
        </g>

        <g className="motif-wavelets">
          <path d="M 32 60 Q 60 40 88 60" className="motif-wavelet-path motif-wavelet-ll" />
          <path d="M 112 52 Q 126 36 140 52 T 168 52" className="motif-wavelet-path motif-wavelet-hl" />
          <path d="M 32 136 Q 48 120 64 136 T 88 136" className="motif-wavelet-path motif-wavelet-lh" />
          <path d="M 112 144 Q 126 128 140 144 T 168 144" className="motif-wavelet-path motif-wavelet-hh" />
        </g>

        <g className="motif-hash-fragments">
          <circle cx="100" cy="24" r="2" className="motif-hash-pip" />
          <circle cx="154" cy="46" r="2" className="motif-hash-pip" />
          <circle cx="176" cy="100" r="2" className="motif-hash-pip" />
          <circle cx="154" cy="154" r="2" className="motif-hash-pip" />
          <circle cx="100" cy="176" r="2" className="motif-hash-pip" />
          <circle cx="46" cy="154" r="2" className="motif-hash-pip" />
          <circle cx="24" cy="100" r="2" className="motif-hash-pip" />
          <circle cx="46" cy="46" r="2" className="motif-hash-pip" />
        </g>

        <g className="motif-nodes">
          <circle cx="100" cy="40" r="4" className="motif-node motif-node-top" />
          <circle cx="160" cy="100" r="4" className="motif-node motif-node-right" />
          <circle cx="100" cy="160" r="4" className="motif-node motif-node-bottom" />
          <circle cx="40" cy="100" r="4" className="motif-node motif-node-left" />
          <circle cx="58" cy="58" r="3" className="motif-node motif-node-tl" />
          <circle cx="142" cy="58" r="3" className="motif-node motif-node-tr" />
          <circle cx="142" cy="142" r="3" className="motif-node motif-node-br" />
          <circle cx="58" cy="142" r="3" className="motif-node motif-node-bl" />
        </g>

        <g className="motif-seal">
          <polygon
            points="100,34 146,54 166,100 146,146 100,166 54,146 34,100 54,54"
            className="motif-seal-geometry"
          />
          <circle cx="100" cy="100" r="28" className="motif-seal-inner-ring" />
        </g>

        <line x1="28" y1="100" x2="172" y2="100" className="motif-scan-trace" />

        <circle cx="100" cy="100" r="7" className="motif-core" />
      </svg>
    </div>
  );
}
