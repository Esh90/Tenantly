import { lazy, Suspense } from "react";
import { useHydrated } from "@/hooks/use-media";
import type { TenantlyMapProps } from "./TenantlyMap";

const TenantlyMap = lazy(() => import("./TenantlyMap"));

function Placeholder({ height }: { height: number }) {
  return <div style={{ height }} className="w-full bg-muted plan-grid opacity-60" aria-hidden="true" />;
}

/** Lazy, client-only map. Every fact it shows is also available in text. */
export function MapPanel(props: TenantlyMapProps) {
  const hydrated = useHydrated();
  if (!hydrated) return <Placeholder height={props.height} />;
  return (
    <Suspense fallback={<Placeholder height={props.height} />}>
      <TenantlyMap {...props} />
    </Suspense>
  );
}
export type { MapPoint } from "./TenantlyMap";
