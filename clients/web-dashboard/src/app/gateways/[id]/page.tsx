"use client";

import React, { useState, useEffect, useMemo, use, Suspense } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { getGatewayStatus, getGateways, deleteGateway } from "@/lib/api/gateways";
import { getAlerts } from "@/lib/api/alerts";
import { useAuth } from "@/lib/auth/AuthContext";
import { useRealtime } from "@/lib/realtime/RealtimeContext";
import {
  Alert,
  AlertTriggeredPayload,
  GatewayStatusChangedPayload,
} from "@/types/api";
import {
  ArrowLeft,
  ChevronRight,
  Radio,
  Layers,
  AlertTriangle,
  Trash2,
  CheckCircle2,
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
  const { role } = useAuth();
  const { subscribe } = useRealtime();

  const [timeRange, setTimeRange] = useState<"24h" | "7d" | "30d">("24h");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [showDeleteModal, setShowDeleteModal] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const initialGw: GatewayInfo = {
    id: rawId,
    name: `Gateway ${rawId}`,
    connected: false,
    operating: false,
    mode: "OFFLINE",
    activeScheduleVersion: 0,
    lastSeenAt: null,
    rfDutyPermille: 0,
    nodeCount: 0,
    channel: "CH01",
    frequency: "920.500 MHz",
    bandwidth: "125 kHz",
    txPower: "14 dBm",
    sf: "SF7",
    cr: "4/5",
    primaryArea: "Khu vực cảm biến",
    ipAddress: "--",
    macAddress: "--",
    firmwareVersion: "ESP-IDF v6.1 · Hybrid-TDMA",
  };

  const [gw, setGw] = useState<GatewayInfo>(initialGw);

  useEffect(() => {
    async function loadRealGateway() {
      try {
        const [realStatusResult, allGwsResult, alertsResult] = await Promise.allSettled([
          getGatewayStatus(rawId),
          getGateways(),
          getAlerts({ gateway_id: rawId, limit: 100 }),
        ]);

        if (allGwsResult.status === "fulfilled" && Array.isArray(allGwsResult.value)) {
          const matchedGw = allGwsResult.value.find((g) => g.gateway_id === rawId);
          if (matchedGw) {
            setGw((prev) => ({
              ...prev,
              name: matchedGw.name || prev.name,
              primaryArea: matchedGw.location || prev.primaryArea,
              ipAddress: matchedGw.ip_address || prev.ipAddress,
              channel: matchedGw.channel_id || prev.channel,
              frequency: matchedGw.frequency_hz
                ? `${(matchedGw.frequency_hz / 1e6).toFixed(3)} MHz`
                : prev.frequency,
            }));
          }
        }

        if (realStatusResult.status === "fulfilled" && realStatusResult.value) {
          const realStatus = realStatusResult.value;
          setGw((prev) => ({
            ...prev,
            mode: realStatus.mode,
            activeScheduleVersion: realStatus.active_schedule_version,
            lastSeenAt: realStatus.last_seen_at,
            rfDutyPermille: realStatus.rf_duty_permille,
            nodeCount: realStatus.node_count,
            connected: realStatus.mode !== "OFFLINE",
            operating: realStatus.mode === "ACTIVE" || realStatus.mode === "AUTONOMOUS",
          }));
        }

        if (
          alertsResult.status === "fulfilled" &&
          alertsResult.value &&
          Array.isArray(alertsResult.value.items)
        ) {
          setAlerts(alertsResult.value.items);
        }
      } catch {
        // preserve baseline
      }
    }
    loadRealGateway();
  }, [rawId]);

  useEffect(() => {
    const unsubscribe = subscribe((envelope) => {
      if (envelope.type === "ALERT_TRIGGERED") {
        const payload = envelope.payload as AlertTriggeredPayload;
        if (payload.gateway_id === rawId) {
          const newAlert: Alert = {
            alert_id: payload.alert_id,
            node_id: payload.node_id,
            gateway_id: payload.gateway_id,
            event_ref: payload.event_ref,
            event_code: payload.event_code,
            event_value: payload.event_value,
            severity: payload.severity,
            triggered_at: payload.triggered_at,
            received_at: new Date().toISOString(),
            ack_status: "UNACKNOWLEDGED",
            acked_at: null,
          };
          setAlerts((prev) => [newAlert, ...prev.filter((a) => a.alert_id !== newAlert.alert_id)]);
        }
      } else if (envelope.type === "GATEWAY_STATUS_CHANGED") {
        const payload = envelope.payload as GatewayStatusChangedPayload;
        if (payload.gateway_id === rawId) {
          setGw((prev) => ({
            ...prev,
            mode: payload.mode,
            connected: payload.mode !== "OFFLINE",
            operating: payload.mode === "ACTIVE" || payload.mode === "AUTONOMOUS",
            lastSeenAt: payload.last_seen_at,
          }));
        }
      }
    });

    return () => {
      unsubscribe();
    };
  }, [rawId, subscribe]);

  // Compute alerts filtered by selected time range (24h / 7d / 30d)
  const filteredAlerts = useMemo(() => {
    const now = Date.now();
    const windowMs =
      timeRange === "24h"
        ? 24 * 60 * 60 * 1000
        : timeRange === "7d"
        ? 7 * 24 * 60 * 60 * 1000
        : 30 * 24 * 60 * 60 * 1000;

    return alerts.filter((a) => {
      const ts = a.triggered_at
        ? new Date(a.triggered_at).getTime()
        : new Date(a.received_at).getTime();
      return !isNaN(ts) && now - ts <= windowMs;
    });
  }, [alerts, timeRange]);

  // Real covered areas derived from gateway metadata and real alert counts
  const coveredAreas: CoveredAreaItem[] = useMemo(() => {
    const rawAreas = gw.primaryArea
      .split(/[,;]/)
      .map((s) => s.trim())
      .filter(Boolean);
    const areaNames = rawAreas.length > 0 ? rawAreas : [gw.primaryArea || "Khu vực chung"];

    return areaNames.map((name, idx) => ({
      id: `CA-${gw.id}-${idx + 1}`,
      name,
      description:
        idx === 0
          ? `Khu vực vận hành và vùng phủ sóng vô tuyến chính của Gateway ${gw.id}`
          : `Phân khu trực thuộc tầm phủ sóng của Gateway ${gw.id}`,
      nodeCount: idx === 0 ? gw.nodeCount : 0,
      faultEventCount: filteredAlerts.length,
      status: filteredAlerts.length > 0 ? ("warning" as const) : ("optimal" as const),
    }));
  }, [gw.id, gw.primaryArea, gw.nodeCount, filteredAlerts.length]);

  const handleNavigateToMonitoring = (areaName: string) => {
    router.push(`/monitoring?area=${encodeURIComponent(areaName)}`);
  };

  const handleConfirmDelete = async () => {
    if (role !== "ADMIN") return;
    try {
      setIsDeleting(true);
      await deleteGateway(rawId);
      setToastMessage(`Đã xóa thành công Gateway [${rawId}]. Đang chuyển hướng...`);
      setShowDeleteModal(false);
      setTimeout(() => {
        router.push("/gateways");
      }, 1000);
    } catch (err) {
      setToastMessage(`Lỗi khi xóa Gateway: ${err instanceof Error ? err.message : "Thất bại"}`);
    } finally {
      setIsDeleting(false);
    }
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

          {/* Action button for ADMIN (Issue #293) */}
          {role === "ADMIN" && (
            <button
              type="button"
              onClick={() => setShowDeleteModal(true)}
              title={`Xóa Gateway ${gw.id}`}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-state-critical bg-state-critical/10 hover:bg-state-critical hover:text-white border border-state-critical/20 transition-colors cursor-pointer"
            >
              <Trash2 className="w-4 h-4" />
              <span>Xóa Gateway</span>
            </button>
          )}
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
              <span className="text-[10px] text-text-secondary mt-0.5">Airtime tối ưu</span>
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
                {coveredAreas.map((area, index) => (
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
                        {index === 0 && (
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

      {/* Confirmation Modal for Safe Gateway Deletion (Issue #293) */}
      {showDeleteModal && role === "ADMIN" && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-gateway-detail-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
        >
          <div className="bg-surface border border-border rounded-xl shadow-none max-w-md w-full p-6 space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-state-critical/10 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-state-critical" />
              </div>
              <div className="space-y-1">
                <h3 id="delete-gateway-detail-modal-title" className="text-base font-semibold text-text-primary">
                  Xác nhận xóa Gateway
                </h3>
                <p className="text-sm text-text-secondary">
                  Bạn có chắc chắn muốn gỡ bỏ Gateway{" "}
                  <span className="font-semibold text-text-primary">{gw.name}</span> (
                  <span className="font-mono text-interactive font-semibold">{gw.id}</span>)?
                </p>
              </div>
            </div>

            <div className="p-3 bg-state-critical/5 border border-state-critical/20 rounded-lg text-xs text-state-critical space-y-1">
              <div className="font-semibold flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" /> Cảnh báo rủi ro hệ thống:
              </div>
              <div>
                Hành động này sẽ ngắt kết nối và gỡ toàn bộ cấu hình trạm Gateway khỏi hệ thống,
                đồng thời giải phóng kênh RF ({gw.frequency}) đang gán để dùng cho trạm khác.
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
              <button
                type="button"
                onClick={() => setShowDeleteModal(false)}
                disabled={isDeleting}
                className="h-9 px-4 rounded-lg border border-border bg-canvas hover:bg-canvas/80 text-text-secondary text-xs font-medium transition-colors cursor-pointer"
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="h-9 px-4 rounded-lg bg-state-critical hover:bg-state-critical/90 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer flex items-center gap-2 disabled:opacity-50"
              >
                {isDeleting ? "Đang xóa..." : "Xác nhận xóa"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Context-Aware Feedback Toast */}
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
