"use client";

import React, { useState, use, Suspense } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import {
  ArrowLeft,
  ChevronRight,
  Radio,
  Layers,
  AlertTriangle,
} from "lucide-react";

interface GatewayDetailProps {
  params: Promise<{ id: string }>;
}

interface GatewayInfo {
  id: string;
  name: string;
  connected: boolean;
  operating: boolean;
  mode: "BOOTSTRAP" | "ACTIVE" | "AUTONOMOUS" | "RECOVERY" | "FAULT" | "OFFLINE";
  activeScheduleVersion: number;
  lastSeenAt: string | null;
  rfDutyPermille: number;
  nodeCount: number;
  channel: string;
  frequency: string;
  bandwidth: string;
  txPower: string;
  sf: string;
  cr: string;
  primaryArea: string;
  ipAddress: string;
  macAddress: string;
  firmwareVersion: string;
}

const GATEWAY_DATA: Record<string, GatewayInfo> = {
  "GW-01": {
    id: "GW-01",
    name: "Trạm Đông - Khu A",
    connected: true,
    operating: true,
    mode: "ACTIVE",
    activeScheduleVersion: 4,
    lastSeenAt: "2026-11-08T03:00:00Z",
    rfDutyPermille: 12,
    nodeCount: 38,
    channel: "CH01",
    frequency: "920.500 MHz",
    bandwidth: "125 kHz",
    txPower: "14 dBm",
    sf: "SF7",
    cr: "4/5",
    primaryArea: "Khu vực A",
    ipAddress: "192.168.10.1",
    macAddress: "B8:D6:1A:4C:82:01",
    firmwareVersion: "ESP-IDF v6.1 · Hybrid-TDMA v2.4",
  },
  "GW-02": {
    id: "GW-02",
    name: "Trạm Tây - Khu B",
    connected: true,
    operating: true,
    mode: "ACTIVE",
    activeScheduleVersion: 3,
    lastSeenAt: "2026-11-08T03:00:00Z",
    rfDutyPermille: 8,
    nodeCount: 24,
    channel: "CH02",
    frequency: "920.750 MHz",
    bandwidth: "125 kHz",
    txPower: "14 dBm",
    sf: "SF7",
    cr: "4/5",
    primaryArea: "Khu vực B",
    ipAddress: "192.168.10.2",
    macAddress: "B8:D6:1A:4C:82:02",
    firmwareVersion: "ESP-IDF v6.1 · Hybrid-TDMA v2.4",
  },
  "GW-03": {
    id: "GW-03",
    name: "Trạm Nam - Khu C",
    connected: true,
    operating: false,
    mode: "AUTONOMOUS",
    activeScheduleVersion: 2,
    lastSeenAt: "2026-11-08T02:45:00Z",
    rfDutyPermille: 5,
    nodeCount: 16,
    channel: "CH03",
    frequency: "921.000 MHz",
    bandwidth: "125 kHz",
    txPower: "14 dBm",
    sf: "SF7",
    cr: "4/5",
    primaryArea: "Khu vực C",
    ipAddress: "192.168.10.3",
    macAddress: "B8:D6:1A:4C:82:03",
    firmwareVersion: "ESP-IDF v6.1 · Hybrid-TDMA v2.4",
  },
  "GW-04": {
    id: "GW-04",
    name: "Trạm Bắc - Khu D",
    connected: true,
    operating: true,
    mode: "ACTIVE",
    activeScheduleVersion: 1,
    lastSeenAt: "2026-11-08T03:00:00Z",
    rfDutyPermille: 15,
    nodeCount: 20,
    channel: "CH04",
    frequency: "921.250 MHz",
    bandwidth: "125 kHz",
    txPower: "14 dBm",
    sf: "SF7",
    cr: "4/5",
    primaryArea: "Khu vực D",
    ipAddress: "192.168.10.4",
    macAddress: "B8:D6:1A:4C:82:04",
    firmwareVersion: "ESP-IDF v6.1 · Hybrid-TDMA v2.4",
  },
};

interface CoveredAreaItem {
  id: string;
  name: string;
  description: string;
  nodeCount: number;
  faultEventCount: number;
  status: "normal" | "warning" | "optimal";
}

