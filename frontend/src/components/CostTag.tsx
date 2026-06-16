import { IconCoin } from "@tabler/icons-react";

import { formatEuro } from "../lib/format.ts";

type CostTagProps = {
  /** EUR amount (API string or number). */
  value: string | number | null | undefined;
  /** "est" prefixes with "est." and dims it (pre-run estimate). */
  variant?: "actual" | "est";
  /** Token counts for the hover tooltip, when known. */
  inputTokens?: number | null;
  outputTokens?: number | null;
};

/** Small euro chip used for per-action cost (estimate or actual) and totals. */
export function CostTag({
  value,
  variant = "actual",
  inputTokens,
  outputTokens,
}: CostTagProps) {
  const isEst = variant === "est";
  const tokens =
    inputTokens != null || outputTokens != null
      ? `${inputTokens ?? 0} in / ${outputTokens ?? 0} out tokens`
      : undefined;

  return (
    <span
      title={tokens}
      className={
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium tabular-nums " +
        (isEst
          ? "text-gray-400"
          : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200")
      }
    >
      <IconCoin size={13} />
      {isEst ? "est. " : ""}
      {formatEuro(value)}
    </span>
  );
}
