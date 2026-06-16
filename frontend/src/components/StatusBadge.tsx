import { Badge } from "@matthiaskrijgsman/mat-ui";
import type { BadgeColorKey } from "@matthiaskrijgsman/mat-ui/types";

// Maps the various backend status / confidence enum values to a Badge color.
// Anything not listed falls back to gray.
const COLOR_BY_VALUE: Record<string, BadgeColorKey> = {
  // confidence
  high: "green",
  medium: "amber",
  low: "orange",
  none: "gray",
  // generic success / failure
  success: "green",
  ok: "green",
  failed: "red",
  partial: "amber",
  llm_error: "red",
  // "nothing found, but not an error" outcomes
  no_jobs: "slate",
  no_careers_page: "slate",
  skipped_no_website: "slate",
  // fetch problems
  blocked: "red",
  js_required: "violet",
  timeout: "orange",
  network_error: "red",
  dead_domain: "red",
  skipped_js_heavy: "violet",
  skipped_dead_domain: "red",
  http_4xx: "orange",
  http_5xx: "red",
  non_html: "amber",
  // name types
  statutory: "blue",
  trade: "indigo",
  short: "slate",
  alias: "slate",
  // employment types
  full_time: "green",
  part_time: "teal",
  contract: "amber",
  internship: "violet",
  unknown: "gray",
};

export function StatusBadge({ value }: { value: string }) {
  return <Badge color={COLOR_BY_VALUE[value] ?? "gray"}>{value}</Badge>;
}
