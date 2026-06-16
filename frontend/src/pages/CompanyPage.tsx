import { Link, useParams } from "react-router-dom";
import { PanelStack, Spinner } from "@matthiaskrijgsman/mat-ui";
import { IconArrowLeft } from "@tabler/icons-react";

import {
  useCareersUrl,
  useCompany,
  useJobs,
  useWebsite,
  useWebsiteSearches,
} from "../api/hooks.ts";
import { CostTag } from "../components/CostTag.tsx";
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

/** Sum the actual EUR cost of the latest row of each costed step. Shares the
 *  section queries' react-query cache — no extra requests. */
function useCompanyTotalEur(kvk: string): number {
  const search = useWebsiteSearches(kvk).data?.[0]?.cost_eur;
  const website = useWebsite(kvk).data?.cost_eur;
  const careers = useCareersUrl(kvk).data?.cost_eur;
  const jobs = useJobs(kvk).data?.cost_eur;
  return [search, website, careers, jobs].reduce<number>(
    (sum, v) => sum + (v ? Number(v) : 0),
    0,
  );
}

export function CompanyPage() {
  const { kvk = "" } = useParams();
  const { data: company, isLoading, error } = useCompany(kvk);
  const totalEur = useCompanyTotalEur(kvk);

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
            <div className="flex items-start justify-between gap-4">
              <h1 className="text-xl font-semibold">
                {primaryName(company.names)}
              </h1>
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span>Total spent</span>
                <CostTag value={totalEur} />
              </div>
            </div>
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
