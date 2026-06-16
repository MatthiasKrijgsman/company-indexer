import type { AddressRead, CompanyNameRead } from "../api/types.ts";

/** Format a euro amount (string from the API, or number) to 4 dp: `€0.0009`. */
export function formatEuro(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(n)) return "—";
  return `€${n.toFixed(4)}`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** Pick the statutory name, falling back to the first available name. */
export function primaryName(names: CompanyNameRead[]): string {
  const statutory = names.find((n) => n.type === "statutory");
  return statutory?.name ?? names[0]?.name ?? "—";
}

export function addressLine(a: AddressRead): string {
  const street = [a.street, a.house_number].filter(Boolean).join(" ");
  const city = [a.postcode, a.city].filter(Boolean).join(" ");
  return [street, city, a.country].filter(Boolean).join(", ");
}

export function firstCity(addresses: AddressRead[]): string {
  return addresses.find((a) => a.city)?.city ?? "—";
}
