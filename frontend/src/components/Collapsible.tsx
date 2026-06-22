import { useState, type ReactNode } from "react";
import { IconChevronRight } from "@tabler/icons-react";

/** A bordered, click-to-expand disclosure for showing a step's raw output.
 *  Collapsed by default — the section's summary fields stay visible above it. */
export function Collapsible({
  title,
  defaultOpen = false,
  children,
}: {
  title: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-md border border-gray-200">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-xs font-medium text-gray-600 hover:text-gray-900"
      >
        <IconChevronRight
          size={14}
          className={`shrink-0 text-gray-400 transition-transform ${open ? "rotate-90" : ""}`}
        />
        {title}
      </button>
      {open && <div className="border-t border-gray-200 p-2.5">{children}</div>}
    </div>
  );
}
