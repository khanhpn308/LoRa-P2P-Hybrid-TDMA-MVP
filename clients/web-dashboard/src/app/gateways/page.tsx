"use client";

import React, { useState, useMemo, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { NavItemKey } from "@/components/layout/Sidebar";
import { GatewayMode, GatewayStatusChangedPayload } from "@/types/api";
import { getGateways, createGateway } from "@/lib/api/gateways";
import { useRealtime } from "@/lib/realtime/RealtimeContext";
import {
  Search,
  Plus,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Router,
  CheckCircle2,
  X,
} from "lucide-react";

export interface GatewayItem {
  id: string;
  name: string;
  connected: boolean;
  operating: boolean;
  mode: GatewayMode;
  activeScheduleVersion: number;
  lastSeenAt: string | null;
  rfDutyPermille: number;
  nodeCount: number;
  areaCount: number;
  primaryArea: string;
  frequency: string;
  channel: number;
}

function GatewaysContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { subscribe } = useRealtime();

  // URL query params initialization (e.g. from Overview Gateway card click)
  const initialConn = searchParams.get("conn") || "all";
  const initialOps = searchParams.get("ops") || "all";
  const initialQuery = searchParams.get("q") || "";

  const [activeRoute, setActiveRoute] = useState<NavItemKey>("gateways");
  const [gateways, setGateways] = useState<GatewayItem[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>(initialQuery);
  const [connFilter, setConnFilter] = useState<string>(initialConn);
  const [opsFilter, setOpsFilter] = useState<string>(initialOps);
  const [rowsPerPage, setRowsPerPage] = useState<number>(10);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [showAddGatewayModal, setShowAddGatewayModal] = useState<boolean>(false);
  const [newGwId, setNewGwId] = useState<string>("");
  const [newGwName, setNewGwName] = useState<string>("");
  const [newGwLocation, setNewGwLocation] = useState<string>("");
  const [newGwIp, setNewGwIp] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const loadGateways = useCallback(async () => {
    try {
      const realGws = await getGateways();
      const mapped: GatewayItem[] = (realGws || []).map((rg) => ({
        id: rg.gateway_id,
        name: rg.name || `Trạm ${rg.gateway_id}`,
        connected: rg.mode !== "OFFLINE",
        operating: rg.mode === "ACTIVE" || rg.mode === "AUTONOMOUS",
        mode: rg.mode,
        activeScheduleVersion: rg.active_schedule_version,
        lastSeenAt: rg.last_seen_at,
        rfDutyPermille: rg.rf_duty_permille,
        nodeCount: rg.node_count,
        areaCount: 1,
        primaryArea: rg.location || "Khu vực chung",
        frequency: `${rg.frequency_hz ? (rg.frequency_hz / 1e6).toFixed(3) : "920.500"} MHz`,
        channel: typeof rg.channel_id === "string" ? parseInt(rg.channel_id.replace(/\D/g, "") || "1", 10) : Number(rg.channel_id) || 1,
      }));
      setGateways(mapped);
    } catch {
      setGateways([]);
    }
  }, []);

  useEffect(() => {
    loadGateways();

    const unsubscribe = subscribe((envelope) => {
      if (envelope.type === "GATEWAY_STATUS_CHANGED") {
        const payload = envelope.payload as GatewayStatusChangedPayload;
        setGateways((prev) =>
          prev.map((gw) =>
            gw.id === payload.gateway_id
              ? {
                  ...gw,
                  mode: payload.mode,
                  connected: payload.mode !== "OFFLINE",
                  operating: payload.mode === "ACTIVE" || payload.mode === "AUTONOMOUS",
                  lastSeenAt: payload.last_seen_at,
                }
              : gw
          )
        );
        setToastMessage(`[Realtime] Gateway ${payload.gateway_id} chuyển sang: ${payload.mode}`);
        setTimeout(() => setToastMessage(null), 3500);
      }
    });

    return () => {
      unsubscribe();
    };
  }, [loadGateways, subscribe]);

  const handleRouteChange = (route: NavItemKey) => {
    setActiveRoute(route);
    if (route === "overview") {
      router.push("/");
    } else if (route === "monitoring") {
      router.push("/monitoring");
    }
  };

  // Filtered gateways based on the 3 independent controls
  const filteredGateways = useMemo(() => {
    return gateways.filter((gw) => {
      // 1. Search Query filter (matches ID or Name)
      if (searchQuery.trim() !== "") {
        const q = searchQuery.toLowerCase().trim();
        const matchId = gw.id.toLowerCase().includes(q);
        const matchName = gw.name.toLowerCase().includes(q);
        if (!matchId && !matchName) return false;
      }

      // 2. Connection Status filter (Đã kết nối / Mất kết nối)
      if (connFilter === "connected" && !gw.connected) return false;
      if (connFilter === "disconnected" && gw.connected) return false;

      // 3. Operating Status filter (Đang hoạt động / Không hoạt động)
      if (opsFilter === "active" && !gw.operating) return false;
      if (opsFilter === "inactive" && gw.operating) return false;

      return true;
    });
  }, [gateways, searchQuery, connFilter, opsFilter]);

  // Pagination calculation
  const totalCount = filteredGateways.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / rowsPerPage));
  const startIndex = (currentPage - 1) * rowsPerPage;
  const paginatedGateways = filteredGateways.slice(startIndex, startIndex + rowsPerPage);

  // Row navigation: DESIGN.md §7:
  // "Rows navigate to Gateway detail. Gateway provisioning form is a separate subsequent design task."
  const handleRowClick = (gw: GatewayItem) => {
    router.push(`/gateways/${gw.id}`);
  };

  const handleOpenAddModal = () => {
    setShowAddGatewayModal(true);
  };

  return (
    <AppShell activeRoute={activeRoute} onRouteChange={handleRouteChange}>
      <div className="space-y-4">
        {/* PAGE HEADER: Title, Subtitle & Primary Action Button (DESIGN.md §7) */}
        <section
          aria-label="Tiêu đề quản lý Gateway"
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 min-h-[40px]"
        >
          <div className="flex flex-col gap-0.5">
            <h1 className="text-2xl font-semibold text-text-primary tracking-tight leading-8">
              Gateway
            </h1>
            <p className="text-xs text-text-secondary">
              Danh sách trạm trung chuyển dữ liệu LoRa TDMA toàn hệ thống
            </p>
          </div>

          <div className="flex items-center shrink-0">
            <button
              type="button"
              onClick={handleOpenAddModal}
              className="h-10 px-4 bg-interactive hover:bg-interactive-hover active:bg-blue-700 text-white font-medium text-sm rounded-lg inline-flex items-center gap-2 transition-colors shadow-none focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 focus:ring-offset-canvas"
            >
              <Plus className="w-4 h-4 shrink-0" />
              <span>Thêm Gateway</span>
            </button>
          </div>
        </section>

        {/* FILTER TOOLBAR: Exactly 3 controls (Search + 2 Independent Status Filters) */}
        <section
          aria-label="Bộ lọc Gateway"
          className="bg-surface border border-border rounded-lg p-3 shadow-none w-full"
        >
          <div className="flex flex-wrap items-center gap-3 w-full">
            {/* Control 1: Search input (matches ID or Name) */}
            <div className="relative flex-1 min-w-[240px] max-w-sm h-10">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-secondary">
                <Search className="w-4 h-4" />
              </div>
              <input
                id="gateway-search"
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                placeholder="Tìm Gateway"
                className="w-full h-10 pl-9 pr-3 bg-surface text-text-primary placeholder:text-text-secondary/60 border border-border rounded-lg text-sm font-normal focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive transition-colors"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-text-secondary hover:text-text-primary"
                  title="Xóa tìm kiếm"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Control 2: Independent Connection Status Filter */}
            <div className="relative w-44 h-10">
              <label htmlFor="filter-conn" className="sr-only">
                Bộ lọc kết nối
              </label>
              <select
                id="filter-conn"
                value={connFilter}
                onChange={(e) => {
                  setConnFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm font-medium appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive transition-colors cursor-pointer"
              >
                <option value="all">Kết nối: Tất cả</option>
                <option value="connected">Đã kết nối</option>
                <option value="disconnected">Mất kết nối</option>
              </select>
              <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>

            {/* Control 3: Independent Operating Status Filter */}
            <div className="relative w-48 h-10">
              <label htmlFor="filter-ops" className="sr-only">
                Bộ lọc hoạt động
              </label>
              <select
                id="filter-ops"
                value={opsFilter}
                onChange={(e) => {
                  setOpsFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm font-medium appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive transition-colors cursor-pointer"
              >
                <option value="all">Hoạt động: Tất cả</option>
                <option value="active">Đang hoạt động</option>
                <option value="inactive">Không hoạt động</option>
              </select>
              <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          </div>
        </section>

        {/* GATEWAY DATA TABLE: Compact table with exactly 5 required columns (DESIGN.md §7) */}
        <section
          aria-label="Danh sách Gateway"
          className="bg-surface border border-border rounded-lg overflow-hidden shadow-none flex flex-col justify-between"
        >
          <div className="overflow-x-auto w-full">
            <table className="w-full text-left border-collapse table-fixed min-w-[700px]">
              {/* Table Header */}
              <thead>
                <tr className="h-11 bg-canvas/60 border-b border-border text-[13px] font-medium text-text-secondary uppercase tracking-wider">
                  {/* Column 1: Mã Gateway (18%) */}
                  <th scope="col" className="py-2.5 pl-6 pr-4 font-semibold" style={{ width: "18%" }}>
                    Mã Gateway
                  </th>

                  {/* Column 2: Tên Gateway (32%) */}
                  <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "32%" }}>
                    Tên Gateway
                  </th>

                  {/* Column 3: Kết nối (20%) */}
                  <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "20%" }}>
                    Kết nối
                  </th>

                  {/* Column 4: Hoạt động (18%) */}
                  <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "18%" }}>
                    Hoạt động
                  </th>

                  {/* Column 5: Khu vực (12% - text-right) */}
                  <th scope="col" className="py-2.5 pr-6 pl-4 font-semibold text-right" style={{ width: "12%" }}>
                    Khu vực
                  </th>
                </tr>
              </thead>

              {/* Table Body */}
              <tbody className="divide-y divide-border text-sm">
                {paginatedGateways.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="h-32 text-center text-text-secondary text-sm">
                      Không tìm thấy Gateway nào phù hợp với bộ lọc.
                    </td>
                  </tr>
                ) : (
                  paginatedGateways.map((gw) => (
                    <tr
                      key={gw.id}
                      onClick={() => handleRowClick(gw)}
                      title={`Xem chi tiết trạm ${gw.id}`}
                      className="h-12 hover:bg-interactive-subtle/40 transition-colors cursor-pointer group focus-within:bg-interactive-subtle/40"
                    >
                      {/* 1. Mã Gateway */}
                      <td className="py-3 pl-6 pr-4 font-mono text-sm font-semibold text-interactive group-hover:underline underline-offset-2">
                        {gw.id}
                      </td>

                      {/* 2. Tên Gateway */}
                      <td className="py-3 px-4 font-medium text-text-primary">
                        <div className="flex items-center gap-2">
                          <span>{gw.name}</span>
                        </div>
                      </td>

                      {/* 3. Kết nối (Dot + Text) */}
                      <td className="py-3 px-4">
                        {gw.connected ? (
                          <div className="inline-flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-state-connected shrink-0" />
                            <span className="text-[13px] font-medium text-state-connected">
                              Đã kết nối
                            </span>
                          </div>
                        ) : (
                          <div className="inline-flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-state-critical shrink-0" />
                            <span className="text-[13px] font-medium text-state-critical">
                              Mất kết nối
                            </span>
                          </div>
                        )}
                      </td>

                      {/* 4. Hoạt động (Dot + Text) */}
                      <td className="py-3 px-4">
                        {gw.operating ? (
                          <div className="inline-flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-state-active shrink-0" />
                            <span className="text-[13px] font-medium text-state-active">
                              Đang hoạt động
                            </span>
                          </div>
                        ) : (
                          <div className="inline-flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-text-secondary/60 shrink-0" />
                            <span className="text-[13px] font-medium text-text-secondary">
                              Không hoạt động
                            </span>
                          </div>
                        )}
                      </td>

                      {/* 5. Khu vực (Number of covered areas right-aligned + chevron) */}
                      <td className="py-3 pr-6 pl-4 text-right">
                        <div className="inline-flex items-center justify-end gap-2 w-full">
                          <span className="font-mono text-sm text-text-primary tabular-nums">
                            {gw.areaCount}
                          </span>
                          <ChevronRight className="w-4 h-4 text-text-secondary group-hover:text-interactive group-hover:translate-x-0.5 transition-all shrink-0" />
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* PAGINATION FOOTER */}
          <div className="p-4 border-t border-border bg-surface flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-text-secondary">
            {/* Left: Per page selector */}
            <div className="flex items-center gap-2">
              <label htmlFor="rows-select" className="text-xs font-medium text-text-secondary">
                Hiển thị
              </label>
              <div className="relative">
                <select
                  id="rows-select"
                  value={rowsPerPage}
                  onChange={(e) => {
                    setRowsPerPage(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="h-8 pl-2.5 pr-7 bg-canvas border border-border rounded text-xs text-text-primary appearance-none focus:outline-none focus:border-interactive cursor-pointer"
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-text-secondary absolute right-1.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
              <span className="text-xs text-text-secondary">dòng mỗi trang</span>
            </div>

            {/* Right: Range readout & Navigation Controls */}
            <div className="flex items-center gap-4">
              <span className="font-mono text-xs text-text-secondary tabular-nums">
                {totalCount === 0
                  ? "0 / 0 Gateway"
                  : `${startIndex + 1}–${Math.min(startIndex + rowsPerPage, totalCount)} / ${totalCount} Gateway`}
              </span>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage <= 1}
                  className="w-8 h-8 flex items-center justify-center rounded border border-border bg-surface text-text-secondary hover:text-text-primary hover:border-interactive disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus:outline-none"
                  title="Trang trước"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage >= totalPages}
                  className="w-8 h-8 flex items-center justify-center rounded border border-border bg-surface text-text-secondary hover:text-text-primary hover:border-interactive disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus:outline-none"
                  title="Trang sau"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* Add Gateway Modal - Minimalist Action Form */}
        {showAddGatewayModal && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-add-title"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          >
            <div className="bg-surface border border-border rounded-xl shadow-none max-w-md w-full p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-border">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-interactive/10 flex items-center justify-center text-interactive">
                    <Router className="w-4 h-4" />
                  </div>
                  <h3 id="modal-add-title" className="text-base font-semibold text-text-primary">
                    Thêm Gateway mới
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setShowAddGatewayModal(false)}
                  className="p-1 rounded text-text-secondary hover:text-text-primary hover:bg-canvas transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (!newGwId.trim()) return;
                  setIsSubmitting(true);
                  try {
                    await createGateway({
                      gateway_id: newGwId.trim(),
                      name: newGwName.trim() || `Trạm điều hành ${newGwId.trim()}`,
                      location: newGwLocation.trim() || "Khu vực chung",
                      ip_address: newGwIp.trim() || undefined,
                    });
                    setShowAddGatewayModal(false);
                    setNewGwId("");
                    setNewGwName("");
                    setNewGwLocation("");
                    setNewGwIp("");
                    setToastMessage(`Đã thêm thành công Gateway ${newGwId.trim()}`);
                    setTimeout(() => setToastMessage(null), 3000);
                    await loadGateways();
                  } catch (err: unknown) {
                    setToastMessage(err instanceof Error ? err.message : "Thêm Gateway thất bại");
                    setTimeout(() => setToastMessage(null), 3000);
                  } finally {
                    setIsSubmitting(false);
                  }
                }}
              >
                <div className="space-y-3 text-xs">
                  <div>
                    <label className="block font-medium text-text-primary mb-1">Mã trạm (ID) *</label>
                    <input
                      type="text"
                      required
                      value={newGwId}
                      onChange={(e) => setNewGwId(e.target.value)}
                      placeholder="VD: GW-01 hoặc gw-a"
                      className="w-full h-10 px-3 bg-canvas border border-border rounded-lg text-text-primary font-mono text-sm focus:outline-none focus:border-interactive"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-text-primary mb-1">Tên trạm Gateway</label>
                    <input
                      type="text"
                      value={newGwName}
                      onChange={(e) => setNewGwName(e.target.value)}
                      placeholder="VD: Trạm điều hành Khu A"
                      className="w-full h-10 px-3 bg-canvas border border-border rounded-lg text-text-primary text-sm focus:outline-none focus:border-interactive"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-text-primary mb-1">Khu vực phân công</label>
                    <input
                      type="text"
                      value={newGwLocation}
                      onChange={(e) => setNewGwLocation(e.target.value)}
                      placeholder="VD: Khu A - Phân xưởng Ép"
                      className="w-full h-10 px-3 bg-canvas border border-border rounded-lg text-text-primary text-sm focus:outline-none focus:border-interactive"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-text-primary mb-1">Địa chỉ IP nội bộ</label>
                    <input
                      type="text"
                      value={newGwIp}
                      onChange={(e) => setNewGwIp(e.target.value)}
                      placeholder="VD: 192.168.88.113"
                      className="w-full h-10 px-3 bg-canvas border border-border rounded-lg text-text-primary font-mono text-sm focus:outline-none focus:border-interactive"
                    />
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-4 mt-3 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setShowAddGatewayModal(false)}
                    className="h-9 px-4 rounded-lg border border-border bg-canvas hover:bg-canvas/80 text-text-secondary text-xs font-medium transition-colors cursor-pointer"
                  >
                    Hủy
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="h-9 px-4 rounded-lg bg-interactive text-white text-xs font-medium hover:bg-interactive-hover transition-colors cursor-pointer disabled:opacity-50"
                  >
                    {isSubmitting ? "Đang lưu..." : "Thêm trạm"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Floating Context-Aware Navigation Feedback Toast */}
        {toastMessage && (
          <div
            role="status"
            aria-live="polite"
            className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 bg-surface border border-interactive text-text-primary text-xs font-medium rounded-lg shadow-lg"
          >
            <CheckCircle2 className="w-4 h-4 text-interactive shrink-0" />
            <span>{toastMessage}</span>
          </div>
        )}
      </div>
    </AppShell>
  );
}

export default function GatewaysPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-canvas">
          <div className="text-sm font-medium text-text-secondary">
            Đang tải dữ liệu Gateway...
          </div>
        </div>
      }
    >
      <GatewaysContent />
    </Suspense>
  );
}

