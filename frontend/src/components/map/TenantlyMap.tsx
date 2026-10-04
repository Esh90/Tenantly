// Browser-only module: imported lazily by MapPanel. Never import from SSR code.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Map, { Layer, Marker, Source, type MapRef } from "react-map-gl/maplibre";
import type { JurisdictionFeature } from "@/lib/api/api";

export interface MapPoint {
  id: string;
  lat: number;
  lon: number;
  kind: "building" | "changed" | "other" | "city";
  label?: string;
}

export interface TenantlyMapProps {
  city?: JurisdictionFeature | null;
  points?: MapPoint[];
  height: number;
  ariaLabel: string;
  fit?: "city" | "points";
  padding?: number;
}

const POSITRON = "https://tiles.openfreemap.org/styles/positron";
const LIBERTY = "https://tiles.openfreemap.org/styles/liberty";
// Map paint needs literal colors; these mirror --highlighter and --deed.
const HIGHLIGHTER = "#F4D35E";
const DEED = "#1B2A33";

function bounds(coords: [number, number][]): [[number, number], [number, number]] {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of coords) {
    minX = Math.min(minX, x); minY = Math.min(minY, y);
    maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
  }
  if (minX === maxX) { minX -= 0.02; maxX += 0.02; }
  if (minY === maxY) { minY -= 0.02; maxY += 0.02; }
  return [[minX, minY], [maxX, maxY]];
}

export default function TenantlyMap({ city, points = [], height, ariaLabel, fit = "city", padding = 28 }: TenantlyMapProps) {
  const ref = useRef<MapRef>(null);
  const [style, setStyle] = useState(POSITRON);
  const reduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const fitCoords = useMemo<[number, number][]>(() => {
    if (fit === "city" && city) return [...(city.geometry.coordinates[0] ?? []), ...points.map((p) => [p.lon, p.lat] as [number, number])];
    return points.map((p) => [p.lon, p.lat]);
  }, [city, points, fit]);

  const initial = useMemo(() => {
    const b = fitCoords.length ? bounds(fitCoords) : ([[-125, 25], [-66, 49]] as [[number, number], [number, number]]);
    return { bounds: b, fitBoundsOptions: { padding } };
  }, [fitCoords, padding]);

  const onLoad = useCallback(() => {
    if (!ref.current || !fitCoords.length) return;
    ref.current.fitBounds(bounds(fitCoords), { padding, duration: reduced ? 0 : 700 });
  }, [fitCoords, padding, reduced]);

  useEffect(() => {
    const m = ref.current;
    if (m && m.loaded() && fitCoords.length) m.fitBounds(bounds(fitCoords), { padding, duration: reduced ? 0 : 700 });
  }, [fitCoords, padding, reduced]);

  return (
    <div role="img" aria-label={ariaLabel} style={{ height }} className="relative w-full overflow-hidden">
      <Map
        ref={ref}
        initialViewState={initial}
        mapStyle={style}
        onLoad={onLoad}
        onError={() => style !== LIBERTY && setStyle(LIBERTY)}
        attributionControl={{ compact: true }}
        dragRotate={false}
        cooperativeGestures
        style={{ width: "100%", height: "100%" }}
      >
        {city && (
          <Source id="city" type="geojson" data={city}>
            <Layer id="city-fill" type="fill" paint={{ "fill-color": HIGHLIGHTER, "fill-opacity": 0.35 }} />
            <Layer id="city-line" type="line" paint={{ "line-color": DEED, "line-width": 2 }} />
          </Source>
        )}
        {points.map((p) => (
          <Marker key={p.id} longitude={p.lon} latitude={p.lat} anchor="center">
            {p.kind === "building" ? (
              <span title={p.label} className="block size-4 rounded-full border-[3px] border-highlighter bg-deed ring-1 ring-deed" />
            ) : p.kind === "changed" || p.kind === "city" ? (
              <span title={p.label} className="block size-3 rounded-full border border-deed bg-highlighter" />
            ) : (
              <span title={p.label} className="block size-1.5 rounded-full bg-graphite" />
            )}
          </Marker>
        ))}
      </Map>
    </div>
  );
}
