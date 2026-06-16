import { Link, useParams } from "react-router-dom";
import { PanelStack, Spinner } from "@matthiaskrijgsman/mat-ui";
import { IconArrowLeft } from "@tabler/icons-react";

import { useCompany } from "../api/hooks.ts";
import { ErrorNote } from "../components/Section.tsx";
import { StatusBadge } from "../components/StatusBadge.tsx";
import { primaryName } from "../lib/format.ts";
import {
  CareersSection,
  GeocodeSection,
  JobsSection,
  ResolveWebsiteSection,
  ScrapeSection,
  WebsiteSearchSection,
} from "./sections.tsx";

export function CompanyPage() {
  const { kvk = "" } = useParams();
  const { data: company, isLoading, error } = useCompany(kvk);

  return (
    <div className="space-y-5">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800"
      >
        <IconArrowLeft size={16} /> All companies
      </Link>

      <ErrorNote error={error} />
      {isLoading && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {company && (
        <>
          <div>
            <h1 className="text-xl font-semibold">{primaryName(company.names)}</h1>
            <p className="font-mono text-sm text-gray-500">{company.kvk_number}</p>
            <div className="mt-3 flex flex-col gap-1.5">
              {company.names.map((n, i) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                  <StatusBadge value={n.type} />
                  <span>{n.name}</span>
                </div>
              ))}
            </div>
          </div>

          <PanelStack>
            <WebsiteSearchSection kvk={kvk} />
            <ResolveWebsiteSection kvk={kvk} />
            <ScrapeSection kvk={kvk} />
            <CareersSection kvk={kvk} />
            <JobsSection kvk={kvk} />
            <GeocodeSection kvk={kvk} company={company} />
          </PanelStack>
        </>
      )}
    </div>
  );
}
