// Browser-only module: imported lazily by MapPanel. Never import from SSR code.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Map, { Layer, Marker, NavigationControl, Source, type MapLayerMouseEvent, type MapRef } from "react-map-gl/maplibre";
import { setWorkerUrl, type GeoJSONSource } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { Box, Maximize2 } from "lucide-react";
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

// OpenFreeMap needs no key. Liberty is a full-color street map with 3D buildings; the dark
// style follows the app theme.
const STYLE_LIGHT = "https://tiles.openfreemap.org/styles/liberty";
const STYLE_DARK = "https://tiles.openfreemap.org/styles/dark";
const STYLE_FALLBACK = "https://tiles.openfreemap.org/styles/bright";
// Map paint needs literal colors; these mirror --highlighter and --deed.
function useDarkMode(): boolean {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    const el = document.documentElement;
    const sync = () => setDark(el.classList.contains("dark"));
    sync();
    const mo = new MutationObserver(sync);
    mo.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => mo.disconnect();
  }, []);
  return dark;
}

const GOLD = "#F4B400";
const DEED = "#1B2A33";
const STREET_VIEW = { zoom: 16.4, pitch: 58, bearing: -22 };

// Bundlers do not always resolve maplibre's worker; point it at the packaged file explicitly.
try { setWorkerUrl(workerUrl); } catch { /* already set */ }

type Pos = [number, number];
type Geometry = { type: string; coordinates: unknown };

function ringsOf(g: Geometry | undefined): Pos[][] {
  if (!g) return [];
  if (g.type === "Polygon") return (g.coordinates as Pos[][]).slice(0, 1);
  if (g.type === "MultiPolygon") return (g.coordinates as Pos[][][]).map((p) => p[0]!).filter(Boolean);
  return [];
}

