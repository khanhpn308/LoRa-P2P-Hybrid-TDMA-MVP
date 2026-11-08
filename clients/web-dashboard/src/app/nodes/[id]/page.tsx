"use client";

import React, { useState, useEffect, use, Suspense } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { getNode } from "@/lib/api/nodes";
import { getAlerts } from "@/lib/api/alerts";
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
} from "lucide-react";
import { NodeSummary, Alert, AlertSeverity, AlertAckStatus } from "@/types/api";

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

  const initialNode: NodeDetailView = {
    node_id: parseInt(rawId.replace(/\D/g, "") || "1", 10),
    gateway_id: "--",
    name: `Node ${rawId}`,
    area: "Khu vực cảm biến",
    assigned_slot_id: null,
    connected: false,
    operating: false,
    state: "OFFLINE",
    last_event_type: "Chưa có sự kiện",
    last_seen_at: null,
    last_rssi_dbm: null,
    last_snr_db: null,
    battery_mv: 0,
    status: "OFFLINE",
    firmware_version: "ESP-IDF v6.1 · Node-TDMA",
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
          assigned_slot_id: realNode.assigned_slot_id,
          last_seen_at: realNode.last_seen_at,
          status: realNode.status,
          connected: realNode.status === "ONLINE",
          operating: realNode.status === "ONLINE" && realNode.assigned_slot_id !== null,
          state: realNode.status === "ONLINE" ? (realNode.assigned_slot_id !== null ? "NORMAL" : "MAINTENANCE") : "OFFLINE",
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
  }, [rawId]);

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
        </div>
      </div>

      {/* 4 Standard Device Cards (Zero-Shadow Baseline, DESIGN.md §4) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {/* Card 1: Định danh & Khe TDMA */}
        <div className="bg-chrome rounded-lg p-5 border border-border flex flex-col justify-between">
          <div className="flex items-center justify-between text-text-secondary">
            <span className="text-xs font-medium">Khe TDMA gán</span>
            <Cpu className="w-4 h-4 text-interactive" />
          </div>
          <div className="my-2">
            <span className="text-3xl font-semibold font-mono tabular-nums text-text-primary tracking-tight">
              {node.assigned_slot_id !== null ? `Slot ${node.assigned_slot_id}` : "Chưa gán"}
            </span>
          </div>
          <div className="text-xs text-text-secondary font-mono">
            Node ID: {node.node_id} (0x{node.node_id.toString(16).padStart(2, "0").toUpperCase()})
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

        {/* Card 4: Lần cuối nhìn thấy */}
        <div className="bg-chrome rounded-lg p-5 border border-border flex flex-col justify-between">
          <div className="flex items-center justify-between text-text-secondary">
            <span className="text-xs font-medium">Lần cuối nhìn thấy</span>
            <Clock className="w-4 h-4 text-text-secondary" />
          </div>
          <div className="my-2">
            <span className="text-base font-semibold font-mono tabular-nums text-text-primary">
              {node.last_seen_at ? new Date(node.last_seen_at).toLocaleTimeString("vi-VN") : "N/A"}
            </span>
          </div>
          <div className="text-xs text-text-secondary font-mono truncate" title={node.last_seen_at || ""}>
            {node.last_seen_at || "Chưa có dữ liệu"}
          </div>
        </div>
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
