import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { apiGet, apiPost, ApiError } from "./client";
import type {
  CompanyCareersUrlRead,
  CompanyListResponse,
  CompanyRead,
  JobsScrapeRead,
  WebsiteRead,
  WebsiteScrapeRead,
  WebsiteSearchDetail,
} from "./types";

const enc = encodeURIComponent;

// Centralized query keys so mutations can invalidate precisely.
export const keys = {
  companies: (q: string, limit: number, offset: number) =>
    ["companies", { q, limit, offset }] as const,
  company: (kvk: string) => ["company", kvk] as const,
  websiteSearches: (kvk: string) => ["website-searches", kvk] as const,
  website: (kvk: string) => ["website", kvk] as const,
  scrape: (kvk: string) => ["scrape", kvk] as const,
  careersUrl: (kvk: string) => ["careers-url", kvk] as const,
  jobs: (kvk: string) => ["jobs", kvk] as const,
};

/** True when a GET legitimately 404s because the step hasn't been run yet. */
export function isNotRunYet(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

// Shared options for "latest result" GETs that 404 until their step has run.
// We don't retry those — a 404 is an expected, meaningful state.
function latestResultOptions<T>(): Partial<UseQueryOptions<T, ApiError>> {
  return {
    retry: (count, error) => !(error instanceof ApiError) && count < 2,
  };
}

// ---- Queries ----

export function useCompanies(q: string, limit = 50, offset = 0) {
  return useQuery<CompanyListResponse, ApiError>({
    queryKey: keys.companies(q, limit, offset),
    queryFn: () => {
      const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
      });
      if (q) params.set("q", q);
      return apiGet<CompanyListResponse>(`/companies?${params}`);
    },
  });
}

export function useCompany(kvk: string) {
  return useQuery<CompanyRead, ApiError>({
    queryKey: keys.company(kvk),
    queryFn: () => apiGet<CompanyRead>(`/companies/${enc(kvk)}`),
  });
}

export function useWebsiteSearches(kvk: string) {
  return useQuery<WebsiteSearchDetail[], ApiError>({
    queryKey: keys.websiteSearches(kvk),
    queryFn: () =>
      apiGet<WebsiteSearchDetail[]>(`/companies/${enc(kvk)}/website-search`),
  });
}

export function useWebsite(kvk: string) {
  return useQuery<WebsiteRead, ApiError>({
    queryKey: keys.website(kvk),
    queryFn: () => apiGet<WebsiteRead>(`/companies/${enc(kvk)}/website`),
    ...latestResultOptions<WebsiteRead>(),
  });
}

export function useLatestScrape(kvk: string) {
  return useQuery<WebsiteScrapeRead, ApiError>({
    queryKey: keys.scrape(kvk),
    queryFn: () => apiGet<WebsiteScrapeRead>(`/companies/${enc(kvk)}/scrape`),
    ...latestResultOptions<WebsiteScrapeRead>(),
  });
}

export function useCareersUrl(kvk: string) {
  return useQuery<CompanyCareersUrlRead, ApiError>({
    queryKey: keys.careersUrl(kvk),
    queryFn: () =>
      apiGet<CompanyCareersUrlRead>(`/companies/${enc(kvk)}/careers-url`),
    ...latestResultOptions<CompanyCareersUrlRead>(),
  });
}

export function useJobs(kvk: string) {
  return useQuery<JobsScrapeRead, ApiError>({
    queryKey: keys.jobs(kvk),
    queryFn: () => apiGet<JobsScrapeRead>(`/companies/${enc(kvk)}/jobs`),
    ...latestResultOptions<JobsScrapeRead>(),
  });
}

// ---- Mutations (each invalidates the GET(s) it affects) ----

function useEnrichmentMutation<T>(
  path: (kvk: string) => string,
  invalidate: (kvk: string) => ReadonlyArray<readonly unknown[]>,
) {
  const qc = useQueryClient();
  return useMutation<T, ApiError, string>({
    mutationFn: (kvk: string) => apiPost<T>(path(kvk)),
    onSuccess: (_data, kvk) => {
      for (const key of invalidate(kvk)) {
        void qc.invalidateQueries({ queryKey: key });
      }
    },
  });
}

export const useRunWebsiteSearch = () =>
  useEnrichmentMutation<WebsiteSearchDetail>(
    (kvk) => `/companies/${enc(kvk)}/website-search`,
    (kvk) => [keys.websiteSearches(kvk)],
  );

export const useResolveWebsite = () =>
  useEnrichmentMutation<WebsiteRead>(
    (kvk) => `/companies/${enc(kvk)}/resolve-website`,
    (kvk) => [keys.website(kvk)],
  );

export const useScrape = () =>
  useEnrichmentMutation<WebsiteScrapeRead>(
    (kvk) => `/companies/${enc(kvk)}/scrape`,
    (kvk) => [keys.scrape(kvk)],
  );

export const useResolveCareers = () =>
  useEnrichmentMutation<CompanyCareersUrlRead>(
    (kvk) => `/companies/${enc(kvk)}/resolve-careers`,
    (kvk) => [keys.careersUrl(kvk)],
  );

export const useScrapeJobs = () =>
  useEnrichmentMutation<JobsScrapeRead>(
    (kvk) => `/companies/${enc(kvk)}/scrape-jobs`,
    (kvk) => [keys.jobs(kvk)],
  );

export const useGeocode = () =>
  useEnrichmentMutation<CompanyRead>(
    (kvk) => `/companies/${enc(kvk)}/geocode`,
    (kvk) => [keys.company(kvk)],
  );
