import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import Analytics from "./pages/Analytics";
import CustomerDetail from "./pages/CustomerDetail";
import Customers from "./pages/Customers";
import Dashboard from "./pages/Dashboard";
import DealDetail from "./pages/DealDetail";
import Login from "./pages/Login";
import MemoryExplorer from "./pages/MemoryExplorer";
import Pipeline from "./pages/Pipeline";
import Recommendations from "./pages/Recommendations";
import SearchResults from "./pages/SearchResults";
import Settings from "./pages/Settings";

export default function App() {
  const { session, loading } = useAuth();

  if (loading) return <Loading label="Restoring session…" />;

  if (!session) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/deals/:dealId" element={<DealDetail />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/customers/:customerId" element={<CustomerDetail />} />
        <Route path="/recommendations" element={<Recommendations />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/memory" element={<MemoryExplorer />} />
        <Route path="/search" element={<SearchResults />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
