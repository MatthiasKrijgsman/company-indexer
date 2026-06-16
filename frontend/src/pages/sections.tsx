import {
  Button,
  PanelField,
  PanelLink,
  Spinner,
  Table,
  type TableColumnDef,
} from "@matthiaskrijgsman/mat-ui";
import {
  IconBriefcase,
  IconExternalLink,
  IconMapPin,
  IconWorld,
} from "@tabler/icons-react";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { ApiError } from "../api/client.ts";
import {
  isNotRunYet,
  useCareersUrl,
  useGeocode,
  useJobs,
  useLatestScrape,
  useResolveCareers,
  useResolveWebsite,
  useRunWebsiteSearch,
  useScrape,
  useScrapeJobs,
  useWebsite,
  useWebsiteSearches,
} from "../api/hooks.ts";
import type { CompanyRead, JobRead } from "../api/types.ts";
import { ErrorNote, NotRunYet, Section } from "../components/Section.tsx";
import { StatusBadge } from "../components/StatusBadge.tsx";
import { addressLine, formatDateTime } from "../lib/format.ts";

// A "run this step" button wired to a mutation's pending/error state.
function RunButton({
  mutation,
  kvk,
  label,
}: {
  mutation: UseMutationResult<unknown, ApiError, string>;
  kvk: string;
  label: string;
}) {
  return (
    <Button
      variant="secondary"
      size="sm"
      loading={mutation.isPending}
      disabled={mutation.isPending}
      onClick={() => mutation.mutate(kvk)}
    >
      {label}
    </Button>
  );
}

// Shared loading / error / not-run-yet handling for a query-backed section.
function QueryState({ query }: { query: UseQueryResult<unknown, ApiError> }) {
  if (query.isLoading) return <Spinner />;
  if (query.error && isNotRunYet(query.error))
    return <NotRunYet label="Not run yet." />;
  return <ErrorNote error={query.error} />;
}

function organicCount(results: Record<string, unknown> | null): number {
  const organic = results?.organic;
  return Array.isArray(organic) ? organic.length : 0;
}

export function WebsiteSearchSection({ kvk }: { kvk: string }) {
  const query = useWebsiteSearches(kvk);
  const mutation = useRunWebsiteSearch();
  const latest = query.data?.[0];

  return (
    <Section
      title="1 · Website search"
      description="Serper Google search for the KVK number; raw results stored."
      action={<RunButton mutation={mutation} kvk={kvk} label="Run search" />}
    >
      <ErrorNote error={mutation.error} />
      {!latest ? (
        <QueryState query={query} />
      ) : (
        <div className="space-y-1 text-sm">
          <PanelField label="Latest" orientation="horizontal">
            <StatusBadge value={latest.status} />
          </PanelField>
          <PanelField label="Candidates" orientation="horizontal">
            {organicCount(latest.results)}
          </PanelField>
          <PanelField label="Attempts" orientation="horizontal">
            {query.data?.length}
          </PanelField>
          <PanelField label="When" orientation="horizontal">
            {formatDateTime(latest.created_at)}
          </PanelField>
          {latest.error && (
            <PanelField label="Error" orientation="horizontal">
              {latest.error}
            </PanelField>
          )}
        </div>
      )}
    </Section>
  );
}

export function ResolveWebsiteSection({ kvk }: { kvk: string }) {
  const query = useWebsite(kvk);
  const mutation = useResolveWebsite();
  const w = query.data;

  return (
    <Section
      title="2 · Resolve website"
      description="LLM picks the company's own homepage from the search results."
      action={<RunButton mutation={mutation} kvk={kvk} label="Resolve" />}
    >
      <ErrorNote error={mutation.error} />
      {!w ? (
        <QueryState query={query} />
      ) : (
        <div className="space-y-1 text-sm">
          <PanelField label="Homepage" orientation="horizontal">
            {w.homepage_url ? (
              <PanelLink href={w.homepage_url} Icon={IconWorld}>
                {w.homepage_url}
              </PanelLink>
            ) : (
              <span className="text-gray-400">no confident match</span>
            )}
          </PanelField>
          <PanelField label="Confidence" orientation="horizontal">
            <StatusBadge value={w.confidence} />
          </PanelField>
          <PanelField label="Reason" orientation="horizontal">
            {w.reason}
          </PanelField>
          <PanelField label="Model" orientation="horizontal">
            {w.llm_model || "—"}
          </PanelField>
        </div>
      )}
    </Section>
  );
}

