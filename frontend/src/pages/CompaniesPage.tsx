import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Input,
  Spinner,
  Table,
  TableEmpty,
  type TableColumnDef,
} from "@matthiaskrijgsman/mat-ui";
import { IconSearch, IconBuildingSkyscraper } from "@tabler/icons-react";

import { useCompanies } from "../api/hooks.ts";
import type { CompanyRead } from "../api/types.ts";
import { ErrorNote } from "../components/Section.tsx";
import { firstCity, primaryName } from "../lib/format.ts";
import { useDebounce } from "../lib/useDebounce.ts";

export function CompaniesPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const q = useDebounce(search.trim(), 300);

  const { data, isLoading, error } = useCompanies(q);

  const columns = useMemo<TableColumnDef<CompanyRead>[]>(
    () => [
      {
        id: "kvk",
        header: "KVK",
        defaultWidth: 130,
        renderCell: (c) => <span className="font-mono">{c.kvk_number}</span>,
      },
      {
        id: "name",
        header: "Name",
        defaultWidth: 320,
        renderCell: (c) => primaryName(c.names),
      },
      {
        id: "city",
        header: "City",
        defaultWidth: 160,
        renderCell: (c) => firstCity(c.addresses),
      },
      {
        id: "names",
        header: "# names",
        defaultWidth: 90,
        renderCell: (c) => c.names.length,
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-lg font-semibold">Companies</h1>
        <div className="w-72">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name…"
            Icon={IconSearch}
          />
        </div>
      </div>

      <ErrorNote error={error} />

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : (
        <Table<CompanyRead>
          columns={columns}
          rows={data?.items ?? []}
          getRowId={(c) => c.kvk_number}
          onRowClick={(c) => navigate(`/companies/${c.kvk_number}`)}
          emptyState={
            <TableEmpty
              Icon={IconBuildingSkyscraper}
              title="No companies"
              description={
                q
                  ? `No company name matches “${q}”.`
                  : "Seed the database, then refresh."
              }
            />
          }
        />
      )}
    </div>
  );
}
