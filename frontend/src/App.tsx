import { Navigate, Route, Routes } from "react-router-dom";
import DashboardLayout from "./layouts/DashboardLayout";
import Overview from "./pages/Overview";
import TurbineMonitoring from "./pages/TurbineMonitoring";
import PerformanceAnalytics from "./pages/PerformanceAnalytics";
import PowerCurvePage from "./pages/PowerCurvePage";
import AnomalyPage from "./pages/AnomalyPage";
import DowntimePage from "./pages/DowntimePage";
import ReportsPage from "./pages/ReportsPage";
import DataManagementPage from "./pages/DataManagementPage";

export default function App() {
  return (
    <Routes>
      <Route element={<DashboardLayout />}>
        <Route index element={<Overview />} />
        <Route path="turbines" element={<TurbineMonitoring />} />
        <Route path="performance" element={<PerformanceAnalytics />} />
        <Route path="power-curve" element={<PowerCurvePage />} />
        <Route path="anomalies" element={<AnomalyPage />} />
        <Route path="downtime" element={<DowntimePage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="data" element={<DataManagementPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
