"use client";

import React, { useState, useEffect, use, useMemo, Suspense } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { getNode, deleteNode } from "@/lib/api/nodes";
import { getAlerts } from "@/lib/api/alerts";
import { useAuth } from "@/lib/auth/AuthContext";
import { useRealtime } from "@/lib/realtime/RealtimeContext";
import { TimeSeriesChart, TimeSeriesPoint } from "@/components/charts/TimeSeriesChart";
import {
  ArrowLeft,
  ChevronRight,
  Cpu,
  Radio,
  Battery,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Bell,
  Trash2,
} from "lucide-react";
import { NodeSummary, Alert, AlertSeverity, AlertAckStatus, AlertTriggeredPayload } from "@/types/api";

interface NodeDetailProps {
  params: Promise<{ id: string }>;
}

interface NodeDetailView extends NodeSummary {
  area: string;
  connected: boolean;
  operating: boolean;
  state: "NORMAL" | "FAULT" | "MAINTENANCE" | "OFFLINE";
  last_event_type: string;
  firmware_version: string;
}

function NodeDetailContent({ params }: { params: Promise<{ id: string }> }) {
  const unwrappedParams = use(params);
  const rawId = decodeURIComponent(unwrappedParams.id || "N-012");
  const router = useRouter();
  const { role } = useAuth();
  const { subscribe } = useRealtime();

  const [showDeleteModal, setShowDeleteModal] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const initialNode: NodeDetailView = {
    node_id: parseInt(rawId.replace(/\D/g, "") || "1", 10),
    gateway_id: "--",
    name: `Node ${rawId}`,
    area: "Khu vực cảm biến",
    connected: false,
    operating: false,
    state: "OFFLINE",
    last_event_type: "Chưa có sự kiện",
    last_seen_at: null,
    last_rssi_dbm: null,
    last_snr_db: null,
    battery_mv: 3300,
    status: "OFFLINE",
    firmware_version: "ESP-IDF v6.1 · P2P CSMA/CAD",
  };

  const [node, setNode] = useState<NodeDetailView>(initialNode);
  const [events, setEvents] = useState<Alert[]>([]);

  useEffect(() => {
    async function loadRealNode() {
      const realNode = await getNode(rawId);
      if (realNode) {
        setNode((prev) => ({
          ...prev,
          node_id: realNode.node_id,
          gateway_id: realNode.gateway_id,
          name: realNode.name || prev.name,
          last_seen_at: realNode.last_seen_at,
          status: realNode.status,
          connected: realNode.status === "ONLINE",
          operating: realNode.status === "ONLINE",
          state: realNode.status === "ONLINE" ? "NORMAL" : "OFFLINE",
        }));
      }
      try {
        const numId = parseInt(rawId.replace(/\D/g, "") || "1", 10);
        const alertsResp = await getAlerts({ node_id: numId });
        if (alertsResp && alertsResp.items) {
          setEvents(alertsResp.items);
        } else {
          setEvents([]);
        }
      } catch {
        setEvents([]);
      }
    }
    loadRealNode();

    const unsubscribe = subscribe((envelope) => {
      if (envelope.type === "ALERT_TRIGGERED") {
        const payload = envelope.payload as AlertTriggeredPayload;
        const currentNumId = parseInt(rawId.replace(/\D/g, "") || "1", 10);
        if (payload.node_id === currentNumId) {
          // Prepend new realtime alert
          const newAlert: Alert = {
            alert_id: payload.alert_id,
            node_id: payload.node_id,
            gateway_id: payload.gateway_id,
            event_ref: payload.event_ref || 0,
            event_code: payload.event_code,
            event_value: payload.event_value,
            severity: payload.severity,
            ack_status: "UNACKNOWLEDGED",
            triggered_at: payload.triggered_at || new Date().toISOString(),
            received_at: payload.triggered_at || new Date().toISOString(),
            acked_at: null,
          };
          setEvents((prev) => [newAlert, ...prev]);
          setNode((prev) => ({
            ...prev,
            connected: true,
            operating: true,
            state: "NORMAL",
            last_seen_at: null,
            last_event_type: `Mã ${payload.event_code} (Giá trị: ${payload.event_value})`,
          }));
        }
      }
    });

    return () => {
      unsubscribe();
    };
  }, [rawId, subscribe]);

  const chartData: TimeSeriesPoint[] = useMemo(() => {
    return events.map((ev) => ({
      id: ev.alert_id,
      timestamp: ev.triggered_at || ev.received_at,
      value: ev.event_value,
      code: ev.event_code,
      name: ev.event_code === 1 ? "Báo động nút nhấn (0x01)" : `Sự kiện 0x${ev.event_code.toString(16).padStart(2, "0").toUpperCase()}`,
      severity: ev.severity,
    }));
  }, [events]);

  const getSeverityBadge = (severity: AlertSeverity) => {
    switch (severity) {
      case "P0_EMERGENCY":
        return "bg-rose-500/10 text-rose-700 dark:text-rose-400 border-rose-500/20";
      case "P1_HIGH":
        return "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20";
      case "P2_MEDIUM":
        return "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20";
      default:
        return "bg-slate-500/10 text-slate-700 dark:text-slate-400 border-slate-500/20";
    }
  };

  const getAckBadge = (status: AlertAckStatus) => {
    if (status === "ACKNOWLEDGED") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
          <CheckCircle2 className="w-3 h-3" />
          <span>Đã xác nhận</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-500/20">
        <Bell className="w-3 h-3 animate-pulse" />
        <span>Chưa xác nhận</span>
      </span>
    );
  };

  const handleConfirmDelete = async () => {
    try {
      setIsDeleting(true);
      await deleteNode(node.node_id);
      setToastMessage(`Đã xóa thành công Node [${rawId}]. Đang chuyển hướng...`);
      setShowDeleteModal(false);
      setTimeout(() => {
        router.push("/nodes");
      }, 1000);
    } catch (err) {
      setToastMessage(`Lỗi khi xóa Node: ${err instanceof Error ? err.message : "Thất bại"}`);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <AppShell activeRoute="nodes">
      {/* Breadcrumb Navigation */}
      <div className="flex flex-col gap-1 mb-5">
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-text-secondary">
          <button
            type="button"
            onClick={() => router.push("/nodes")}
            className="flex items-center gap-1 hover:text-interactive transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Quản lý</span>
          </button>
          <ChevronRight className="w-3.5 h-3.5 text-text-secondary/60" />
          <Link href="/nodes" className="hover:text-interactive transition-colors">
            Node
          </Link>
          <ChevronRight className="w-3.5 h-3.5 text-text-secondary/60" />
          <span className="font-mono font-medium text-text-primary">{rawId}</span>
        </nav>

        {/* Top Header & Identity */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold font-mono text-text-primary tracking-tight">
              Node {rawId}
            </h1>
            <span className="text-base text-text-secondary font-medium">
              — {node.name || `Node ${node.node_id}`}
            </span>

            {/* Status Badges */}
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="px-2.5 py-1 rounded-md bg-canvas border border-border text-text-secondary font-medium">
                Gateway: <strong className="font-mono text-text-primary">{node.gateway_id}</strong>
              </span>
              <span className="px-2.5 py-1 rounded-md bg-canvas border border-border text-text-secondary font-medium">
                Khu vực: <strong className="text-text-primary">{node.area}</strong>
              </span>

              {node.connected ? (
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

              {node.operating ? (
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
              title={`Xóa Node ${rawId}`}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-state-critical bg-state-critical/10 hover:bg-state-critical hover:text-white border border-state-critical/20 transition-colors cursor-pointer"
            >
              <Trash2 className="w-4 h-4" />
              <span>Xóa Node</span>
            </button>
          )}
        </div>
      </div>

      {/* 4 Standard Device Cards (Zero-Shadow Baseline, DESIGN.md §4) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {/* Card 1: Giao thức & Định danh */}
        <div className="bg-chrome rounded-lg p-5 border border-border flex flex-col justify-between">
          <div className="flex items-center justify-between text-text-secondary">
            <span className="text-xs font-medium">Giao thức MAC</span>
            <Cpu className="w-4 h-4 text-interactive" />
          </div>
          <div className="my-2">
            <span className="text-2xl font-semibold font-mono tabular-nums text-text-primary tracking-tight">
              P2P CSMA/CAD
            </span>
          </div>
          <div className="text-xs text-text-secondary font-mono">
            Node ID: #{node.node_id} (0x{node.node_id.toString(16).padStart(2, "0").toUpperCase()})
          </div>
        </div>

        {/* Card 2: Điện áp Pin */}
        <div className="bg-chrome rounded-lg p-5 border border-border flex flex-col justify-between">
          <div className="flex items-center justify-between text-text-secondary">
            <span className="text-xs font-medium">Điện áp Pin</span>
            <Battery className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="my-2">
            <span className="text-3xl font-semibold font-mono tabular-nums text-text-primary tracking-tight">
              {node.battery_mv !== null ? `${node.battery_mv}` : "N/A"}
            </span>
            <span className="text-sm font-medium text-text-secondary ml-1.5">mV</span>
          </div>
          <div className="text-xs text-text-secondary">
            {node.battery_mv && node.battery_mv > 3000 ? "Tình trạng: Tốt (>3.0V)" : "Tình trạng: Yếu (<3.0V)"}
          </div>
        </div>

        {/* Card 3: Chất lượng RF */}
        <div className="bg-chrome rounded-lg p-5 border border-border flex flex-col justify-between">
          <div className="flex items-center justify-between text-text-secondary">
            <span className="text-xs font-medium">Chất lượng RF</span>
            <Radio className="w-4 h-4 text-interactive" />
          </div>
          <div className="my-2">
            <span className="text-3xl font-semibold font-mono tabular-nums text-text-primary tracking-tight">
              {node.last_rssi_dbm !== null ? `${node.last_rssi_dbm}` : "N/A"}
            </span>
            <span className="text-sm font-medium text-text-secondary ml-1.5">dBm</span>
          </div>
          <div className="text-xs text-text-secondary font-mono">
            SNR: {node.last_snr_db !== null ? `${node.last_snr_db} dB` : "N/A"}
          </div>
        </div>

        {/* Card 4: Tổng sự kiện thu nhận */}
        <div className="bg-chrome rounded-lg p-5 border border-border flex flex-col justify-between">
          <div className="flex items-center justify-between text-text-secondary">
            <span className="text-xs font-medium">Tổng sự kiện</span>
            <Radio className="w-4 h-4 text-text-secondary" />
          </div>
          <div className="my-2">
            <span className="text-2xl font-bold font-mono tabular-nums text-text-primary">
              {events.length}
            </span>
          </div>
          <div className="text-xs text-text-secondary font-mono truncate">
            {events.length > 0 ? "Thu nhận sự kiện realtime" : "Chưa có sự kiện"}
          </div>
        </div>
      </div>

      {/* Visual Time Series Event Chart */}
      <div className="mb-6">
        <TimeSeriesChart
          title="Biểu đồ sự kiện đo cảm biến theo thời gian"
          description={`Chuỗi dữ liệu thu nhận qua LoRa P2P từ Node #${node.node_id}`}
          data={chartData}
        />
      </div>

      {/* Discrete Event Logs Section (Event-Only V2 Architecture) */}
      <section className="bg-chrome rounded-lg border border-border overflow-hidden">
        <div className="p-5 pb-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="w-5 h-5 text-state-warning" />
            <div>
              <h2 className="text-base font-semibold text-text-primary">
                Nhật ký sự kiện cảnh báo (Event-Only V2 · UP_EVENT 0x41)
              </h2>
              <p className="text-xs text-text-secondary mt-0.5">
                Các sự kiện lỗi phát sinh từ nút cảm biến hiện trường, không giả định telemetry liên tục dạng sóng.
              </p>
            </div>
          </div>
          <span className="text-xs font-mono px-2 py-0.5 rounded bg-canvas border border-border text-text-secondary">
            {events.length} sự kiện ghi nhận
          </span>
        </div>

        <div className="overflow-x-auto w-full">
          <table className="w-full text-left border-collapse table-fixed min-w-[720px]">
            <thead>
              <tr className="h-10 bg-canvas/60 border-b border-border text-[13px] font-medium text-text-secondary uppercase tracking-wider">
                <th scope="col" className="py-2.5 pl-6 pr-3 font-semibold" style={{ width: "15%" }}>
                  Mã sự kiện
                </th>
                <th scope="col" className="py-2.5 px-3 font-semibold" style={{ width: "20%" }}>
                  Thời điểm kích hoạt
                </th>
                <th scope="col" className="py-2.5 px-3 font-semibold" style={{ width: "20%" }}>
                  Mã vi phạm / Loại lỗi
                </th>
                <th scope="col" className="py-2.5 px-3 font-semibold" style={{ width: "15%" }}>
                  Mức độ
                </th>
                <th scope="col" className="py-2.5 px-3 font-semibold" style={{ width: "15%" }}>
                  Giá trị đo
                </th>
                <th scope="col" className="py-2.5 pr-6 pl-3 font-semibold" style={{ width: "15%" }}>
                  Trạng thái xác nhận
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border text-sm">
              {events.length === 0 ? (
                <tr>
                  <td colSpan={6} className="h-28 text-center text-text-secondary text-sm">
                    Không có sự kiện cảnh báo bất thường nào được ghi nhận cho thiết bị này.
                  </td>
                </tr>
              ) : (
                events.map((ev) => (
                  <tr key={ev.alert_id} className="h-12 hover:bg-canvas/50 transition-colors">
                    <td className="pl-6 pr-3 py-2 font-mono tabular-nums text-text-primary font-medium">
                      #{ev.alert_id}
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums text-text-secondary text-xs">
                      {ev.triggered_at ? new Date(ev.triggered_at).toLocaleString("vi-VN") : "N/A"}
                    </td>
                    <td className="px-3 py-2 font-medium text-text-primary">
                      {ev.event_code === 1 ? "Báo động nút nhấn (0x01)" : `Sự kiện mã 0x${ev.event_code.toString(16).padStart(2, "0")}`}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold border ${getSeverityBadge(ev.severity)}`}>
                        {ev.severity}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono tabular-nums text-text-primary font-medium">
                      {ev.event_value}
                    </td>
                    <td className="pr-6 pl-3 py-2">
                      {getAckBadge(ev.ack_status)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Confirmation Modal for Safe Node Deletion (Issue #293) */}
      {showDeleteModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-node-detail-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
        >
          <div className="bg-surface border border-border rounded-xl shadow-none max-w-md w-full p-6 space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-state-critical/10 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-state-critical" />
              </div>
              <div className="space-y-1">
                <h3 id="delete-node-detail-modal-title" className="text-base font-semibold text-text-primary">
                  Xác nhận xóa Node
                </h3>
                <p className="text-sm text-text-secondary">
                  Bạn có chắc chắn muốn xóa và gỡ bỏ node{" "}
                  <span className="font-mono text-interactive font-semibold">{rawId}</span> (Trạm{" "}
                  <span className="font-semibold text-text-primary">{node.gateway_id}</span>)?
                </p>
              </div>
            </div>

            <div className="p-3 bg-state-critical/5 border border-state-critical/20 rounded-lg text-xs text-state-critical space-y-1">
              <div className="font-semibold flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" /> Cảnh báo rủi ro thiết bị:
              </div>
              <div>
                Hành động này sẽ ngắt kết nối, gỡ toàn bộ cấu hình node và thu hồi slot TDMA khỏi hệ thống.
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

export default function NodeDetailPage({ params }: NodeDetailProps) {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-canvas">
          <div className="flex items-center gap-3 text-text-secondary text-sm">
            <div className="w-5 h-5 border-2 border-interactive border-t-transparent rounded-full animate-spin" />
            <span>Đang tải thông tin chi tiết Node...</span>
          </div>
        </div>
      }
    >
      <NodeDetailContent params={params} />
    </Suspense>
  );
}