function bounds(coords: Pos[]): [Pos, Pos] {
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
  const [style, setStyle] = useState<string | null>(null);
  const [street, setStreet] = useState(false);
  const reduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const dark = useDarkMode();
  const mapStyle = style ?? (dark ? STYLE_DARK : STYLE_LIGHT);

  const rings = useMemo(() => ringsOf(city?.geometry as Geometry | undefined), [city]);
  const building = points.find((p) => p.kind === "building");
  const many = points.filter((p) => p.kind === "other" || p.kind === "changed");
  const cities = points.filter((p) => p.kind === "city");

  const fitCoords = useMemo<Pos[]>(() => {
    const pts = points.map((p) => [p.lon, p.lat] as Pos);
    if (fit === "city" && rings.length) return [...rings.flat(), ...pts];
    return pts;
  }, [rings, points, fit]);

  const initial = useMemo(() => {
    const b = fitCoords.length ? bounds(fitCoords) : ([[-125, 25], [-66, 49]] as [Pos, Pos]);
    return { bounds: b, fitBoundsOptions: { padding } };
  }, [fitCoords, padding]);

  const overview = useCallback(
    (animate = true) => {
      const m = ref.current;
      if (!m || !fitCoords.length) return;
      m.fitBounds(bounds(fitCoords), { padding, pitch: 0, bearing: 0, duration: reduced || !animate ? 0 : 900 });
      setStreet(false);
    },
    [fitCoords, padding, reduced],
  );

  const streetView = useCallback(() => {
    const m = ref.current;
    if (!m || !building) return;
    m.flyTo({ center: [building.lon, building.lat], ...STREET_VIEW, duration: reduced ? 0 : 2200, essential: false });
    setStreet(true);
  }, [building, reduced]);

  // After the city view settles, glide down to the building so the 3D street view is the payoff.
  useEffect(() => {
    const m = ref.current;
    if (!m || !m.loaded() || !fitCoords.length) return;
    overview(true);
    if (building && fit === "city") {
      const t = setTimeout(streetView, reduced ? 0 : 1300);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [fitCoords]); // eslint-disable-line react-hooks/exhaustive-deps

  const onLoad = useCallback(() => {
    overview(false);
    if (building && fit === "city") setTimeout(streetView, reduced ? 0 : 1300);
  }, [building, fit, overview, streetView, reduced]);

  const pointsGeo = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: many.map((p) => ({ type: "Feature" as const, properties: { id: p.id, kind: p.kind, label: p.label ?? "" }, geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] } })),
    }),
    [many],
  );

  const maskGeo = useMemo(() => {
    if (!rings.length) return null;
    const world: Pos[] = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
    return { type: "Feature" as const, properties: {}, geometry: { type: "Polygon" as const, coordinates: [world, ...rings] } };
  }, [rings]);

  const onClick = (e: MapLayerMouseEvent) => {
    const f = e.features?.[0];
    const m = ref.current?.getMap();
    if (!f || !m || f.properties?.["cluster_id"] === undefined) return;
    const src = m.getSource("pts") as GeoJSONSource;
    void src.getClusterExpansionZoom(f.properties["cluster_id"] as number).then((zoom) => {
      const g = f.geometry as unknown as { coordinates: Pos };
      m.easeTo({ center: g.coordinates, zoom: zoom + 0.5, duration: reduced ? 0 : 500 });
    });
  };

  const bb = rings.length ? bounds(rings.flat()) : null;
  const cityLabelAt: Pos | null = bb ? [(bb[0][0] + bb[1][0]) / 2, bb[1][1]] : null;
  const cluster = many.length > 40;

  return (
    <div role="img" aria-label={ariaLabel} style={{ height }} className="relative w-full overflow-hidden">
      <Map
        ref={ref}
        initialViewState={initial}
        mapStyle={mapStyle}
        onLoad={onLoad}
        onError={(e) => { if (!style && /styles\//.test(String((e.error as { url?: string } | undefined)?.url ?? ""))) setStyle(STYLE_FALLBACK); }}
        attributionControl={{ compact: true }}
        dragRotate
        cooperativeGestures
        interactiveLayerIds={cluster ? ["pts-clusters"] : []}
        onClick={onClick}
        style={{ width: "100%", height: "100%" }}
      >
        <NavigationControl position="top-right" visualizePitch showCompass />

        {maskGeo && (
          <Source id="mask" type="geojson" data={maskGeo}>
            <Layer id="mask-fill" type="fill" paint={{ "fill-color": dark ? "#04080c" : "#0b1620", "fill-opacity": dark ? 0.45 : 0.2 }} />
          </Source>
        )}
        {city && (
          <Source id="city" type="geojson" data={city as never}>
            <Layer id="city-fill" type="fill" paint={{ "fill-color": GOLD, "fill-opacity": 0.1 }} />
            <Layer id="city-glow" type="line" paint={{ "line-color": GOLD, "line-width": 9, "line-blur": 7, "line-opacity": 0.75 }} />
            <Layer id="city-line" type="line" paint={{ "line-color": dark ? "#FFF3C4" : DEED, "line-width": 2.2 }} />
          </Source>
        )}

        {many.length > 0 && (
          <Source id="pts" type="geojson" data={pointsGeo} cluster={cluster} clusterRadius={46} clusterMaxZoom={13}>
            <Layer id="pts-clusters" type="circle" filter={["has", "point_count"]} paint={{
              "circle-color": ["step", ["get", "point_count"], "#2563EB", 25, "#7C3AED", 80, "#DB2777"],
              "circle-radius": ["step", ["get", "point_count"], 17, 25, 22, 80, 28],
              "circle-stroke-width": 3, "circle-stroke-color": "#ffffff", "circle-opacity": 0.92,
            }} />
            <Layer id="pts-count" type="symbol" filter={["has", "point_count"]} layout={{
              "text-field": ["get", "point_count_abbreviated"], "text-font": ["Noto Sans Bold"], "text-size": 13, "text-allow-overlap": true,
            }} paint={{ "text-color": "#ffffff" }} />
            <Layer id="pts-dot" type="circle" filter={["!", ["has", "point_count"]]} paint={{
              "circle-color": ["match", ["get", "kind"], "changed", GOLD, "#2563EB"],
              "circle-radius": ["match", ["get", "kind"], "changed", 6.5, 4.5],
              "circle-stroke-width": 2, "circle-stroke-color": "#ffffff",
            }} />
          </Source>
        )}

        {cities.map((p) => (
          <Marker key={p.id} longitude={p.lon} latitude={p.lat} anchor="bottom">
            <span title={p.label} className="flex flex-col items-center">
              <span className="rounded-full bg-deed px-2 py-0.5 text-[11px] font-semibold leading-tight text-primary-foreground shadow-md ring-2 ring-white/80">{p.label}</span>
              <span className="-mt-0.5 block size-2.5 rotate-45 bg-deed ring-1 ring-white/80" aria-hidden="true" />
            </span>
          </Marker>
        ))}

        {building && (
          <Marker longitude={building.lon} latitude={building.lat} anchor="bottom">
            <span title={building.label} className="relative flex flex-col items-center">
              <span className="absolute -bottom-1 size-6 animate-ping rounded-full bg-[#F4B400]/60" aria-hidden="true" />
              <svg width="38" height="50" viewBox="0 0 38 50" aria-hidden="true" className="relative drop-shadow-[0_4px_6px_rgba(0,0,0,0.45)]">
                <path d="M19 49C19 49 3 31 3 19a16 16 0 0 1 32 0c0 12-16 30-16 30z" fill={GOLD} stroke="#1B2A33" strokeWidth="2.5" />
                <path d="M11 22l8-7 8 7v8H11z" fill="#1B2A33" />
                <rect x="16.5" y="23.5" width="5" height="6.5" fill={GOLD} />
              </svg>
            </span>
          </Marker>
        )}

        {city && cityLabelAt && (
          <Marker longitude={cityLabelAt[0]} latitude={cityLabelAt[1]} anchor="bottom">
            <span className="rounded-full bg-deed px-3 py-1 text-xs font-semibold text-primary-foreground shadow-lg ring-2 ring-[#F4B400]">{city.properties.label}</span>
          </Marker>
        )}
      </Map>

      {(building || fitCoords.length > 1) && (
        <div className="pointer-events-none absolute bottom-2 left-2 flex gap-1.5">
          <button type="button" onClick={() => overview(true)} className="pointer-events-auto inline-flex items-center gap-1.5 rounded-md bg-white/95 px-2.5 py-1.5 text-xs font-semibold text-deed shadow ring-1 ring-black/10 hover:bg-white">
            <Maximize2 className="size-3.5" aria-hidden="true" />Overview
          </button>
          {building && (
            <button type="button" onClick={streetView} aria-pressed={street} className={`pointer-events-auto inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold shadow ring-1 ring-black/10 ${street ? "bg-deed text-primary-foreground" : "bg-white/95 text-deed hover:bg-white"}`}>
              <Box className="size-3.5" aria-hidden="true" />3D street view
            </button>
          )}
        </div>
      )}
    </div>
  );
}
