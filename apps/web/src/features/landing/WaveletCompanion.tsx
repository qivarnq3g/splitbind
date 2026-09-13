import { Suspense, lazy, useEffect, useState } from "react";

import { deviceCanAfford, whenIdle } from "../shared/deviceCapability";

const WaveletSurface = lazy(() => import("./WaveletSurface"));

export function WaveletCompanion() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!deviceCanAfford()) return;
    return whenIdle(() => setReady(true), 2600);
  }, []);

  if (!ready) return <div className="wavelet-stage" aria-hidden="true" />;
  return (
    <Suspense fallback={<div className="wavelet-stage" aria-hidden="true" />}>
      <WaveletSurface />
    </Suspense>
  );
}
