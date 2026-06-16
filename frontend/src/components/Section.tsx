import type { ReactNode } from "react";
import { Panel } from "@matthiaskrijgsman/mat-ui";

import { ApiError } from "../api/client.ts";
import { isNotRunYet } from "../api/hooks.ts";

type SectionProps = {
  title: string;
  description?: string;
  /** Action button(s) rendered in the section header. */
  action?: ReactNode;
  children?: ReactNode;
};

/** A titled Panel used for each enrichment step on the company detail page. */
export function Section({ title, description, action, children }: SectionProps) {
  return (
    <Panel className="p-4">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold">{title}</h2>
          {description && (
            <p className="text-sm text-gray-500">{description}</p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {children}
    </Panel>
  );
}

/** Inline error line for a failed query/mutation. Hides "not run yet" 404s. */
export function ErrorNote({ error }: { error: unknown }) {
  if (!error || isNotRunYet(error)) return null;
  const text =
    error instanceof ApiError ? error.detail : "Unexpected error";
  return <p className="text-sm text-red-600">{text}</p>;
}

/** Muted placeholder for a step that hasn't been run yet (a 404 GET). */
export function NotRunYet({ label }: { label: string }) {
  return <p className="text-sm text-gray-400">{label}</p>;
}