function GatewayDetailContent({ params }: { params: Promise<{ id: string }> }) {
  const unwrappedParams = use(params);
  const rawId = decodeURIComponent(unwrappedParams.id || "GW-01");
  const router = useRouter();

  const [timeRange, setTimeRange] = useState<"24h" | "7d" | "30d">("24h");

  const gw: GatewayInfo = GATEWAY_DATA[rawId] || {
    id: rawId,
    name: `Trạm điều hành ${rawId}`,
    connected: true,
    operating: true,
    mode: "ACTIVE",
    activeScheduleVersion: 1,
    lastSeenAt: "2026-11-08T03:00:00Z",
    rfDutyPermille: 10,
    nodeCount: 20,
    channel: "CH01",
    frequency: "920.500 MHz",
    bandwidth: "125 kHz",
    txPower: "14 dBm",
    sf: "SF7",
    cr: "4/5",
    primaryArea: "Khu vực A",
    ipAddress: "192.168.10.10",
    macAddress: "B8:D6:1A:4C:82:99",
    firmwareVersion: "ESP-IDF v6.1 · Hybrid-TDMA v2.4",
  };

  // Backend-provided covered areas with fault-event count (DESIGN.md §7)
  const coveredAreas: CoveredAreaItem[] = [
    {
      id: "CA-1",
      name: gw.primaryArea,
      description: "Khu phân xưởng sản xuất chính & buồng máy nén",
      nodeCount: 38,
      faultEventCount: timeRange === "24h" ? 5 : timeRange === "7d" ? 18 : 42,
      status: "warning",
    },
    {
      id: "CA-2",
      name: "Khu vực Phụ trợ",
      description: "Hệ thống trạm bơm giải nhiệt và tháp trao đổi nhiệt",
      nodeCount: 24,
      faultEventCount: timeRange === "24h" ? 2 : timeRange === "7d" ? 7 : 15,
      status: "normal",
    },
    {
      id: "CA-3",
      name: "Kho nguyên liệu",
      description: "Kho lưu trữ vật tư và sàn bến bãi logistics",
      nodeCount: 16,
      faultEventCount: 0,
      status: "optimal",
    },
  ];

  const handleNavigateToMonitoring = (areaName: string) => {
    router.push(`/monitoring?area=${encodeURIComponent(areaName)}`);
  };

  return (
    <AppShell activeRoute="gateways">
      {/* Breadcrumb Navigation */}
      <div className="flex flex-col gap-1 mb-5">
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-text-secondary">
          <button
            type="button"
            onClick={() => router.push("/gateways")}
            className="flex items-center gap-1 hover:text-interactive transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Quản lý</span>
          </button>
          <ChevronRight className="w-3.5 h-3.5 text-text-secondary/60" />
          <Link href="/gateways" className="hover:text-interactive transition-colors">
            Gateway
          </Link>
          <ChevronRight className="w-3.5 h-3.5 text-text-secondary/60" />
          <span className="font-mono font-medium text-text-primary">{gw.id}</span>
        </nav>

        {/* Top Header & Identity */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold font-mono text-text-primary tracking-tight">
              Gateway {gw.id}
            </h1>
            <span className="text-base text-text-secondary font-medium">
              — {gw.name}
            </span>

            {/* Connected & Operating status separately (DESIGN.md §7) */}
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="px-2.5 py-1 rounded-md bg-canvas border border-border text-text-secondary font-medium">
                Khu vực chính: <strong className="text-text-primary">{gw.primaryArea}</strong>
              </span>

              {gw.connected ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 text-state-connected font-medium">
                  <span className="w-2 h-2 rounded-full bg-state-connected" />
                  Kết nối: Đã kết nối
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/60 text-state-critical font-medium">
                  <span className="w-2 h-2 rounded-full bg-state-critical" />
                  Kết nối: Mất kết nối
                </span>
              )}

              {gw.operating ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800/60 text-interactive font-medium">
                  <span className="w-2 h-2 rounded-full bg-interactive" />
                  Hoạt động: Đang hoạt động
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-canvas border border-border text-text-secondary font-medium">
                  <span className="w-2 h-2 rounded-full bg-text-secondary/60" />
                  Hoạt động: Dừng hoạt động
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-6">
        {/* SECTION 1: Read-only Radio Fields (Kênh, Tần số, Dải tần - DESIGN.md §7) */}
        <section className="bg-chrome rounded-lg p-6 border border-border shadow-none flex flex-col gap-5">
          <div className="flex items-center justify-between pb-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Radio className="w-5 h-5 text-interactive" />
              <div>
                <h2 className="text-base font-semibold text-text-primary">
                  Thông số vô tuyến LoRa RF (Chỉ đọc)
                </h2>
                <p className="text-xs text-text-secondary mt-0.5">
                  Cấu hình phần cứng PHY/TDMA nạp trực tiếp từ firmware ESP32-WROOM-32E + SX1276
                </p>
              </div>
            </div>

            <span className="text-xs font-mono px-2.5 py-1 rounded bg-canvas border border-border text-text-secondary">
              {gw.firmwareVersion}
            </span>
          </div>

          {/* 6 Radio Specification Cards strictly read-only */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
            {/* Field 1: Kênh */}
            <div className="bg-canvas rounded-lg p-3 border border-border flex flex-col">
              <span className="text-xs font-medium text-text-secondary">Kênh (Channel)</span>
              <span className="text-lg font-mono font-semibold text-text-primary mt-1">
                {gw.channel}
              </span>
              <span className="text-[10px] text-text-secondary mt-0.5">Kênh TDMA chính</span>
            </div>

            {/* Field 2: Tần số (MHz) */}
            <div className="bg-canvas rounded-lg p-3 border border-border flex flex-col">
              <span className="text-xs font-medium text-text-secondary">Tần số (MHz)</span>
              <span className="text-lg font-mono font-semibold text-interactive mt-1">
                {gw.frequency}
              </span>
              <span className="text-[10px] text-text-secondary mt-0.5">Băng tần AS923</span>
            </div>

            {/* Field 3: Dải tần */}
            <div className="bg-canvas rounded-lg p-3 border border-border flex flex-col">
              <span className="text-xs font-medium text-text-secondary">Dải tần (BW)</span>
              <span className="text-lg font-mono font-semibold text-text-primary mt-1">
                {gw.bandwidth}
              </span>
              <span className="text-[10px] text-text-secondary mt-0.5">Băng thông cố định</span>
            </div>

            {/* Field 4: Công suất phát */}
            <div className="bg-canvas rounded-lg p-3 border border-border flex flex-col">
              <span className="text-xs font-medium text-text-secondary">Công suất TX</span>
              <span className="text-lg font-mono font-semibold text-text-primary mt-1">
                {gw.txPower}
              </span>
              <span className="text-[10px] text-text-secondary mt-0.5">PA_BOOST path</span>
            </div>

            {/* Field 5: Spreading Factor */}
            <div className="bg-canvas rounded-lg p-3 border border-border flex flex-col">
              <span className="text-xs font-medium text-text-secondary">Trải phổ (SF)</span>
              <span className="text-lg font-mono font-semibold text-text-primary mt-1">
                {gw.sf}
              </span>
              <span className="text-[10px] text-text-secondary mt-0.5">Slot thời gian ngắn</span>
            </div>

            {/* Field 6: Coding Rate */}
            <div className="bg-canvas rounded-lg p-3 border border-border flex flex-col">
              <span className="text-xs font-medium text-text-secondary">Coding Rate (CR)</span>
              <span className="text-lg font-mono font-semibold text-text-primary mt-1">
                {gw.cr}
              </span>
              <span className="text-[10px] text-text-secondary mt-0.5">Sửa lỗi FEC 4/5</span>
            </div>
          </div>
        </section>

        {/* SECTION 2: List of backend-provided covered areas with fault-event count (DESIGN.md §7) */}
        <section className="bg-chrome rounded-lg border border-border shadow-none overflow-hidden flex flex-col">
          <div className="p-5 border-b border-border flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-text-primary flex items-center gap-2">
                <Layers className="w-5 h-5 text-interactive" />
                <span>Khu vực phủ sóng & Sự kiện lỗi</span>
              </h2>
              <p className="text-xs text-text-secondary mt-0.5">
                Danh sách các khu vực do backend xác nhận thuộc tầm phủ sóng của Gateway {gw.id}
              </p>
            </div>

            {/* Time Period Filter: 24h / 7d / 30d */}
            <div className="flex items-center p-0.5 bg-canvas border border-border rounded-lg h-9">
              <button
                type="button"
                onClick={() => setTimeRange("24h")}
                className={`px-3 h-8 rounded text-xs font-medium transition-colors ${
                  timeRange === "24h"
                    ? "bg-interactive text-white shadow-sm font-semibold"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                24 giờ qua
              </button>
              <button
                type="button"
                onClick={() => setTimeRange("7d")}
                className={`px-3 h-8 rounded text-xs font-medium transition-colors ${
                  timeRange === "7d"
                    ? "bg-interactive text-white shadow-sm font-semibold"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                7 ngày qua
              </button>
              <button
                type="button"
                onClick={() => setTimeRange("30d")}
                className={`px-3 h-8 rounded text-xs font-medium transition-colors ${
                  timeRange === "30d"
                    ? "bg-interactive text-white shadow-sm font-semibold"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                30 ngày qua
              </button>
            </div>
          </div>

          {/* Table of Covered Areas */}
          <div className="overflow-x-auto w-full">
            <table className="w-full text-left border-collapse table-fixed min-w-[700px]">
              <thead>
                <tr className="h-10 bg-canvas/60 border-b border-border text-[12px] font-semibold text-text-secondary uppercase tracking-wider">
                  <th scope="col" className="py-2.5 pl-6 pr-4" style={{ width: "24%" }}>
                    Khu vực
                  </th>
                  <th scope="col" className="py-2.5 px-4" style={{ width: "36%" }}>
                    Mô tả vị trí hạ tầng
                  </th>
                  <th scope="col" className="py-2.5 px-4 text-center" style={{ width: "15%" }}>
                    Số Node
                  </th>
                  <th scope="col" className="py-2.5 px-4 text-center" style={{ width: "15%" }}>
                    Sự kiện lỗi
                  </th>
                  <th scope="col" className="py-2.5 pr-6 pl-2 text-right" style={{ width: "10%" }}>
                    Theo dõi
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-border text-sm">
                {coveredAreas.map((area) => (
                  <tr
                    key={area.id}
                    onClick={() => handleNavigateToMonitoring(area.name)}
                    title={`Mở trang Theo dõi cho ${area.name}`}
                    className="h-14 hover:bg-interactive-subtle/40 transition-colors cursor-pointer group"
                  >
                    {/* 1. Tên khu vực */}
                    <td className="py-3 pl-6 pr-4">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-interactive text-sm group-hover:underline underline-offset-2">
                          {area.name}
                        </span>
                        {area.id === "CA-1" && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 dark:bg-blue-950/60 text-interactive border border-blue-200 dark:border-blue-800">
                            Chính
                          </span>
                        )}
                      </div>
                    </td>

                    {/* 2. Mô tả */}
                    <td className="py-3 px-4 text-xs text-text-secondary">
                      {area.description}
                    </td>

                    {/* 3. Số Node */}
                    <td className="py-3 px-4 text-center font-mono font-medium text-text-primary text-xs">
                      {area.nodeCount} node
                    </td>

                    {/* 4. Sự kiện lỗi */}
                    <td className="py-3 px-4 text-center">
                      {area.faultEventCount > 0 ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 dark:bg-red-950/60 text-state-critical border border-red-200 dark:border-red-900/60 font-mono">
                          <AlertTriangle className="w-3 h-3" />
                          <span>{area.faultEventCount} lỗi</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium text-state-connected bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 font-mono">
                          0 lỗi
                        </span>
                      )}
                    </td>

                    {/* 5. Nút điều hướng */}
                    <td className="py-3 pr-6 pl-2 text-right">
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-interactive group-hover:translate-x-0.5 transition-transform">
                        <span>Chi tiết</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

export default function GatewayDetailPage({ params }: GatewayDetailProps) {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-canvas">
          <div className="flex items-center gap-3 text-text-secondary text-sm">
            <div className="w-5 h-5 border-2 border-interactive border-t-transparent rounded-full animate-spin" />
            <span>Đang tải thông tin Gateway...</span>
          </div>
        </div>
      }
    >
      <GatewayDetailContent params={params} />
    </Suspense>
  );
}
