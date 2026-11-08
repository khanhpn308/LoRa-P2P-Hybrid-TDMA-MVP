"use client";

import React, { useState, useMemo, useEffect, useCallback, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { NavItemKey } from "@/components/layout/Sidebar";
import {
  ChevronRight,
  ChevronDown,
  Search,
  Calendar,
  ArrowUpDown,
  CheckCircle2,
  Bell,
  RefreshCw,
} from "lucide-react";
import { AlertSeverity, AlertAckStatus, AlertTriggeredPayload } from "@/types/api";
import { getAlerts, acknowledgeAlert as apiAcknowledgeAlert } from "@/lib/api/alerts";
import { useAuth } from "@/lib/auth/AuthContext";
import { useRealtime } from "@/lib/realtime/RealtimeContext";
import { ApiClientError } from "@/lib/api/client";

export interface FaultEvent {
  id: string; // alert_id
  node_id: number;
  node: string;
  gateway: string;
  area: string;
  timestamp: string; // triggered_at
  rawTimestamp: number;
  faultType: "Nhiệt độ" | "Tốc độ";
  severity: AlertSeverity;
  thresholdValue: string;
  duration: string;
  ack_status: AlertAckStatus;
  acknowledged_at: string | null;
}

function MonitoringContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, role } = useAuth();
  const { subscribe } = useRealtime();

  // URL query params initialization (e.g. from Overview card navigation)
  const initialType = searchParams.get("type") || "all";
  const initialArea = searchParams.get("area") || "all";

  const [activeRoute, setActiveRoute] = useState<NavItemKey>("monitoring");
  const [events, setEvents] = useState<FaultEvent[]>([]);
  const [selectedArea, setSelectedArea] = useState<string>(initialArea);
  const [selectedFaultType, setSelectedFaultType] = useState<string>(
    initialType === "temp" ? "Nhiệt độ" : initialType === "speed" ? "Tốc độ" : "all"
  );
  const [selectedTimeRange, setSelectedTimeRange] = useState<string>("today");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [sortAscending, setSortAscending] = useState<boolean>(false);
  const [rowsPerPage, setRowsPerPage] = useState<number>(10);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("--:--:--");
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const loadAlerts = useCallback(async () => {
    setIsLoading(true);
    try {
      const resp = await getAlerts({ limit: 50 });
      if (resp && resp.items) {
        const mapped: FaultEvent[] = resp.items.map((a) => {
          const isTemp = a.event_code === 1;
          const trigger = a.trigger;
          let threshold: string;
          if (trigger) {
            threshold = `${trigger.observed_raw} (ngưỡng ${trigger.threshold_raw})`;
          } else if (isTemp) {
            threshold = `${(a.event_value / 10).toFixed(1)} °C`;
          } else {
            threshold = `${a.event_value} rpm`;
          }

          const triggeredDate = a.triggered_at ? new Date(a.triggered_at) : new Date(a.received_at);

          return {
            id: a.alert_id,
            node_id: a.node_id,
            node: `N-${String(a.node_id).padStart(3, "0")}`,
            gateway: a.gateway_id || "GW-01",
            area: "Khu vực cảm biến",
            timestamp: triggeredDate.toLocaleString("vi-VN"),
            rawTimestamp: Math.floor(triggeredDate.getTime() / 1000),
            faultType: isTemp ? "Nhiệt độ" : "Tốc độ",
            severity: a.severity,
            thresholdValue: threshold,
            duration: "30 s",
            ack_status: a.ack_status,
            acknowledged_at: a.acked_at ? new Date(a.acked_at).toLocaleString("vi-VN") : null,
          };
        });
        setEvents(mapped);
      } else {
        setEvents([]);
      }
    } catch {
      setEvents([]);
    } finally {
      const now = new Date();
      setLastUpdated(now.toTimeString().split(" ")[0] || "--:--:--");
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAlerts();

    // Listen for incoming alerts via WebSocket Hub
    const unsubscribe = subscribe((envelope) => {
      if (envelope.type === "ALERT_TRIGGERED") {
        const payload = envelope.payload as AlertTriggeredPayload;
        const now = new Date();
        const isTemp = payload.event_code === 1;
        const newEv: FaultEvent = {
          id: payload.alert_id,
          node_id: payload.node_id,
          node: `N-${String(payload.node_id).padStart(3, "0")}`,
          gateway: payload.gateway_id,
          area: "Khu vực cảm biến",
          timestamp: payload.triggered_at
            ? new Date(payload.triggered_at).toLocaleString("vi-VN")
            : now.toLocaleString("vi-VN"),
          rawTimestamp: Math.floor(now.getTime() / 1000),
          faultType: isTemp ? "Nhiệt độ" : "Tốc độ",
          severity: payload.severity,
          thresholdValue: isTemp ? `${(payload.event_value / 10).toFixed(1)} °C` : `${payload.event_value} rpm`,
          duration: "10 s",
          ack_status: "UNACKNOWLEDGED",
          acknowledged_at: null,
        };
        setEvents((prev) => [newEv, ...prev.filter((e) => e.id !== newEv.id)]);
        setToastMessage(`[Realtime] Cảnh báo mới từ ${newEv.node}: ${newEv.faultType} (${newEv.severity})`);
        setTimeout(() => setToastMessage(null), 4000);
      }
    });

    return () => {
      unsubscribe();
    };
  }, [loadAlerts, subscribe]);

  const handleRouteChange = (route: NavItemKey) => {
    setActiveRoute(route);
    if (route === "overview") {
      router.push("/");
    }
  };

  const handleAcknowledgeAlert = async (e: React.MouseEvent, alertId: string) => {
    e.stopPropagation();

    // Client-side RBAC Guard (ADR-0005)
    if (role === "VIEWER") {
      setToastMessage("Quyền VIEWER chỉ có quyền xem, không được phép xác nhận cảnh báo.");
      setTimeout(() => setToastMessage(null), 3500);
      return;
    }

    try {
      await apiAcknowledgeAlert(alertId, user?.username || "operator");
      const nowStr = new Date().toLocaleString("vi-VN");
      setEvents((prev) =>
        prev.map((ev) =>
          ev.id === alertId
            ? { ...ev, ack_status: "ACKNOWLEDGED", acknowledged_at: nowStr }
            : ev
        )
      );
      setToastMessage(`Đã xác nhận sự cố cảnh báo [${alertId}] thành công.`);
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 403) {
        setToastMessage("Lỗi 403: Bạn không có quyền xác nhận cảnh báo này.");
      } else {
        setToastMessage(`Lỗi xác nhận cảnh báo: ${err instanceof Error ? err.message : "Thất bại"}`);
      }
    } finally {
      setTimeout(() => {
        setToastMessage(null);
      }, 3500);
    }
  };

  // Filtered & Sorted events
  const filteredEvents = useMemo(() => {
    return events.filter((ev) => {
      // Area filter
      if (selectedArea !== "all" && !ev.area.includes(selectedArea)) {
        return false;
      }
      // Fault type filter
      if (selectedFaultType !== "all" && ev.faultType !== selectedFaultType) {
        return false;
      }
      // Search filter (Node or Gateway)
      if (searchQuery.trim() !== "") {
        const query = searchQuery.toLowerCase().trim();
        const matchNode = ev.node.toLowerCase().includes(query);
        const matchGateway = ev.gateway.toLowerCase().includes(query);
        if (!matchNode && !matchGateway) {
          return false;
        }
      }
      return true;
    }).sort((a, b) => {
      return sortAscending
        ? a.rawTimestamp - b.rawTimestamp
        : b.rawTimestamp - a.rawTimestamp;
    });
  }, [events, selectedArea, selectedFaultType, searchQuery, sortAscending]);

  // Pagination calculation
  const totalCount = filteredEvents.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / rowsPerPage));
  const startIndex = (currentPage - 1) * rowsPerPage;
  const paginatedEvents = filteredEvents.slice(startIndex, startIndex + rowsPerPage);

  // Row navigation: DESIGN.md §7 mandates:
  // "Entire row navigates to the relevant Node detail page, not to an incident modal."
  const handleRowClick = (event: FaultEvent) => {
    router.push(`/nodes/${encodeURIComponent(event.node)}`);
  };

  return (
    <AppShell activeRoute={activeRoute} onRouteChange={handleRouteChange}>
      <div className="space-y-4">
        {/* Page Header */}
        <section
          aria-label="Tiêu đề trang theo dõi"
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 min-h-[40px]"
        >
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold text-text-primary tracking-tight leading-8">
              Theo dõi
            </h1>
            {isLoading && (
              <RefreshCw className="w-4 h-4 text-interactive animate-spin" />
            )}
            <span className="text-[13px] font-medium text-text-secondary">
              Sự kiện cảnh báo vượt ngưỡng thông số giám sát
            </span>
          </div>

          <div className="flex items-center gap-2 text-xs text-text-secondary tabular-nums">
            <span className="w-2 h-2 rounded-full bg-state-active shrink-0 animate-pulse" />
            <span>Cập nhật lần cuối: {lastUpdated} (Trực tiếp)</span>
          </div>
        </section>

        {/* Filter Toolbar: Exactly 4 controls in single horizontal row */}
        <section
          aria-label="Bộ lọc sự kiện"
          className="bg-surface border border-border rounded-lg p-3 shadow-none w-full"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-3 w-full items-end">
            {/* Filter 1: Khu vực (approx 200px / col-span-3) */}
            <div className="lg:col-span-3">
              <label
                htmlFor="filter-area"
                className="block text-xs font-medium text-text-secondary mb-1"
              >
                Khu vực
              </label>
              <div className="relative">
                <select
                  id="filter-area"
                  value={selectedArea}
                  onChange={(e) => {
                    setSelectedArea(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="w-full h-10 appearance-none bg-surface border border-border rounded-md pl-3 pr-8 text-sm text-text-primary font-medium focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer"
                >
                  <option value="all">Tất cả khu vực</option>
                  <option value="Khu A">Khu A - Phân xưởng Ép</option>
                  <option value="Khu B">Khu B - Trạm Bơm & Thủy lực</option>
                  <option value="Khu C">Khu C - Kho lạnh Công nghiệp</option>
                  <option value="Ngoài trời">Trạm Thu phát Ngoài trời</option>
                </select>
                <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>

            {/* Filter 2: Loại lỗi (col-span-2) */}
            <div className="lg:col-span-2">
              <label
                htmlFor="filter-type"
                className="block text-xs font-medium text-text-secondary mb-1"
              >
                Loại lỗi
              </label>
              <div className="relative">
                <select
                  id="filter-type"
                  value={selectedFaultType}
                  onChange={(e) => {
                    setSelectedFaultType(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="w-full h-10 appearance-none bg-surface border border-border rounded-md pl-3 pr-8 text-sm text-text-primary font-medium focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer"
                >
                  <option value="all">Tất cả</option>
                  <option value="Nhiệt độ">Nhiệt độ</option>
                  <option value="Tốc độ">Tốc độ</option>
                </select>
                <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>

            {/* Filter 3: Thời gian (col-span-3) */}
            <div className="lg:col-span-3">
              <label
                htmlFor="filter-time"
                className="block text-xs font-medium text-text-secondary mb-1"
              >
                Thời gian
              </label>
              <div className="relative flex items-center">
                <div className="absolute left-3 text-text-secondary pointer-events-none">
                  <Calendar className="w-4 h-4" />
                </div>
                <select
                  id="filter-time"
                  value={selectedTimeRange}
                  onChange={(e) => setSelectedTimeRange(e.target.value)}
                  className="w-full h-10 appearance-none bg-surface border border-border rounded-md pl-9 pr-8 text-sm text-text-primary font-medium focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer tabular-nums"
                >
                  <option value="today">Hôm nay (06/11/2026)</option>
                  <option value="24h">24 giờ qua</option>
                  <option value="7d">7 ngày qua</option>
                  <option value="30d">30 ngày qua</option>
                </select>
                <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>

            {/* Filter 4: Tìm kiếm (col-span-4 to fill width) */}
            <div className="lg:col-span-4">
              <label
                htmlFor="filter-search"
                className="block text-xs font-medium text-text-secondary mb-1"
              >
                Tìm kiếm
              </label>
              <div className="relative flex items-center">
                <div className="absolute left-3 text-text-secondary pointer-events-none">
                  <Search className="w-4 h-4" />
                </div>
                <input
                  id="filter-search"
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setCurrentPage(1);
                  }}
                  placeholder="Tìm Gateway hoặc Node"
                  className="w-full h-10 bg-surface border border-border rounded-md pl-9 pr-3 text-sm text-text-primary placeholder:text-text-secondary/60 focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Main Data Table Container (DESIGN.md §7: Required columns in order) */}
        <section
          aria-label="Danh sách sự kiện lỗi"
          className="bg-surface border border-border rounded-lg overflow-hidden shadow-none flex flex-col justify-between"
        >
          <div className="overflow-x-auto w-full">
            <table className="w-full text-left border-collapse table-fixed min-w-[768px]">
              <thead>
                <tr className="h-11 bg-canvas/60 border-b border-border text-[13px] font-medium text-text-secondary">
                  {/* Column 1: Thời gian (18%) */}
                  <th
                    scope="col"
                    className="pl-5 pr-3 py-2 font-medium"
                    style={{ width: "18%" }}
                  >
                    <button
                      type="button"
                      onClick={() => setSortAscending(!sortAscending)}
                      className="flex items-center gap-1.5 hover:text-text-primary transition-colors focus:outline-none"
                      title="Sắp xếp thời gian"
                    >
                      <span>Thời gian</span>
                      <ArrowUpDown className="w-3.5 h-3.5 text-interactive" />
                    </button>
                  </th>

                  {/* Column 2: Khu vực (14%) */}
                  <th
                    scope="col"
                    className="px-3 py-2 font-medium"
                    style={{ width: "14%" }}
                  >
                    Khu vực
                  </th>

                  {/* Column 3: Gateway (11%) */}
                  <th
                    scope="col"
                    className="px-3 py-2 font-medium"
                    style={{ width: "11%" }}
                  >
                    Gateway
                  </th>

                  {/* Column 4: Node (10%) */}
                  <th
                    scope="col"
                    className="px-3 py-2 font-medium"
                    style={{ width: "10%" }}
                  >
                    Node
                  </th>

                  {/* Column 5: Loại lỗi (13%) */}
                  <th
                    scope="col"
                    className="px-3 py-2 font-medium"
                    style={{ width: "13%" }}
                  >
                    Loại lỗi
                  </th>

                  {/* Column 6: TB vượt ngưỡng (16%) */}
                  <th
                    scope="col"
                    className="px-3 py-2 font-medium text-right"
                    style={{ width: "16%" }}
                  >
                    TB vượt ngưỡng
                  </th>

                  {/* Column 7: Xác nhận sự cố (20%) */}
                  <th
                    scope="col"
                    className="px-3 py-2 font-medium"
                    style={{ width: "20%" }}
                  >
                    Xác nhận sự cố
                  </th>

                  {/* Column 8: Action right chevron (4%) */}
                  <th
                    scope="col"
                    className="pr-4 pl-1 py-2 text-center"
                    style={{ width: "4%" }}
                  ></th>
                </tr>
              </thead>

              <tbody className="divide-y divide-border text-sm">
                {paginatedEvents.length === 0 ? (
                  <tr>
                    <td
                      colSpan={8}
                      className="h-32 text-center text-text-secondary text-sm"
                    >
                      Không tìm thấy sự kiện lỗi nào phù hợp với bộ lọc.
                    </td>
                  </tr>
                ) : (
                  paginatedEvents.map((ev) => (
                    <tr
                      key={ev.id}
                      onClick={() => handleRowClick(ev)}
                      title="Nhấp để xem chi tiết Node"
                      className="h-12 hover:bg-canvas/50 transition-colors cursor-pointer group"
                    >
                      {/* 1. Thời gian */}
                      <td className="pl-5 pr-3 py-2 tabular-nums text-text-primary whitespace-nowrap overflow-hidden text-ellipsis">
                        {ev.timestamp}
                      </td>

                      {/* 2. Khu vực */}
                      <td className="px-3 py-2 text-text-secondary whitespace-nowrap overflow-hidden text-ellipsis">
                        {ev.area}
                      </td>

                      {/* 3. Gateway */}
                      <td className="px-3 py-2 font-medium tabular-nums text-text-primary whitespace-nowrap">
                        {ev.gateway}
                      </td>

                      {/* 4. Node (Pill badge) */}
                      <td className="px-3 py-2 whitespace-nowrap">
                        <Link
                          href={`/nodes/${encodeURIComponent(ev.node)}`}
                          onClick={(e) => e.stopPropagation()}
                          title={`Xem thông tin chi tiết Node ${ev.node}`}
                          className="inline-flex items-center px-2 py-0.5 rounded text-[13px] font-mono font-medium tabular-nums text-interactive bg-blue-50 dark:bg-blue-950/70 border border-blue-200 dark:border-blue-800/80 hover:bg-interactive hover:text-white dark:hover:bg-interactive dark:hover:text-white transition-colors cursor-pointer"
                        >
                          {ev.node}
                        </Link>
                      </td>

                      {/* 5. Loại lỗi */}
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1.5 text-text-primary font-medium">
                          <span className="w-2 h-2 rounded-full bg-state-critical shrink-0" />
                          <span>{ev.faultType}</span>
                        </span>
                      </td>

                      {/* 6. TB vượt ngưỡng */}
                      <td className="px-3 py-2 text-right font-semibold tabular-nums text-state-critical whitespace-nowrap">
                        {ev.thresholdValue}
                      </td>

                      {/* 7. Trạng thái xác nhận (Acknowledge Alert) */}
                      <td className="px-3 py-2 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                        {ev.ack_status === "UNACKNOWLEDGED" ? (
                          <button
                            type="button"
                            disabled={role === "VIEWER"}
                            onClick={(e) => handleAcknowledgeAlert(e, ev.id)}
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors shadow-none ${
                              role === "VIEWER"
                                ? "bg-border text-text-secondary cursor-not-allowed opacity-60"
                                : "bg-interactive hover:bg-btn-primary-hover text-white cursor-pointer"
                            }`}
                            title={
                              role === "VIEWER"
                                ? "Quyền VIEWER không thể xác nhận sự cố"
                                : "Xác nhận sự cố (POST /api/v1/alerts/{id}/acknowledge)"
                            }
                          >
                            <Bell className="w-3.5 h-3.5" />
                            <span>Xác nhận</span>
                          </button>
                        ) : (
                          <div className="flex flex-col">
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20 font-mono w-fit">
                              <CheckCircle2 className="w-3 h-3" />
                              <span>Đã xác nhận</span>
                            </span>
                            {ev.acknowledged_at && (
                              <span className="text-[10px] text-text-secondary font-mono mt-0.5">
                                {ev.acknowledged_at}
                              </span>
                            )}
                          </div>
                        )}
                      </td>

                      {/* 8. Action right chevron */}
                      <td className="pr-4 pl-1 py-2 text-center">
                        <ChevronRight className="w-4 h-4 text-text-secondary/60 group-hover:text-interactive group-hover:translate-x-0.5 transition-all inline" />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Compact Pagination Bar */}
          <div className="h-12 border-t border-border px-5 flex items-center justify-between text-[13px] text-text-secondary bg-canvas/40 w-full">
            {/* Left: Rows per page selector */}
            <div className="flex items-center gap-2">
              <span>Hiển thị</span>
              <select
                value={rowsPerPage}
                onChange={(e) => {
                  setRowsPerPage(Number(e.target.value));
                  setCurrentPage(1);
                }}
                className="bg-surface border border-border rounded px-2 py-0.5 text-[13px] text-text-primary font-medium tabular-nums cursor-pointer focus:outline-none"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
              <span>dòng mỗi trang</span>
            </div>

            {/* Right: Page navigation & counts */}
            <div className="flex items-center gap-4">
              <span className="tabular-nums font-medium text-text-primary">
                {totalCount === 0
                  ? "0 sự kiện"
                  : `${startIndex + 1}–${Math.min(
                      startIndex + rowsPerPage,
                      totalCount
                    )} / ${totalCount} sự kiện`}
              </span>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className={`w-7 h-7 rounded border border-border flex items-center justify-center transition-colors ${
                    currentPage <= 1
                      ? "bg-surface opacity-40 cursor-not-allowed text-text-secondary"
                      : "bg-surface hover:bg-canvas text-text-primary"
                  }`}
                  title="Trang trước"
                >
                  <ChevronRight className="w-3.5 h-3.5 rotate-180" />
                </button>

                <button
                  type="button"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  className={`w-7 h-7 rounded border border-border flex items-center justify-center transition-colors ${
                    currentPage >= totalPages
                      ? "bg-surface opacity-40 cursor-not-allowed text-text-secondary"
                      : "bg-surface hover:bg-canvas text-text-primary"
                  }`}
                  title="Trang kế tiếp"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Floating Context-Aware Navigation Feedback Toast */}
        {toastMessage && (
          <div
            role="status"
            aria-live="polite"
            className="fixed bottom-6 right-6 bg-[#0F172A] text-white px-4 py-3 rounded-lg text-xs font-medium shadow-xl border border-slate-700 flex items-center gap-2.5 z-50 animate-in fade-in slide-in-from-bottom-2 duration-200"
          >
            <CheckCircle2 className="w-4 h-4 text-blue-400 shrink-0" />
            <span>{toastMessage}</span>
          </div>
        )}
      </div>
    </AppShell>
  );
}

export default function MonitoringPage() {
  return (
    <Suspense fallback={<div className="p-6 text-text-secondary">Đang tải dữ liệu theo dõi...</div>}>
      <MonitoringContent />
    </Suspense>
  );
}

