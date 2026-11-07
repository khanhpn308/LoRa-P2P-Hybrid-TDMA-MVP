"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { NavItemKey } from "@/components/layout/Sidebar";
import {
  Router,
  Cpu,
  AlertTriangle,
  ChevronRight,
  Thermometer,
  Gauge,
  CheckCircle2,
} from "lucide-react";

// Area datasets conforming strictly to DESIGN.md §7:
// "Minimal status summary only, without graphs: Gateway (connected and operating counts separately),
// Node (connected and operating counts separately), and recorded fault-event counts by type.
// Use 'Sự kiện lỗi', not 'Lỗi đang mở'."
interface MetricSnapshot {
  gateway: { connected: number; total: number; operating: number };
  node: { connected: number; total: number; operating: number };
  faults: { total: number; temp: number; speed: number };
}

const AREA_METRICS: Record<string, { name: string; data: MetricSnapshot }> = {
  all: {
    name: "Tất cả khu vực",
    data: {
      gateway: { connected: 8, total: 10, operating: 7 },
      node: { connected: 180, total: 200, operating: 175 },
      faults: { total: 12, temp: 8, speed: 4 },
    },
  },
  "khu-a": {
    name: "Khu A - Phân xưởng Ép",
    data: {
      gateway: { connected: 3, total: 3, operating: 3 },
      node: { connected: 60, total: 64, operating: 58 },
      faults: { total: 5, temp: 4, speed: 1 },
    },
  },
  "khu-b": {
    name: "Khu B - Trạm Bơm & Thủy lực",
    data: {
      gateway: { connected: 2, total: 2, operating: 2 },
      node: { connected: 45, total: 48, operating: 44 },
      faults: { total: 3, temp: 1, speed: 2 },
    },
  },
  "khu-c": {
    name: "Khu C - Kho lạnh Công nghiệp",
    data: {
      gateway: { connected: 2, total: 3, operating: 1 },
      node: { connected: 50, total: 56, operating: 48 },
      faults: { total: 4, temp: 3, speed: 1 },
    },
  },
  "ngoai-troi": {
    name: "Trạm Thu phát Ngoài trời",
    data: {
      gateway: { connected: 1, total: 2, operating: 1 },
      node: { connected: 25, total: 32, operating: 25 },
      faults: { total: 0, temp: 0, speed: 0 },
    },
  },
};

