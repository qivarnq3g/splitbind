type NavigatorWithMemory = Navigator & { deviceMemory?: number };

export function deviceCanAfford(): boolean {
  if (typeof window.matchMedia !== "function") return false;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    return false;
  if (!window.matchMedia("(min-width: 64rem)").matches) return false;
  if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches)
    return false;

  const cores = navigator.hardwareConcurrency;
  if (typeof cores === "number" && cores < 4) return false;
  const memory = (navigator as NavigatorWithMemory).deviceMemory;
  if (typeof memory === "number" && memory < 4) return false;

  try {
    const probe = document.createElement("canvas");
    if (!probe.getContext("webgl2")) return false;
  } catch {
    return false;
  }
  return true;
}

export function whenIdle(run: () => void, timeout: number): () => void {
  if (window.requestIdleCallback) {
    const handle = window.requestIdleCallback(run, { timeout });
    return () => window.cancelIdleCallback?.(handle);
  }
  const handle = window.setTimeout(run, Math.min(timeout, 900));
  return () => window.clearTimeout(handle);
}
