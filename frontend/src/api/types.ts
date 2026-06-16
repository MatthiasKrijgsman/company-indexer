// TypeScript mirror of the API response schemas.
//
// ⚠️  KEEP IN SYNC BY HAND with the Pydantic schemas in
//     src/company_indexer/schemas/ (see VISION.md §5 "API reference").
//     There is no codegen — when a backend schema changes, update this file.

// ---- Enums (string unions matching the backend native enums) ----

export type NameType = "statutory" | "trade" | "short" | "alias";

export type WebsiteConfidence = "high" | "medium" | "low" | "none";

export type WebsiteSearchStatus = "success" | "failed";

export type WebsiteScrapeStatus =
  | "ok"
  | "partial"
  | "failed"
  | "skipped_no_website"
  | "skipped_js_heavy"
  | "skipped_dead_domain";

export type WebsitePageFetchMethod = "http" | "jina" | "firecrawl" | "playwright";

export type WebsitePageStatus =
  | "ok"
  | "http_4xx"
  | "http_5xx"
  | "timeout"
  | "network_error"
  | "js_required"
  | "blocked"
  | "dead_domain"
  | "non_html";

export type JobsScrapeStatus =
  | "ok"
  | "no_jobs"
  | "no_careers_page"
  | "js_required"
  | "blocked"
  | "failed"
  | "llm_error";

export type JobEmploymentType =
  | "full_time"
  | "part_time"
  | "contract"
  | "internship"
  | "unknown";

// ---- Core company ----

export interface CompanyNameRead {
  name: string;
  type: NameType;
}

export interface AddressRead {
  street: string | null;
  house_number: string | null;
  postcode: string | null;
  city: string | null;
  country: string;
  // Decimals are serialized as JSON strings by Pydantic.
  lat: string | null;
  lon: string | null;
  geocoded_at: string | null;
}

export interface CompanyRead {
  kvk_number: string;
  names: CompanyNameRead[];
  addresses: AddressRead[];
}

export interface CompanyListResponse {
  items: CompanyRead[];
  limit: number;
  offset: number;
}

// ---- Website search & resolution ----

export interface WebsiteSearchDetail {
  id: number;
  query: string;
  status: WebsiteSearchStatus;
  error: string | null;
  results: Record<string, unknown> | null;
  created_at: string;
}

export interface WebsiteRead {
  id: number;
  source_search_id: number;
  url: string | null;
  homepage_url: string | null;
  confidence: WebsiteConfidence;
  reason: string;
  llm_model: string;
  created_at: string;
}

// ---- Website scrape ----

export interface WebsitePageRead {
  id: number;
  url: string;
  normalized_url: string;
  fetch_method: WebsitePageFetchMethod;
  status: WebsitePageStatus;
  http_status: number | null;
  content_type: string | null;
  content_hash: string | null;
  title: string | null;
  markdown: string | null;
  fetched_at: string;
}

export interface WebsiteScrapeRead {
  id: number;
  source_website_id: number;
  status: WebsiteScrapeStatus;
  pages_attempted: number;
  pages_ok: number;
  pages_failed: number;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
  pages: WebsitePageRead[];
}

// ---- Careers & jobs ----

export interface CompanyCareersUrlRead {
  id: number;
  source_scrape_id: number;
  url: string | null;
  confidence: WebsiteConfidence;
  reason: string;
  llm_model: string;
  created_at: string;
}

export interface JobRead {
  id: number;
  title: string;
  url: string | null;
  careers_url: string;
  location: string | null;
  employment_type: JobEmploymentType;
  department: string | null;
  raw_snippet: string | null;
  created_at: string;
}

export interface JobsScrapeRead {
  id: number;
  source_careers_id: number;
  fetched_url: string;
  status: JobsScrapeStatus;
  http_status: number | null;
  content_hash: string | null;
  llm_model: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
  jobs: JobRead[];
}