export function ScrapeSection({ kvk }: { kvk: string }) {
  const query = useLatestScrape(kvk);
  const mutation = useScrape();
  const scrape = query.data;

  return (
    <Section
      title="3 · Scrape homepage"
      description="Tier-1 httpx fetch; HTML to disk, markdown to the database."
      action={
        <RunButton mutation={mutation} kvk={kvk} label="Scrape" />
      }
    >
      <ErrorNote error={mutation.error} />
      {!scrape ? (
        <QueryState query={query} />
      ) : (
        <div className="space-y-1 text-sm">
          <PanelField label="Status" orientation="horizontal">
            <StatusBadge value={scrape.status} />
          </PanelField>
          {scrape.pages.map((p) => (
            <PanelField key={p.id} label={p.title || "page"} orientation="horizontal">
              <span className="flex items-center gap-2">
                <StatusBadge value={p.status} />
                {p.markdown != null && (
                  <span className="text-gray-400">
                    {p.markdown.length.toLocaleString()} md chars
                  </span>
                )}
              </span>
            </PanelField>
          ))}
          <PanelField label="When" orientation="horizontal">
            {formatDateTime(scrape.created_at)}
          </PanelField>
        </div>
      )}
    </Section>
  );
}

export function CareersSection({ kvk }: { kvk: string }) {
  const query = useCareersUrl(kvk);
  const mutation = useResolveCareers();
  const c = query.data;

  return (
    <Section
      title="4 · Resolve careers URL"
      description="LLM picks a same-domain careers page from the homepage links."
      action={<RunButton mutation={mutation} kvk={kvk} label="Resolve" />}
    >
      <ErrorNote error={mutation.error} />
      {!c ? (
        <QueryState query={query} />
      ) : (
        <div className="space-y-1 text-sm">
          <PanelField label="Careers URL" orientation="horizontal">
            {c.url ? (
              <PanelLink href={c.url} Icon={IconBriefcase}>
                {c.url}
              </PanelLink>
            ) : (
              <span className="text-gray-400">no same-domain careers page</span>
            )}
          </PanelField>
          <PanelField label="Confidence" orientation="horizontal">
            <StatusBadge value={c.confidence} />
          </PanelField>
          <PanelField label="Reason" orientation="horizontal">
            {c.reason}
          </PanelField>
        </div>
      )}
    </Section>
  );
}

const JOB_COLUMNS: TableColumnDef<JobRead>[] = [
  { id: "title", header: "Title", defaultWidth: 280, renderCell: (j) => j.title },
  {
    id: "type",
    header: "Type",
    defaultWidth: 120,
    renderCell: (j) => <StatusBadge value={j.employment_type} />,
  },
  {
    id: "location",
    header: "Location",
    defaultWidth: 150,
    renderCell: (j) => j.location ?? "—",
  },
  {
    id: "link",
    header: "",
    defaultWidth: 60,
    renderCell: (j) =>
      j.url ? (
        <a href={j.url} target="_blank" rel="noreferrer">
          <IconExternalLink size={16} className="text-gray-400" />
        </a>
      ) : null,
  },
];

export function JobsSection({ kvk }: { kvk: string }) {
  const query = useJobs(kvk);
  const mutation = useScrapeJobs();
  const scrape = query.data;

  return (
    <Section
      title="5 · Scrape jobs"
      description="Fetch the careers page; LLM extracts open positions."
      action={
        <RunButton mutation={mutation} kvk={kvk} label="Scrape jobs" />
      }
    >
      <ErrorNote error={mutation.error} />
      {!scrape ? (
        <QueryState query={query} />
      ) : (
        <div className="space-y-2 text-sm">
          <PanelField label="Status" orientation="horizontal">
            <StatusBadge value={scrape.status} />
          </PanelField>
          {scrape.jobs.length > 0 && (
            <Table<JobRead>
              columns={JOB_COLUMNS}
              rows={scrape.jobs}
              getRowId={(j) => j.id}
            />
          )}
          <PanelField label="When" orientation="horizontal">
            {formatDateTime(scrape.created_at)}
          </PanelField>
        </div>
      )}
    </Section>
  );
}

export function GeocodeSection({
  kvk,
  company,
}: {
  kvk: string;
  company: CompanyRead;
}) {
  const mutation = useGeocode();

  return (
    <Section
      title="6 · Geocode"
      description="PDOK Locatieserver fills lat/lon for each address."
      action={<RunButton mutation={mutation} kvk={kvk} label="Geocode" />}
    >
      <ErrorNote error={mutation.error} />
      <div className="space-y-2 text-sm">
        {company.addresses.length === 0 && (
          <span className="text-gray-400">No addresses.</span>
        )}
        {company.addresses.map((a, i) => (
          <PanelField key={i} label={<IconMapPin size={16} />} orientation="horizontal">
            <div>
              <div>{addressLine(a)}</div>
              <div className="text-gray-400">
                {a.lat && a.lon
                  ? `${a.lat}, ${a.lon} · geocoded ${formatDateTime(a.geocoded_at)}`
                  : "not geocoded"}
              </div>
            </div>
          </PanelField>
        ))}
      </div>
    </Section>
  );
}
