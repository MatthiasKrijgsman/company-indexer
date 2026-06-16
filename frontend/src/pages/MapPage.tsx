import { useEffect } from "react";
import { Link } from "react-router-dom";
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import { Spinner } from "@matthiaskrijgsman/mat-ui";

// Leaflet's default marker icon URLs don't survive bundling — point them at the
// package's image assets (Vite resolves these imports to URLs). We build an
// explicit L.Icon and pass it per-Marker: L.Icon.Default prepends its
// auto-detected image path to the URL, which doubles up an already-absolute
// bundled URL. The base L.Icon uses the URLs verbatim.
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

import { useCompanyGeo } from "../api/hooks.ts";
import type { CompanyGeoPoint } from "../api/types.ts";
import { ErrorNote, NotRunYet } from "../components/Section.tsx";

const PIN = new L.Icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

// Center of the Netherlands — the fallback view when there are no points.
const NL_CENTER: [number, number] = [52.15, 5.3];

function latlng(p: CompanyGeoPoint): [number, number] {
  return [Number(p.lat), Number(p.lon)];
}

/** Fits the map to the markers once they load. */
function FitBounds({ points }: { points: CompanyGeoPoint[] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    const bounds = L.latLngBounds(points.map(latlng));
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
  }, [points, map]);
  return null;
}

export function MapPage() {
  const { data, isLoading, error } = useCompanyGeo();
  const points = data ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Map</h1>
        <span className="text-sm text-gray-500">
          {points.length} geocoded {points.length === 1 ? "location" : "locations"}
        </span>
      </div>

      <ErrorNote error={error} />

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : (
        <div className="h-[70vh] overflow-hidden rounded-lg border border-gray-200">
          <MapContainer center={NL_CENTER} zoom={7} className="h-full w-full">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {points.map((p, i) => (
              <Marker key={`${p.kvk_number}-${i}`} position={latlng(p)} icon={PIN}>
                <Popup>
                  <div className="space-y-0.5">
                    <div className="font-semibold">{p.name}</div>
                    <div className="font-mono text-xs text-gray-500">
                      {p.kvk_number}
                    </div>
                    {p.city && <div className="text-xs">{p.city}</div>}
                    <Link
                      to={`/companies/${p.kvk_number}`}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Open company →
                    </Link>
                  </div>
                </Popup>
              </Marker>
            ))}
            <FitBounds points={points} />
          </MapContainer>
        </div>
      )}

      {!isLoading && points.length === 0 && (
        <NotRunYet label="No geocoded companies yet — run Geocode on a company first." />
      )}
    </div>
  );
}
