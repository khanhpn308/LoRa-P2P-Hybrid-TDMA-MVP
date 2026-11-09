"use client";

import React, { useState, useMemo, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { NavItemKey } from "@/components/layout/Sidebar";
import { getNodes, getDeviceJoinRequests, approveDeviceJoinRequest, rejectDeviceJoinRequest, deleteNode } from "@/lib/api/nodes";
import { ProvisionDeviceModal } from "@/components/nodes/ProvisionDeviceModal";
import type { DeviceProvisionResponse } from "@/types/api";
import { useAuth } from "@/lib/auth/AuthContext";
import { useRealtime } from "@/lib/realtime/RealtimeContext";
import { ApiClientError } from "@/lib/api/client";
import {
  Search,
  Plus,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Cpu,
  CheckCircle2,
  X,
  Check,
  RotateCw,
  CheckCheck,
  ShieldCheck,
  AlertTriangle,
  Trash2,
} from "lucide-react";

export interface ConnectedNodeItem {
  id: string;
  node_id: number;
  gateway: string;
  area: string;
  connected: boolean;
  operating: boolean;
  state: "NORMAL" | "FAULT" | "MAINTENANCE" | "OFFLINE";
  battery_mv: number;
  last_event_type: string;
}

export interface NewNodeRequest {
  id: string;
  rawId: number;
  device_mac: string;
  gateway: string;
  area: string;
  rssi: string;
  signalQuality: "Tốt" | "Khá" | "Yếu";
  snr: string;
  time: string;
  relativeTime: string;
}

function NodesContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { role } = useAuth();
  const { subscribe } = useRealtime();

  // URL query params initialization (e.g. from Overview Node card click)
  const initialConn = searchParams.get("conn") || "all";
  const initialOps = searchParams.get("ops") || "all";
  const initialTab = searchParams.get("tab") === "new" ? "new" : "connected";

  const [activeRoute, setActiveRoute] = useState<NavItemKey>("nodes");
  const [activeTab, setActiveTab] = useState<"connected" | "new">(initialTab);

  // Tab 1 state: Connected Nodes
  const [connectedNodes, setConnectedNodes] = useState<ConnectedNodeItem[]>([]);
  const [searchConnected, setSearchConnected] = useState<string>("");
  const [selectedGateway, setSelectedGateway] = useState<string>("ALL");
  const [selectedArea, setSelectedArea] = useState<string>("ALL");
  const [connFilter, setConnFilter] = useState<string>(initialConn);
  const [opsFilter, setOpsFilter] = useState<string>(initialOps);
  const [rowsPerPage, setRowsPerPage] = useState<number>(10);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Tab 2 state: New Node Requests
  const [newNodes, setNewNodes] = useState<NewNodeRequest[]>([]);
  const [searchNew, setSearchNew] = useState<string>("");

  // Modal states
  const [approvingNode, setApprovingNode] = useState<NewNodeRequest | null>(null);
  const [rejectingNode, setRejectingNode] = useState<NewNodeRequest | null>(null);
  const [approveFormName, setApproveFormName] = useState<string>("");
  const [approveFormArea, setApproveFormArea] = useState<string>("Khu A - Phân xưởng Ép");
  const [deletingNode, setDeletingNode] = useState<ConnectedNodeItem | null>(null);
  const [isDeletingNode, setIsDeletingNode] = useState<boolean>(false);
  const [isProvisionModalOpen, setIsProvisionModalOpen] = useState<boolean>(false);

  // Toast feedback state
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  const handleProvisionSuccess = (resp: DeviceProvisionResponse) => {
    showToast(`Cấp phát thành công thiết bị [${resp.device_mac}] cho Network ${resp.network_id}!`);
    loadNodes();
  };

  const handleConfirmDeleteNode = async () => {
    if (!deletingNode) return;
    try {
      setIsDeletingNode(true);
      await deleteNode(deletingNode.node_id);
      showToast(`Đã xóa thành công Node [${deletingNode.id}].`);
      setDeletingNode(null);
      await loadNodes();
    } catch (err) {
      showToast(`Lỗi khi xóa Node: ${err instanceof Error ? err.message : "Thất bại"}`);
    } finally {
      setIsDeletingNode(false);
    }
  };

  const loadNodes = useCallback(async () => {
    try {
      const resp = await getNodes({ limit: 100 });
      if (resp && resp.items) {
        const mapped: ConnectedNodeItem[] = resp.items.map((n) => ({
          id: `N-${String(n.node_id).padStart(3, "0")}`,
          node_id: n.node_id,
          gateway: n.gateway_id,
          area: "Khu vực cảm biến",
          connected: n.status === "ONLINE",
          operating: n.status === "ONLINE",
          state: n.status === "ONLINE" ? "NORMAL" : "OFFLINE",
          battery_mv: 3300,
          last_event_type: n.status === "ONLINE" ? "P2P CSMA/CAD (Sẵn sàng)" : "Ngoại tuyến",
        }));
        setConnectedNodes(mapped);
      } else {
        setConnectedNodes([]);
      }
    } catch {
      setConnectedNodes([]);
    }

    try {
      const reqs = await getDeviceJoinRequests();
      if (reqs) {
        const mappedReqs: NewNodeRequest[] = reqs
          .filter((r) => r.status === "PENDING")
          .map((r) => ({
            id: `REQ-${r.id}`,
            rawId: r.id,
            device_mac: r.device_mac,
            gateway: r.gateway_id,
            area: "Khu vực cảm biến",
            rssi: `${r.rssi} dBm`,
            signalQuality: r.rssi > -80 ? "Tốt" : r.rssi > -100 ? "Khá" : "Yếu",
            snr: `${r.snr.toFixed(1)} dB`,
            time: new Date(r.created_at).toLocaleTimeString("vi-VN"),
            relativeTime: new Date(r.created_at).toLocaleString("vi-VN"),
          }));
        setNewNodes(mappedReqs);
      }
    } catch {
      // Graceful fallback
    }
  }, []);

  useEffect(() => {
    loadNodes();

    const unsubscribe = subscribe((envelope) => {
      if (envelope.type === "NODE_JOIN_REQUEST") {
        loadNodes();
        showToast("[Realtime] Có thiết bị mới gửi yêu cầu gia nhập mạng!");
      } else if (envelope.type === "ALERT_TRIGGERED") {
        loadNodes();
      }
    });

    return () => {
      unsubscribe();
    };
  }, [loadNodes, subscribe]);

  const handleRouteChange = (route: NavItemKey) => {
    setActiveRoute(route);
    if (route === "overview") router.push("/");
    else if (route === "monitoring") router.push("/monitoring");
    else if (route === "gateways") router.push("/gateways");
  };

  // Filtered Connected Nodes
  const filteredConnectedNodes = useMemo(() => {
    return connectedNodes.filter((node) => {
      if (searchConnected.trim() !== "") {
        const q = searchConnected.toLowerCase().trim();
        const matchId = node.id.toLowerCase().includes(q);
        const matchGw = node.gateway.toLowerCase().includes(q);
        const matchArea = node.area.toLowerCase().includes(q);
        if (!matchId && !matchGw && !matchArea) return false;
      }

      if (selectedGateway !== "ALL" && node.gateway !== selectedGateway) {
        return false;
      }

      if (selectedArea !== "ALL" && !node.area.includes(selectedArea)) {
        return false;
      }

      if (connFilter === "connected" && !node.connected) return false;
      if (connFilter === "disconnected" && node.connected) return false;

      if (opsFilter === "active" && !node.operating) return false;
      if (opsFilter === "inactive" && node.operating) return false;

      return true;
    });
  }, [connectedNodes, searchConnected, selectedGateway, selectedArea, connFilter, opsFilter]);

  // Pagination for Connected Nodes
  const totalConnected = filteredConnectedNodes.length;
  const totalPages = Math.max(1, Math.ceil(totalConnected / rowsPerPage));
  const startIndex = (currentPage - 1) * rowsPerPage;
  const paginatedConnectedNodes = filteredConnectedNodes.slice(
    startIndex,
    startIndex + rowsPerPage
  );

  // Filtered New Nodes
  const filteredNewNodes = useMemo(() => {
    return newNodes.filter((n) => {
      if (searchNew.trim() === "") return true;
      const q = searchNew.toLowerCase().trim();
      return (
        n.id.toLowerCase().includes(q) ||
        n.device_mac.toLowerCase().includes(q) ||
        n.gateway.toLowerCase().includes(q)
      );
    });
  }, [newNodes, searchNew]);

  // Row navigation: DESIGN.md §7 mandates:
  // "Entire row navigates to the relevant Node detail page, not to an incident modal."
  const handleRowClick = (node: ConnectedNodeItem) => {
    router.push(`/nodes/${node.id}`);
  };

  // Modal actions
  const handleOpenApproveModal = (node: NewNodeRequest) => {
    if (role === "VIEWER") {
      showToast("Quyền VIEWER chỉ có quyền xem, không được phép cấp phát thiết bị.");
      return;
    }
    setApprovingNode(node);
    setApproveFormName(`Cảm biến ${node.area.includes("Ép") ? "Nhiệt độ" : "Tốc độ"} - ${node.id}`);
    setApproveFormArea(node.area);
  };

  const handleConfirmApproval = async () => {
    if (!approvingNode) return;
    if (role === "VIEWER") {
      showToast("Quyền VIEWER không có quyền cấp phát thiết bị.");
      return;
    }

    try {
      const res = await approveDeviceJoinRequest(approvingNode.rawId);
      setApprovingNode(null);
      showToast(
        `Đã phê duyệt Node [${approvingNode.device_mac}] thành công! Cấp Node ID #${res.assigned_node_id}.`
      );
      await loadNodes();
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 403) {
        showToast("Lỗi 403: Bạn không có quyền ADMIN để cấp phát thiết bị.");
      } else {
        showToast(`Lỗi khi phê duyệt thiết bị: ${(err as Error).message}`);
      }
    }
  };

  const handleOpenRejectModal = (node: NewNodeRequest) => {
    if (role === "VIEWER") {
      showToast("Quyền VIEWER không thể từ chối thiết bị.");
      return;
    }
    setRejectingNode(node);
  };

  const handleConfirmRejection = async () => {
    if (!rejectingNode) return;
    try {
      await rejectDeviceJoinRequest(rejectingNode.rawId);
      setRejectingNode(null);
      showToast(`Đã từ chối yêu cầu gia nhập của Node [${rejectingNode.device_mac}].`);
      await loadNodes();
    } catch (err) {
      showToast(`Lỗi khi từ chối thiết bị: ${(err as Error).message}`);
    }
  };

  const handleApproveAll = async () => {
    if (newNodes.length === 0) return;
    let count = 0;
    for (const n of newNodes) {
      try {
        await approveDeviceJoinRequest(n.rawId);
        count++;
      } catch {
        // Continue with others
      }
    }
    showToast(`Đã phê duyệt thành công ${count}/${newNodes.length} Node mới vào mạng!`);
    await loadNodes();
  };

  return (
    <AppShell activeRoute={activeRoute} onRouteChange={handleRouteChange}>
      <div className="space-y-4">
        {/* PAGE HEADER: Title, Subtitle & Primary Button */}
        <section
          aria-label="Tiêu đề quản lý Node"
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 min-h-[40px]"
        >
          <div className="flex flex-col gap-0.5">
            <h1 className="text-2xl font-semibold text-text-primary tracking-tight leading-8">
              Node
            </h1>
            <p className="text-xs text-text-secondary">
              Danh sách thiết bị cảm biến đầu cuối LoRa P2P toàn hệ thống
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            {role === "ADMIN" && (
              <button
                type="button"
                onClick={() => setIsProvisionModalOpen(true)}
                className="h-10 px-4 bg-interactive hover:bg-interactive-hover active:bg-blue-700 text-white font-medium text-sm rounded-lg inline-flex items-center gap-2 transition-colors shadow-none focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 focus:ring-offset-canvas cursor-pointer"
              >
                <ShieldCheck className="w-4 h-4 shrink-0" />
                <span>Cấp phát thiết bị</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setActiveTab("new")}
              className="h-10 px-4 bg-canvas hover:bg-surface border border-border text-text-primary font-medium text-sm rounded-lg inline-flex items-center gap-2 transition-colors shadow-none focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 focus:ring-offset-canvas cursor-pointer"
            >
              <Plus className="w-4 h-4 shrink-0" />
              <span>Thêm Node</span>
            </button>
          </div>
        </section>

        {/* TABS HEADER: 2 Tabs (Node đang kết nối & Node mới) */}
        <div className="flex items-center gap-2 border-b border-border">
          {/* Tab 1: Node đang kết nối */}
          <button
            type="button"
            onClick={() => setActiveTab("connected")}
            className={`relative pb-3 px-2 flex items-center gap-2 text-sm font-medium transition-colors cursor-pointer ${
              activeTab === "connected"
                ? "text-interactive font-semibold border-b-2 border-interactive -mb-px"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            <Cpu className="w-4 h-4" />
            <span>Node đang kết nối</span>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-semibold tabular-nums ${
                activeTab === "connected"
                  ? "bg-interactive/10 text-interactive"
                  : "bg-canvas text-text-secondary border border-border"
              }`}
            >
              {connectedNodes.length}
            </span>
          </button>

          {/* Tab 2: Node mới (Yêu cầu gia nhập) */}
          <button
            type="button"
            onClick={() => setActiveTab("new")}
            className={`relative pb-3 px-2 flex items-center gap-2 text-sm font-medium transition-colors cursor-pointer ${
              activeTab === "new"
                ? "text-interactive font-semibold border-b-2 border-interactive -mb-px"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            <span>Node mới</span>
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              <span>{newNodes.length} yêu cầu</span>
            </span>
          </button>
        </div>

        {/* ======================================================== */}
        {/* VIEW 1: NODE ĐANG KẾT NỐI                                */}
        {/* ======================================================== */}
        {activeTab === "connected" && (
          <div className="space-y-4">
            {/* Filter Toolbar: Search + Gateway + Area */}
            <section
              aria-label="Bộ lọc Node đang kết nối"
              className="bg-surface border border-border rounded-lg p-3 shadow-none w-full"
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-3 w-full items-center">
                {/* Search Input */}
                <div className="lg:col-span-4 relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-secondary">
                    <Search className="w-4 h-4" />
                  </div>
                  <input
                    type="text"
                    value={searchConnected}
                    onChange={(e) => {
                      setSearchConnected(e.target.value);
                      setCurrentPage(1);
                    }}
                    placeholder="Tìm Node, Gateway, Khu vực..."
                    className="w-full h-10 pl-9 pr-8 bg-surface text-text-primary placeholder:text-text-secondary/60 border border-border rounded-lg text-sm font-normal focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                  />
                  {searchConnected && (
                    <button
                      type="button"
                      onClick={() => setSearchConnected("")}
                      className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-text-secondary hover:text-text-primary"
                      title="Xóa tìm kiếm"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {/* Gateway Select */}
                <div className="lg:col-span-2 relative">
                  <select
                    value={selectedGateway}
                    onChange={(e) => {
                      setSelectedGateway(e.target.value);
                      setCurrentPage(1);
                    }}
                    className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm font-medium appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer"
                  >
                    <option value="ALL">Tất cả Gateway</option>
                    <option value="GW-01">GW-01 (Nhà máy Ép 1)</option>
                    <option value="GW-02">GW-02 (Trạm Bơm 2)</option>
                    <option value="GW-03">GW-03 (Kho Lạnh C)</option>
                    <option value="GW-09">GW-09 (Ngoài trời 1)</option>
                  </select>
                  <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>

                {/* Area Select */}
                <div className="lg:col-span-2 relative">
                  <select
                    value={selectedArea}
                    onChange={(e) => {
                      setSelectedArea(e.target.value);
                      setCurrentPage(1);
                    }}
                    className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm font-medium appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer"
                  >
                    <option value="ALL">Tất cả khu vực</option>
                    <option value="Khu A">Khu A - Phân xưởng Ép</option>
                    <option value="Khu B">Khu B - Trạm Bơm & Thủy lực</option>
                    <option value="Khu C">Khu C - Kho lạnh Công nghiệp</option>
                    <option value="Ngoài trời">Trạm Thu phát Ngoài trời</option>
                  </select>
                  <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>

                {/* Quick Status Select */}
                <div className="lg:col-span-2 relative">
                  <select
                    value={connFilter}
                    onChange={(e) => {
                      setConnFilter(e.target.value);
                      setCurrentPage(1);
                    }}
                    className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm font-medium appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer"
                  >
                    <option value="all">Kết nối: Tất cả</option>
                    <option value="connected">Đã kết nối</option>
                    <option value="disconnected">Mất kết nối</option>
                  </select>
                  <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>

                {/* Quick Operating Select */}
                <div className="lg:col-span-2 relative">
                  <select
                    value={opsFilter}
                    onChange={(e) => {
                      setOpsFilter(e.target.value);
                      setCurrentPage(1);
                    }}
                    className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm font-medium appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer"
                  >
                    <option value="all">Hoạt động: Tất cả</option>
                    <option value="active">Đang hoạt động</option>
                    <option value="inactive">Dừng hoạt động</option>
                  </select>
                  <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>
              </div>
            </section>

            {/* Connected Nodes Data Table (5 columns) */}
            <section
              aria-label="Bảng danh sách Node đang kết nối"
              className="bg-surface border border-border rounded-lg overflow-hidden shadow-none flex flex-col justify-between"
            >
              <div className="overflow-x-auto w-full">
                <table className="w-full text-left border-collapse table-fixed min-w-[720px]">
                  <thead>
                    <tr className="h-11 bg-canvas/60 border-b border-border text-[13px] font-medium text-text-secondary uppercase tracking-wider">
                      <th scope="col" className="py-2.5 pl-6 pr-4 font-semibold" style={{ width: "16%" }}>
                        Mã Node
                      </th>
                      <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "20%" }}>
                        Gateway
                      </th>
                      <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "28%" }}>
                        Khu vực
                      </th>
                      <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "18%" }}>
                        Kết nối
                      </th>
                      <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: role === "ADMIN" ? "16%" : "18%" }}>
                        Hoạt động
                      </th>
                      {role === "ADMIN" && (
                        <th scope="col" className="py-2.5 pr-6 pl-2 font-semibold text-right" style={{ width: "12%" }}>
                          Thao tác
                        </th>
                      )}
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-border text-sm">
                    {paginatedConnectedNodes.length === 0 ? (
                      <tr>
                        <td colSpan={role === "ADMIN" ? 6 : 5} className="h-32 text-center text-text-secondary text-sm">
                          Không tìm thấy Node nào phù hợp với bộ lọc.
                        </td>
                      </tr>
                    ) : (
                      paginatedConnectedNodes.map((node) => (
                        <tr
                          key={node.id}
                          onClick={() => handleRowClick(node)}
                          title={`Xem chi tiết Node ${node.id}`}
                          className="h-12 hover:bg-interactive-subtle/40 transition-colors cursor-pointer group"
                        >
                          {/* 1. Mã Node */}
                          <td className="py-3 pl-6 pr-4">
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold bg-interactive/10 text-interactive group-hover:underline underline-offset-2">
                              {node.id}
                            </span>
                          </td>

                          {/* 2. Gateway */}
                          <td className="py-3 px-4 font-mono font-medium text-text-primary text-sm">
                            {node.gateway}
                          </td>

                          {/* 3. Khu vực */}
                          <td className="py-3 px-4 font-medium text-text-secondary text-sm">
                            {node.area}
                          </td>

                          {/* 4. Kết nối */}
                          <td className="py-3 px-4">
                            {node.connected ? (
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

                          {/* 5. Hoạt động */}
                          <td className="py-3 px-4">
                            <div className="flex items-center justify-between">
                              {node.operating ? (
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
                              {role !== "ADMIN" && (
                                <ChevronRight className="w-4 h-4 text-text-secondary group-hover:text-interactive group-hover:translate-x-0.5 transition-all shrink-0" />
                              )}
                            </div>
                          </td>

                          {/* 6. Thao tác xóa an toàn (Chỉ ADMIN) */}
                          {role === "ADMIN" && (
                            <td className="py-3 pr-6 pl-2 text-right" onClick={(e) => e.stopPropagation()}>
                              <div className="inline-flex items-center justify-end gap-2">
                                <button
                                  type="button"
                                  onClick={() => setDeletingNode(node)}
                                  title={`Xóa Node ${node.id}`}
                                  aria-label={`Xóa Node ${node.id}`}
                                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-state-critical bg-state-critical/10 hover:bg-state-critical hover:text-white rounded border border-state-critical/20 transition-colors cursor-pointer"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                  <span>Xóa</span>
                                </button>
                                <ChevronRight className="w-4 h-4 text-text-secondary group-hover:text-interactive group-hover:translate-x-0.5 transition-all shrink-0" />
                              </div>
                            </td>
                          )}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination Footer */}
              <div className="p-4 border-t border-border bg-surface flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-text-secondary">
                <div className="flex items-center gap-2">
                  <label htmlFor="rows-node-select" className="text-xs font-medium text-text-secondary">
                    Hiển thị
                  </label>
                  <div className="relative">
                    <select
                      id="rows-node-select"
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

                <div className="flex items-center gap-4">
                  <span className="font-mono text-xs text-text-secondary tabular-nums">
                    {totalConnected === 0
                      ? "0 / 0 Node"
                      : `${startIndex + 1}–${Math.min(startIndex + rowsPerPage, totalConnected)} / ${totalConnected} Node`}
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
          </div>
        )}

        {/* ======================================================== */}
        {/* VIEW 2: NODE MỚI (YÊU CẦU GIA NHẬP MẠNG)                  */}
        {/* ======================================================== */}
        {activeTab === "new" && (
          <div className="space-y-4">
            {/* Toolbar for New Nodes */}
            <section
              aria-label="Thao tác yêu cầu gia nhập"
              className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-surface border border-border rounded-lg p-3 shadow-none w-full"
            >
              <div className="flex items-center gap-3 w-full sm:w-auto">
                <div className="relative w-full sm:w-72">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-secondary">
                    <Search className="w-4 h-4" />
                  </div>
                  <input
                    type="text"
                    value={searchNew}
                    onChange={(e) => setSearchNew(e.target.value)}
                    placeholder="Tìm DevEUI, mã tạm..."
                    className="w-full h-10 pl-9 pr-3 bg-surface text-text-primary placeholder:text-text-secondary/60 border border-border rounded-lg text-sm font-normal focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                  />
                </div>
                <span className="text-xs text-text-secondary whitespace-nowrap">
                  {newNodes.length} yêu cầu đang chờ phê duyệt
                </span>
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                {role === "ADMIN" && (
                  <button
                    type="button"
                    onClick={() => setIsProvisionModalOpen(true)}
                    className="h-10 px-3 bg-surface hover:bg-canvas border border-border text-text-primary rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <ShieldCheck className="w-3.5 h-3.5 text-interactive" />
                    <span>Cấp phát thiết bị</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    loadNodes();
                    showToast("Đã làm mới danh sách yêu cầu gia nhập.");
                  }}
                  className="h-10 px-3 bg-canvas hover:bg-surface border border-border text-text-primary rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <RotateCw className="w-3.5 h-3.5" />
                  <span>Làm mới</span>
                </button>
                <button
                  type="button"
                  onClick={handleApproveAll}
                  disabled={newNodes.length === 0}
                  className="h-10 px-4 bg-interactive hover:bg-interactive-hover disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer shadow-none"
                >
                  <CheckCheck className="w-4 h-4" />
                  <span>Chấp thuận tất cả</span>
                </button>
              </div>
            </section>

            {/* New Nodes Data Table (6 columns) */}
            <section
              aria-label="Danh sách yêu cầu gia nhập"
              className="bg-surface border border-border rounded-lg overflow-hidden shadow-none flex flex-col justify-between"
            >
              <div className="overflow-x-auto w-full">
                <table className="w-full text-left border-collapse table-fixed min-w-[760px]">
                  <thead>
                    <tr className="h-11 bg-canvas/60 border-b border-border text-[13px] font-medium text-text-secondary uppercase tracking-wider">
                      <th scope="col" className="py-2.5 pl-6 pr-4 font-semibold" style={{ width: "24%" }}>
                        Device MAC / Thiết bị
                      </th>
                      <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "20%" }}>
                        Gateway thu nhận
                      </th>
                      <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "16%" }}>
                        Tín hiệu (RSSI/SNR)
                      </th>
                      <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "15%" }}>
                        Thời gian gửi
                      </th>
                      <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "13%" }}>
                        Trạng thái
                      </th>
                      <th scope="col" className="py-2.5 pr-6 pl-4 font-semibold text-right" style={{ width: "12%" }}>
                        Thao tác
                      </th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-border text-sm">
                    {filteredNewNodes.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="h-32 text-center text-text-secondary text-sm">
                          Không có yêu cầu gia nhập nào đang chờ xử lý.
                        </td>
                      </tr>
                    ) : (
                      filteredNewNodes.map((item) => (
                        <tr key={item.id} className="h-14 hover:bg-canvas/50 transition-colors">
                          {/* 1. Device MAC / Định danh */}
                          <td className="py-3 pl-6 pr-4">
                            <div className="flex flex-col">
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-text-primary text-sm">
                                  {item.id}
                                </span>
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 uppercase">
                                  Mới
                                </span>
                              </div>
                              <span className="font-mono text-xs text-interactive font-medium">
                                {item.device_mac}
                              </span>
                            </div>
                          </td>

                          {/* 2. Gateway thu nhận */}
                          <td className="py-3 px-4">
                            <div className="flex flex-col">
                              <span className="font-medium text-text-primary text-sm">
                                {item.gateway}
                              </span>
                              <span className="text-xs text-text-secondary">
                                {item.area}
                              </span>
                            </div>
                          </td>

                          {/* 3. Tín hiệu RSSI / SNR */}
                          <td className="py-3 px-4">
                            <div className="flex flex-col">
                              <div className="flex items-center gap-1.5">
                                <span className="font-mono font-medium text-text-primary text-xs">
                                  {item.rssi}
                                </span>
                                <span
                                  className={`text-[11px] font-medium ${
                                    item.signalQuality === "Tốt"
                                      ? "text-state-connected font-semibold"
                                      : item.signalQuality === "Khá"
                                      ? "text-blue-600 dark:text-blue-400"
                                      : "text-state-critical"
                                  }`}
                                >
                                  ({item.signalQuality})
                                </span>
                              </div>
                              <span className="font-mono text-[11px] text-text-secondary">
                                SNR: {item.snr}
                              </span>
                            </div>
                          </td>

                          {/* 4. Thời gian gửi */}
                          <td className="py-3 px-4">
                            <div className="flex flex-col">
                              <span className="text-text-primary text-xs tabular-nums">
                                {item.time}
                              </span>
                              <span className="text-[11px] text-text-secondary">
                                {item.relativeTime}
                              </span>
                            </div>
                          </td>

                          {/* 5. Trạng thái */}
                          <td className="py-3 px-4">
                            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                              <span>Chờ phê duyệt</span>
                            </span>
                          </td>

                          {/* 6. Thao tác */}
                          <td className="py-3 pr-6 pl-4 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                type="button"
                                onClick={() => handleOpenApproveModal(item)}
                                className="h-8 px-2.5 rounded-md bg-interactive hover:bg-interactive-hover text-white text-xs font-medium inline-flex items-center gap-1 transition-colors cursor-pointer"
                                title="Chấp thuận Node này"
                              >
                                <Check className="w-3.5 h-3.5" />
                                <span>Chấp thuận</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => handleOpenRejectModal(item)}
                                className="h-8 px-2 rounded-md bg-canvas hover:bg-red-50 dark:hover:bg-red-950/40 text-text-secondary hover:text-state-critical border border-border transition-colors cursor-pointer"
                                title="Từ chối yêu cầu gia nhập"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Footer */}
              <div className="p-4 border-t border-border bg-surface flex items-center justify-between text-xs text-text-secondary">
                <span>Hiển thị tất cả yêu cầu mới trong phiên</span>
                <span className="font-mono tabular-nums">
                  1–{filteredNewNodes.length} / {newNodes.length} Yêu cầu
                </span>
              </div>
            </section>
          </div>
        )}

        {/* ======================================================== */}
        {/* MODAL 1: CHẤP THUẬN NODE MỚI (Stitch 9c8843af872d40258316) */}
        {/* ======================================================== */}
        {approvingNode && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="approve-modal-title"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm select-none"
          >
            <div className="w-full max-w-[520px] bg-surface rounded-xl shadow-none border border-border overflow-hidden flex flex-col">
              {/* Modal Header */}
              <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-canvas">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-interactive/10 text-interactive flex items-center justify-center">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 id="approve-modal-title" className="text-base font-semibold text-text-primary leading-tight">
                      Xác nhận chấp thuận Node
                    </h3>
                    <p className="text-xs text-text-secondary">
                      Cấp quyền gia nhập mạng LoRa P2P cho thiết bị cảm biến
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setApprovingNode(null)}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-surface transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Modal Content */}
              <div className="p-6 flex flex-col gap-4 text-sm">
                {/* Node RF Specs Card */}
                <div className="p-3.5 bg-canvas rounded-lg border border-border">
                  <div className="grid grid-cols-2 gap-y-2 text-xs">
                    <div>
                      <span className="text-text-secondary block">Mã tạm Node:</span>
                      <span className="font-semibold text-text-primary">{approvingNode.id}</span>
                    </div>
                    <div>
                      <span className="text-text-secondary block">Gateway phát hiện:</span>
                      <span className="font-medium text-text-primary">{approvingNode.gateway}</span>
                    </div>
                    <div className="col-span-2">
                      <span className="text-text-secondary block">Device MAC thiết bị:</span>
                      <span className="font-mono font-medium text-interactive bg-surface px-2 py-0.5 rounded border border-border inline-block mt-0.5">
                        {approvingNode.device_mac}
                      </span>
                    </div>
                    <div>
                      <span className="text-text-secondary block">Tín hiệu sóng RSSI:</span>
                      <span className="font-medium text-text-primary">
                        {approvingNode.rssi}{" "}
                        <span className="text-state-connected font-semibold">
                          ({approvingNode.signalQuality})
                        </span>
                      </span>
                    </div>
                    <div>
                      <span className="text-text-secondary block">Tỷ số SNR:</span>
                      <span className="font-medium text-text-primary">{approvingNode.snr}</span>
                    </div>
                  </div>
                </div>

                {/* Form Inputs */}
                <div className="flex flex-col gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-text-primary">
                      Tên hiển thị Node <span className="text-state-critical">*</span>
                    </label>
                    <input
                      type="text"
                      value={approveFormName}
                      onChange={(e) => setApproveFormName(e.target.value)}
                      placeholder="Nhập tên thiết bị..."
                      className="w-full h-10 px-3 bg-surface text-text-primary border border-border rounded-lg text-sm focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                    />
                  </div>

                  <div className="flex flex-col gap-1">
                    <label className="text-xs font-medium text-text-primary">
                      Gán vào Khu vực <span className="text-state-critical">*</span>
                    </label>
                    <div className="relative">
                      <select
                        value={approveFormArea}
                        onChange={(e) => setApproveFormArea(e.target.value)}
                        className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer"
                      >
                        <option value="Khu A - Phân xưởng Ép">Khu A - Phân xưởng Ép</option>
                        <option value="Khu B - Trạm Bơm & Thủy lực">Khu B - Trạm Bơm & Thủy lực</option>
                        <option value="Khu C - Kho lạnh Công nghiệp">Khu C - Kho lạnh Công nghiệp</option>
                        <option value="Trạm Thu phát Ngoài trời">Trạm Thu phát Ngoài trời</option>
                      </select>
                      <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Modal Footer */}
              <div className="px-6 py-4 border-t border-border bg-canvas flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setApprovingNode(null)}
                  className="h-10 px-4 rounded-lg border border-border bg-surface hover:bg-canvas text-text-primary text-xs font-medium transition-colors cursor-pointer"
                >
                  Hủy bỏ
                </button>
                <button
                  type="button"
                  onClick={handleConfirmApproval}
                  className="h-10 px-4 rounded-lg bg-interactive hover:bg-interactive-hover text-white text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer shadow-none"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Xác nhận & Cấp quyền</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* MODAL 2: TỪ CHỐI GIA NHẬP (Stitch 25b32c42bc7249308d2e)    */}
        {/* ======================================================== */}
        {rejectingNode && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="reject-modal-title"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm select-none"
          >
            <div className="w-full max-w-[500px] bg-surface rounded-xl shadow-none border border-border overflow-hidden flex flex-col">
              {/* Header */}
              <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-canvas">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-red-500/10 text-state-critical flex items-center justify-center">
                    <AlertTriangle className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 id="reject-modal-title" className="text-base font-semibold text-text-primary leading-tight">
                      Từ chối yêu cầu gia nhập
                    </h3>
                    <p className="text-xs text-text-secondary">
                      Hủy bỏ yêu cầu tham gia mạng LoRa P2P của thiết bị cảm biến
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setRejectingNode(null)}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-surface transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Body */}
              <div className="p-6 flex flex-col gap-4 text-sm">
                <div className="p-3.5 bg-canvas rounded-lg border border-border">
                  <div className="grid grid-cols-2 gap-y-2 text-xs">
                    <div>
                      <span className="text-text-secondary block">Mã tạm Node:</span>
                      <span className="font-semibold text-text-primary">{rejectingNode.id}</span>
                    </div>
                    <div>
                      <span className="text-text-secondary block">Gateway phát hiện:</span>
                      <span className="font-medium text-text-primary">{rejectingNode.gateway}</span>
                    </div>
                    <div className="col-span-2">
                      <span className="text-text-secondary block">Device MAC thiết bị:</span>
                      <span className="font-mono font-medium text-state-critical bg-surface px-2 py-0.5 rounded border border-border inline-block mt-0.5">
                        {rejectingNode.device_mac}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-start gap-2.5 p-3 rounded-lg bg-red-500/10 text-text-primary border border-red-500/20">
                  <AlertTriangle className="w-5 h-5 text-state-critical shrink-0 mt-0.5" />
                  <p className="text-xs leading-relaxed">
                    <span className="font-semibold text-state-critical">Xác nhận:</span> Bạn có chắc chắn muốn từ chối yêu cầu gia nhập của Node này không? Phiên yêu cầu kết nối sẽ bị hủy bỏ ngay lập tức.
                  </p>
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-border bg-canvas flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setRejectingNode(null)}
                  className="h-10 px-4 rounded-lg border border-border bg-surface hover:bg-canvas text-text-primary text-xs font-medium transition-colors cursor-pointer"
                >
                  Hủy bỏ
                </button>
                <button
                  type="button"
                  onClick={handleConfirmRejection}
                  className="h-10 px-4 rounded-lg bg-state-critical hover:bg-red-700 text-white text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer shadow-none"
                >
                  <X className="w-4 h-4" />
                  <span>Xác nhận từ chối</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Confirmation Modal for Safe Node Deletion (Issue #293) */}
        {deletingNode && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-node-modal-title"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
          >
            <div className="bg-surface border border-border rounded-xl shadow-none max-w-md w-full p-6 space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-full bg-state-critical/10 flex items-center justify-center shrink-0">
                  <AlertTriangle className="w-5 h-5 text-state-critical" />
                </div>
                <div className="space-y-1">
                  <h3 id="delete-node-modal-title" className="text-base font-semibold text-text-primary">
                    Xác nhận xóa Node
                  </h3>
                  <p className="text-sm text-text-secondary">
                    Bạn có chắc chắn muốn xóa và gỡ bỏ node{" "}
                    <span className="font-mono text-interactive font-semibold">{deletingNode.id}</span> (Trạm{" "}
                    <span className="font-semibold text-text-primary">{deletingNode.gateway}</span>)?
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
                  onClick={() => setDeletingNode(null)}
                  disabled={isDeletingNode}
                  className="h-9 px-4 rounded-lg border border-border bg-canvas hover:bg-canvas/80 text-text-secondary text-xs font-medium transition-colors cursor-pointer"
                >
                  Hủy bỏ
                </button>
                <button
                  type="button"
                  onClick={handleConfirmDeleteNode}
                  disabled={isDeletingNode}
                  className="h-9 px-4 rounded-lg bg-state-critical hover:bg-state-critical/90 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer flex items-center gap-2 disabled:opacity-50"
                >
                  {isDeletingNode ? "Đang xóa..." : "Xác nhận xóa"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Provision Device Modal (Issue #305) */}
        <ProvisionDeviceModal
          isOpen={isProvisionModalOpen}
          onClose={() => setIsProvisionModalOpen(false)}
          onSuccess={handleProvisionSuccess}
        />

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
      </div>
    </AppShell>
  );
}

export default function NodesPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-canvas">
          <div className="text-sm font-medium text-text-secondary">
            Đang tải dữ liệu Node...
          </div>
        </div>
      }
    >
      <NodesContent />
    </Suspense>
  );
}

