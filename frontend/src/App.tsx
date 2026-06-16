import { Link, Route, Routes } from "react-router-dom";
import { IconBuildingWarehouse } from "@tabler/icons-react";

import { CompaniesPage } from "./pages/CompaniesPage.tsx";
import { CompanyPage } from "./pages/CompanyPage.tsx";

export function App() {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-2 px-6 py-3">
          <IconBuildingWarehouse size={20} className="text-gray-500" />
          <Link to="/" className="font-semibold">
            company-indexer
          </Link>
          <span className="text-xs text-gray-400">dev console</span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-6">
        <Routes>
          <Route path="/" element={<CompaniesPage />} />
          <Route path="/companies/:kvk" element={<CompanyPage />} />
        </Routes>
      </main>
    </div>
  );
}