export default function OverviewPage() {
  const router = useRouter();
  const [activeRoute, setActiveRoute] = useState<NavItemKey>("overview");
  const [selectedArea, setSelectedArea] = useState<string>("all");
  const [lastUpdated, setLastUpdated] = useState<string>("14:32:05");
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  useEffect(() => {
    // Generate initial live time format hh:mm:ss
    const now = new Date();
    setLastUpdated(
      now.toTimeString().split(" ")[0] || "14:32:05"
    );
  }, []);

  const currentMetrics = AREA_METRICS[selectedArea]?.data ?? AREA_METRICS.all.data;
  const currentAreaName = AREA_METRICS[selectedArea]?.name ?? "Tất cả khu vực";

  const showNavigationFeedback = (destination: string, filterStatus: string) => {
    setToastMessage(
      `Điều hướng: ${destination} | Bộ lọc: [${filterStatus}] | Khu vực: [${currentAreaName}]`
    );
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  const navigateToMonitoring = (type?: "temp" | "speed") => {
    showNavigationFeedback("Giám sát sự cố", type ? `Loại: ${type}` : "Tất cả");
    const params = new URLSearchParams();
    if (type) params.set("type", type);
    if (selectedArea === "khu-a") params.set("area", "Khu A");
    else if (selectedArea === "khu-b") params.set("area", "Khu B");
    else if (selectedArea === "khu-c") params.set("area", "Khu C");
    else if (selectedArea === "ngoai-troi") params.set("area", "Ngoài trời");

    const qs = params.toString();
    router.push(qs ? `/monitoring?${qs}` : "/monitoring");
  };

  const navigateToGateways = (filter?: { conn?: string; ops?: string }) => {
    showNavigationFeedback("Quản lý Gateway", filter?.conn ? `Kết nối: ${filter.conn}` : "Tất cả");
    const params = new URLSearchParams();
    if (filter?.conn) params.set("conn", filter.conn);
    if (filter?.ops) params.set("ops", filter.ops);
    const qs = params.toString();
    router.push(qs ? `/gateways?${qs}` : "/gateways");
  };

  const navigateToNodes = (filter?: { conn?: string; ops?: string }) => {
    showNavigationFeedback("Thiết bị Node", filter?.conn ? `Kết nối: ${filter.conn}` : "Tất cả");
    const params = new URLSearchParams();
    if (filter?.conn) params.set("conn", filter.conn);
    if (filter?.ops) params.set("ops", filter.ops);
    const qs = params.toString();
    router.push(qs ? `/nodes?${qs}` : "/nodes");
  };

  return (
    <AppShell activeRoute={activeRoute} onRouteChange={setActiveRoute}>
      <div className="space-y-5">
        {/* Page Header: Title + Area Selector & Timestamp */}
        <section
          aria-label="Tiêu đề trang"
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 min-h-[40px]"
        >
          <h1 className="text-2xl font-semibold text-text-primary tracking-[-0.015em]">
            Tổng quan
          </h1>

          <div className="flex flex-wrap items-center gap-4">
            {/* Area Filter Select */}
            <div className="relative inline-flex items-center">
              <select
                id="area-filter-select"
                aria-label="Lọc theo khu vực"
                value={selectedArea}
                onChange={(e) => {
                  setSelectedArea(e.target.value);
                  const now = new Date();
                  setLastUpdated(now.toTimeString().split(" ")[0] || "14:32:05");
                }}
                className="h-10 pl-3.5 pr-9 rounded-lg border border-border bg-surface text-text-primary text-sm font-medium focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive appearance-none cursor-pointer shadow-none"
              >
                {Object.entries(AREA_METRICS).map(([key, item]) => (
                  <option key={key} value={key}>
                    {item.name}
                  </option>
                ))}
              </select>
              <div className="absolute right-3 pointer-events-none text-text-secondary">
                <ChevronRight className="w-4 h-4 rotate-90" />
              </div>
            </div>

            {/* Timestamp text */}
            <div className="text-xs text-text-secondary tabular-nums whitespace-nowrap">
              Cập nhật lần cuối: {lastUpdated} (Vừa xong)
            </div>
          </div>
        </section>

        {/* Exact 3 KPI Containers Grid (DESIGN.md §7) */}
        <div className="flex flex-col gap-4 w-full">
          {/* First Row: Two Equal-Width Cards (Gateway & Node) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
            {/* CARD 1 — GATEWAY */}
            <article
              aria-labelledby="card-gateway-title"
              className="card-zero-shadow p-5 flex flex-col justify-between"
            >
              {/* Card Header: Clickable navigation trigger */}
              <button
                type="button"
                onClick={() => navigateToGateways()}
                title="Xem danh sách tất cả Gateway"
                className="group flex items-center justify-between w-full pb-4 border-b border-border/80 text-left transition-opacity hover:opacity-85 focus:outline-none"
              >
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded bg-canvas border border-border flex items-center justify-center text-text-secondary">
                    <Router className="w-4 h-4" />
                  </div>
                  <h2
                    id="card-gateway-title"
                    className="text-base font-semibold text-text-primary tracking-tight"
                  >
                    Gateway
                  </h2>
                </div>
                <ChevronRight className="w-4 h-4 text-text-secondary group-hover:text-interactive group-hover:translate-x-0.5 transition-all" />
              </button>

              {/* Fields Container (Two Fields) */}
              <div className="grid grid-cols-2 gap-4 pt-4">
                {/* Field A: Đã kết nối */}
                <button
                  type="button"
                  aria-label={`Xem Gateway Đã kết nối: ${currentMetrics.gateway.connected} trên ${currentMetrics.gateway.total}`}
                  onClick={() => navigateToGateways({ conn: "connected" })}
                  className="group/field flex flex-col gap-1.5 p-2.5 -m-2.5 rounded-lg text-left hover:bg-canvas transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-interactive"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-state-connected shrink-0" />
                    <span className="text-[13px] font-medium text-text-secondary">
                      Đã kết nối
                    </span>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <span className="text-[32px] font-semibold tabular-nums text-text-primary leading-tight">
                      {currentMetrics.gateway.connected}/{currentMetrics.gateway.total}
                    </span>
                  </div>
                  <div className="text-xs text-text-secondary group-hover/field:text-interactive flex items-center gap-1 opacity-0 group-hover/field:opacity-100 transition-opacity">
                    <span>Chi tiết kết nối</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </div>
                </button>

                {/* Field B: Đang hoạt động */}
                <button
                  type="button"
                  aria-label={`Xem Gateway Đang hoạt động: ${currentMetrics.gateway.operating} trên ${currentMetrics.gateway.total}`}
                  onClick={() => navigateToGateways({ ops: "active" })}
                  className="group/field flex flex-col gap-1.5 p-2.5 -m-2.5 pl-4 border-l border-border/70 rounded-lg text-left hover:bg-canvas transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-interactive"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-state-active shrink-0" />
                    <span className="text-[13px] font-medium text-text-secondary">
                      Đang hoạt động
                    </span>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <span className="text-[32px] font-semibold tabular-nums text-text-primary leading-tight">
                      {currentMetrics.gateway.operating}/{currentMetrics.gateway.total}
                    </span>
                  </div>
                  <div className="text-xs text-text-secondary group-hover/field:text-interactive flex items-center gap-1 opacity-0 group-hover/field:opacity-100 transition-opacity">
                    <span>Chi tiết hoạt động</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </div>
                </button>
              </div>
            </article>

            {/* CARD 2 — NODE */}
            <article
              aria-labelledby="card-node-title"
              className="card-zero-shadow p-5 flex flex-col justify-between"
            >
              {/* Card Header: Clickable navigation trigger */}
              <button
                type="button"
                onClick={() => navigateToNodes()}
                title="Xem danh sách tất cả Node"
                className="group flex items-center justify-between w-full pb-4 border-b border-border/80 text-left transition-opacity hover:opacity-85 focus:outline-none"
              >
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded bg-canvas border border-border flex items-center justify-center text-text-secondary">
                    <Cpu className="w-4 h-4" />
                  </div>
                  <h2
                    id="card-node-title"
                    className="text-base font-semibold text-text-primary tracking-tight"
                  >
                    Node
                  </h2>
                </div>
                <ChevronRight className="w-4 h-4 text-text-secondary group-hover:text-interactive group-hover:translate-x-0.5 transition-all" />
              </button>

              {/* Fields Container (Two Fields, identical structure) */}
              <div className="grid grid-cols-2 gap-4 pt-4">
                {/* Field A: Đã kết nối */}
                <button
                  type="button"
                  aria-label={`Xem Node Đã kết nối: ${currentMetrics.node.connected} trên ${currentMetrics.node.total}`}
                  onClick={() => navigateToNodes({ conn: "connected" })}
                  className="group/field flex flex-col gap-1.5 p-2.5 -m-2.5 rounded-lg text-left hover:bg-canvas transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-interactive"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-state-connected shrink-0" />
                    <span className="text-[13px] font-medium text-text-secondary">
                      Đã kết nối
                    </span>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <span className="text-[32px] font-semibold tabular-nums text-text-primary leading-tight">
                      {currentMetrics.node.connected}/{currentMetrics.node.total}
                    </span>
                  </div>
                  <div className="text-xs text-text-secondary group-hover/field:text-interactive flex items-center gap-1 opacity-0 group-hover/field:opacity-100 transition-opacity">
                    <span>Chi tiết kết nối</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </div>
                </button>

                {/* Field B: Đang hoạt động */}
                <button
                  type="button"
                  aria-label={`Xem Node Đang hoạt động: ${currentMetrics.node.operating} trên ${currentMetrics.node.total}`}
                  onClick={() => navigateToNodes({ ops: "active" })}
                  className="group/field flex flex-col gap-1.5 p-2.5 -m-2.5 pl-4 border-l border-border/70 rounded-lg text-left hover:bg-canvas transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-interactive"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-state-active shrink-0" />
                    <span className="text-[13px] font-medium text-text-secondary">
                      Đang hoạt động
                    </span>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <span className="text-[32px] font-semibold tabular-nums text-text-primary leading-tight">
                      {currentMetrics.node.operating}/{currentMetrics.node.total}
                    </span>
                  </div>
                  <div className="text-xs text-text-secondary group-hover/field:text-interactive flex items-center gap-1 opacity-0 group-hover/field:opacity-100 transition-opacity">
                    <span>Chi tiết hoạt động</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </div>
                </button>
              </div>
            </article>
          </div>

          {/* Second Row: One Full-Width Card (Sự kiện lỗi) */}
          <div className="w-full">
            <article
              aria-labelledby="card-faults-title"
              className="card-zero-shadow p-5 flex flex-col justify-between"
            >
              {/* Card Header: Clickable navigation trigger */}
              <button
                type="button"
                onClick={() => navigateToMonitoring()}
                title="Xem tất cả sự kiện lỗi trong hệ thống"
                className="group flex items-center justify-between w-full pb-4 border-b border-border/80 text-left transition-opacity hover:opacity-85 focus:outline-none"
              >
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded bg-red-50 dark:bg-red-950/60 border border-red-200 dark:border-red-900/70 flex items-center justify-center text-state-critical">
                    <AlertTriangle className="w-4 h-4" />
                  </div>
                  <h2
                    id="card-faults-title"
                    className="text-base font-semibold text-text-primary tracking-tight"
                  >
                    Sự kiện lỗi
                  </h2>
                </div>
                <ChevronRight className="w-4 h-4 text-text-secondary group-hover:text-interactive group-hover:translate-x-0.5 transition-all" />
              </button>

              {/* Fields Container (Three Fields Evenly Spaced) */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
                {/* Field A: Tổng sự kiện */}
                <button
                  type="button"
                  aria-label={`Xem Tổng sự kiện lỗi: ${currentMetrics.faults.total}`}
                  onClick={() => navigateToMonitoring()}
                  className="group/field flex flex-col gap-1.5 p-2.5 -m-2.5 rounded-lg text-left hover:bg-canvas transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-interactive"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-state-critical shrink-0" />
                    <span className="text-[13px] font-medium text-text-secondary">
                      Tổng sự kiện
                    </span>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <span className="text-[32px] font-semibold tabular-nums text-state-critical leading-tight">
                      {currentMetrics.faults.total}
                    </span>
                  </div>
                  <div className="text-xs text-text-secondary group-hover/field:text-interactive flex items-center gap-1 opacity-0 group-hover/field:opacity-100 transition-opacity">
                    <span>Xem danh sách sự kiện</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </div>
                </button>

                {/* Field B: Nhiệt độ */}
                <button
                  type="button"
                  aria-label={`Xem sự kiện Nhiệt độ: ${currentMetrics.faults.temp}`}
                  onClick={() => navigateToMonitoring("temp")}
                  className="group/field flex flex-col gap-1.5 p-2.5 -m-2.5 md:pl-4 md:border-l md:border-border/70 rounded-lg text-left hover:bg-canvas transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-interactive"
                >
                  <div className="flex items-center gap-2">
                    <Thermometer className="w-4 h-4 text-text-secondary shrink-0" />
                    <span className="text-[13px] font-medium text-text-secondary">
                      Nhiệt độ
                    </span>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <span className="text-[32px] font-semibold tabular-nums text-text-primary leading-tight">
                      {currentMetrics.faults.temp}
                    </span>
                  </div>
                  <div className="text-xs text-text-secondary group-hover/field:text-interactive flex items-center gap-1 opacity-0 group-hover/field:opacity-100 transition-opacity">
                    <span>Lọc sự kiện nhiệt độ</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </div>
                </button>

                {/* Field C: Tốc độ */}
                <button
                  type="button"
                  aria-label={`Xem sự kiện Tốc độ: ${currentMetrics.faults.speed}`}
                  onClick={() => navigateToMonitoring("speed")}
                  className="group/field flex flex-col gap-1.5 p-2.5 -m-2.5 md:pl-4 md:border-l md:border-border/70 rounded-lg text-left hover:bg-canvas transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-interactive"
                >
                  <div className="flex items-center gap-2">
                    <Gauge className="w-4 h-4 text-text-secondary shrink-0" />
                    <span className="text-[13px] font-medium text-text-secondary">
                      Tốc độ
                    </span>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <span className="text-[32px] font-semibold tabular-nums text-text-primary leading-tight">
                      {currentMetrics.faults.speed}
                    </span>
                  </div>
                  <div className="text-xs text-text-secondary group-hover/field:text-interactive flex items-center gap-1 opacity-0 group-hover/field:opacity-100 transition-opacity">
                    <span>Lọc sự kiện tốc độ</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </div>
                </button>
              </div>
            </article>
          </div>
        </div>

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
