import { Suspense, lazy, useEffect, useState } from "react";

import { deviceCanAfford, whenIdle } from "../shared/deviceCapability";

const ParticleField = lazy(() => import("./ParticleField"));

export function AtmosphereLayer() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!deviceCanAfford()) return;
    return whenIdle(() => setReady(true), 2200);
  }, []);

  if (!ready) return null;
  return (
    <Suspense fallback={null}>
      <ParticleField />
    </Suspense>
  );
}
