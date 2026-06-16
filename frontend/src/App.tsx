import { Link, NavLink, Route, Routes } from "react-router-dom";
import { IconBuildingWarehouse } from "@tabler/icons-react";

import { CompaniesPage } from "./pages/CompaniesPage.tsx";
import { CompanyPage } from "./pages/CompanyPage.tsx";
import { MapPage } from "./pages/MapPage.tsx";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive
    ? "text-gray-900 font-medium"
    : "text-gray-500 hover:text-gray-800";
}

export function App() {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-6 py-3">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <IconBuildingWarehouse size={20} className="text-gray-500" />
            company-indexer
          </Link>
          <span className="text-xs text-gray-400">dev console</span>
          <nav className="ml-auto flex items-center gap-4 text-sm">
            <NavLink to="/" end className={navClass}>
              Companies
            </NavLink>
            <NavLink to="/map" className={navClass}>
              Map
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-6">
        <Routes>
          <Route path="/" element={<CompaniesPage />} />
          <Route path="/companies/:kvk" element={<CompanyPage />} />
          <Route path="/map" element={<MapPage />} />
        </Routes>
      </main>
    </div>
  );
}
