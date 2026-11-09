"use client";

import React, { useState, useMemo, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { NavItemKey } from "@/components/layout/Sidebar";
import {
  Search,
  Plus,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  KeyRound,
  UserX,
  UserCheck,
  CheckCircle2,
  X,
  RotateCw,
  Copy,
  Check,
  Eye,
  EyeOff,
  AlertTriangle,
  User,
  Shield,
} from "lucide-react";
import { UserRole } from "@/types/api";
import { getUsers, createUser, updateUserStatus, updateUserRole, resetUserPassword } from "@/lib/api/users.ts";
import { ApiClientError } from "@/lib/api/client.ts";

export type { UserRole };
export type UserStatus = "active" | "disabled";

export interface UserItem {
  id: string;
  username: string;
  fullName: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  lastLogin: string;
}

const ROLE_LABELS: Record<UserRole, { label: string; tag: string; description: string; badgeClass: string }> = {
  ADMIN: {
    label: "Quản trị viên (Super Admin)",
    tag: "Cấp cao nhất",
    description: "Toàn quyền quản trị hệ thống, cấp phát thiết bị, phê duyệt/kích hoạt lịch TDMA, cấp kênh và quản lý người dùng.",
    badgeClass: "bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/20",
  },
  OPERATOR: {
    label: "Vận hành viên (Operator)",
    tag: "Phù hợp trực ca",
    description: "Giám sát toàn bộ dữ liệu viễn thông, theo dõi cảnh báo sự kiện, xác nhận sự cố, yêu cầu sinh lịch TDMA.",
    badgeClass: "bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/20",
  },
  VIEWER: {
    label: "Người xem (Viewer / Auditor)",
    tag: "Chỉ đọc",
    description: "Chỉ có quyền xem báo cáo, theo dõi thông số thời gian thực và luồng sự kiện qua WebSocket. Không thể thay đổi cấu hình.",
    badgeClass: "bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20",
  },
};

function UsersContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialRoleParam = searchParams.get("role") || "all";

  const [activeRoute, setActiveRoute] = useState<NavItemKey>("users");
  const [users, setUsers] = useState<UserItem[]>([]);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [roleFilter, setRoleFilter] = useState<string>(initialRoleParam);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [rowsPerPage, setRowsPerPage] = useState<number>(10);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Modal States

  const loadUsers = useCallback(async () => {
    try {
      const data = await getUsers();
      if (Array.isArray(data)) {
        const mapped: UserItem[] = data.map((u) => ({
          id: u.id,
          username: u.username,
          fullName: u.full_name || (u.username === "admin" ? "Quản trị viên Hệ thống" : (u.username === "operator01" ? "Trần Vận Hành" : u.username)),
          email: u.email || `${u.username}@iiot-lora.vn`,
          role: (u.role as UserRole) || "VIEWER",
          status: u.is_active ? "active" : "disabled",
          lastLogin: u.created_at ? new Date(u.created_at).toLocaleDateString("vi-VN") : "Hôm nay",
        }));
        setUsers(mapped);
        return;
      }
      setUsers([]);
    } catch {
      setUsers([]);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const [roleModalUser, setRoleModalUser] = useState<UserItem | null>(null);
  const [selectedNewRole, setSelectedNewRole] = useState<UserRole>("OPERATOR");

  const [passwordModalUser, setPasswordModalUser] = useState<UserItem | null>(null);
  const [passwordMode, setPasswordMode] = useState<"auto" | "manual">("auto");
  const [generatedPassword, setGeneratedPassword] = useState<string>("LoRa#2026!k9Qx");
  const [manualPassword, setManualPassword] = useState<string>("");
  const [manualConfirmPassword, setManualConfirmPassword] = useState<string>("");
  const [showPasswordText, setShowPasswordText] = useState<boolean>(false);
  const [copiedPassword, setCopiedPassword] = useState<boolean>(false);

  const [statusModalUser, setStatusModalUser] = useState<UserItem | null>(null);
  const [showAddUserModal, setShowAddUserModal] = useState<boolean>(false);
  const [newUsername, setNewUsername] = useState<string>("");
  const [newFullName, setNewFullName] = useState<string>("");
  const [newEmail, setNewEmail] = useState<string>("");
  const [newRole, setNewRole] = useState<UserRole>("OPERATOR");
  const [newPassword, setNewPassword] = useState<string>("");
  const [newConfirmPassword, setNewConfirmPassword] = useState<string>("");
  const [showNewPassword, setShowNewPassword] = useState<boolean>(false);
  const [showNewConfirmPassword, setShowNewConfirmPassword] = useState<boolean>(false);
  const [isSubmittingUser, setIsSubmittingUser] = useState<boolean>(false);
  const [addUserError, setAddUserError] = useState<string | null>(null);

  const resetAddUserForm = () => {
    setNewUsername("");
    setNewFullName("");
    setNewEmail("");
    setNewRole("OPERATOR");
    setNewPassword("");
    setNewConfirmPassword("");
    setShowNewPassword(false);
    setShowNewConfirmPassword(false);
    setAddUserError(null);
    setIsSubmittingUser(false);
  };

  // Toast feedback state
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  const handleRouteChange = (route: NavItemKey) => {
    setActiveRoute(route);
    if (route === "overview") router.push("/");
    else if (route === "monitoring") router.push("/monitoring");
    else if (route === "gateways") router.push("/gateways");
    else if (route === "nodes") router.push("/nodes");
  };

  // Filtered users
  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      if (searchQuery.trim() !== "") {
        const q = searchQuery.toLowerCase().trim();
        const matchUsername = u.username.toLowerCase().includes(q);
        const matchName = u.fullName.toLowerCase().includes(q);
        const matchEmail = u.email.toLowerCase().includes(q);
        if (!matchUsername && !matchName && !matchEmail) return false;
      }

      if (roleFilter !== "all" && u.role !== roleFilter) return false;
      if (statusFilter !== "all" && u.status !== statusFilter) return false;

      return true;
    });
  }, [users, searchQuery, roleFilter, statusFilter]);

  // Pagination calculation
  const totalCount = filteredUsers.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / rowsPerPage));
  const startIndex = (currentPage - 1) * rowsPerPage;
  const paginatedUsers = filteredUsers.slice(startIndex, startIndex + rowsPerPage);

  // Modal Triggers
  const openRoleModal = (user: UserItem) => {
    setRoleModalUser(user);
    setSelectedNewRole(user.role);
  };

  const confirmRoleChange = async () => {
    if (!roleModalUser) return;
    try {
      await updateUserRole(roleModalUser.id || roleModalUser.username, selectedNewRole);
      setUsers((prev) =>
        prev.map((u) => (u.id === roleModalUser.id ? { ...u, role: selectedNewRole } : u))
      );
      showToast(
        `Đã cập nhật vai trò cho [${roleModalUser.username}] thành [${ROLE_LABELS[selectedNewRole].label.split(" (")[0]}].`
      );
      setRoleModalUser(null);
    } catch (err) {
      const msg = err instanceof ApiClientError ? err.message : (err instanceof Error ? err.message : "Đổi vai trò thất bại");
      showToast(`Lỗi: ${msg}`);
    }
  };

  const openPasswordModal = (user: UserItem) => {
    setPasswordModalUser(user);
    setPasswordMode("auto");
    setGeneratedPassword(generateRandomPassword());
    setManualPassword("");
    setManualConfirmPassword("");
    setCopiedPassword(false);
  };

  const generateRandomPassword = () => {
    const list = [
      "LoRa#2026!k9Qx",
      "Scada@9182#mTxZ",
      "Iiot$Mesh!v4B8",
      "Node&Gate#2026P",
      "SubGhz!7792$wQ",
    ];
    return list[Math.floor(Math.random() * list.length)];
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(generatedPassword);
    setCopiedPassword(true);
    setTimeout(() => setCopiedPassword(false), 2000);
  };

  const confirmPasswordReset = async () => {
    if (!passwordModalUser) return;
    const pwdToSet = passwordMode === "auto" ? generatedPassword : manualPassword.trim();
    if (pwdToSet.length < 8) {
      showToast("Mật khẩu phải có ít nhất 8 ký tự.");
      return;
    }
    try {
      await resetUserPassword(passwordModalUser.id || passwordModalUser.username, pwdToSet);
      showToast(`Đã cấp lại mật khẩu bảo mật cho tài khoản [${passwordModalUser.username}].`);
      setPasswordModalUser(null);
    } catch (err) {
      const msg = err instanceof ApiClientError ? err.message : (err instanceof Error ? err.message : "Đặt lại mật khẩu thất bại");
      showToast(`Lỗi: ${msg}`);
    }
  };

  const openStatusModal = (user: UserItem) => {
    setStatusModalUser(user);
  };

  const confirmStatusToggle = async () => {
    if (!statusModalUser) return;
    const nextActive = statusModalUser.status !== "active";
    try {
      const updated = await updateUserStatus(statusModalUser.id || statusModalUser.username, nextActive);
      const newStatus: UserStatus = updated.is_active ? "active" : "disabled";
      setUsers((prev) =>
        prev.map((u) => (u.id === statusModalUser.id ? { ...u, status: newStatus } : u))
      );
      showToast(
        newStatus === "active"
          ? `Đã kích hoạt lại tài khoản [${statusModalUser.username}].`
          : `Đã vô hiệu hóa tài khoản [${statusModalUser.username}].`
      );
      setStatusModalUser(null);
    } catch (err) {
      const msg = err instanceof ApiClientError ? err.message : (err instanceof Error ? err.message : "Cập nhật trạng thái thất bại");
      showToast(`Lỗi: ${msg}`);
    }
  };

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newFullName.trim()) {
      setAddUserError("Vui lòng điền đầy đủ tên tài khoản và họ tên hiển thị.");
      return;
    }
    if (newPassword.length < 8) {
      setAddUserError("Mật khẩu phải có ít nhất 8 ký tự.");
      return;
    }
    if (newPassword !== newConfirmPassword) {
      setAddUserError("Mật khẩu xác nhận không trùng khớp.");
      return;
    }

    setIsSubmittingUser(true);
    setAddUserError(null);

    try {
      const created = await createUser({
        username: newUsername.trim().toLowerCase(),
        full_name: newFullName.trim(),
        email: newEmail.trim() || `${newUsername.trim().toLowerCase()}@iiot-lora.vn`,
        password: newPassword,
        role: newRole,
      });

      await loadUsers();
      setShowAddUserModal(false);
      resetAddUserForm();
      showToast(`Đã tạo tài khoản mới [${created.username}] (${created.full_name || created.username}) thành công!`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Không thể tạo tài khoản mới. Vui lòng thử lại.";
      setAddUserError(msg);
    } finally {
      setIsSubmittingUser(false);
    }
  };

  return (
    <AppShell activeRoute={activeRoute} onRouteChange={handleRouteChange}>
      <div className="space-y-4">
        {/* PAGE HEADER: Title & Primary Button (Stitch screen 7b351f2cec7e432eb4d905186a7a978a) */}
        <section
          aria-label="Tiêu đề quản lý người dùng"
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 min-h-[40px]"
        >
          <div className="flex flex-col gap-0.5">
            <h1 className="text-2xl font-semibold text-text-primary tracking-tight leading-8">
              Người dùng
            </h1>
            <p className="text-xs text-text-secondary">
              Danh sách tài khoản và phân quyền truy cập hệ thống giám sát IIoT
            </p>
          </div>

          <div className="flex items-center shrink-0">
            <button
              type="button"
              onClick={() => setShowAddUserModal(true)}
              className="h-10 px-4 bg-interactive hover:bg-interactive-hover active:bg-blue-700 text-white font-medium text-sm rounded-lg inline-flex items-center gap-2 transition-colors shadow-none focus:outline-none focus:ring-2 focus:ring-interactive focus:ring-offset-2 focus:ring-offset-canvas"
            >
              <Plus className="w-4 h-4 shrink-0" />
              <span>Thêm người dùng</span>
            </button>
          </div>
        </section>

        {/* FILTER TOOLBAR: Search + Role Select + Status Select */}
        <section
          aria-label="Bộ lọc người dùng"
          className="bg-surface border border-border rounded-lg p-3 shadow-none w-full"
        >
          <div className="flex flex-wrap items-center gap-3 w-full">
            {/* Search Input */}
            <div className="relative flex-1 min-w-[240px] max-w-sm h-10">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-secondary">
                <Search className="w-4 h-4" />
              </div>
              <input
                id="user-search"
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                placeholder="Tìm tài khoản, tên hiển thị, email..."
                className="w-full h-10 pl-9 pr-8 bg-surface text-text-primary placeholder:text-text-secondary/60 border border-border rounded-lg text-sm font-normal focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive transition-colors"
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

            {/* Role Filter */}
            <div className="relative w-48 h-10">
              <label htmlFor="filter-role" className="sr-only">
                Bộ lọc vai trò
              </label>
              <select
                id="filter-role"
                value={roleFilter}
                onChange={(e) => {
                  setRoleFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm font-medium appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive transition-colors cursor-pointer"
              >
                <option value="all">Vai trò: Tất cả</option>
                <option value="ADMIN">Quản trị viên (Admin)</option>
                <option value="OPERATOR">Vận hành viên (Operator)</option>
                <option value="VIEWER">Người xem (Viewer)</option>
              </select>
              <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>

            {/* Status Filter */}
            <div className="relative w-44 h-10">
              <label htmlFor="filter-status" className="sr-only">
                Bộ lọc trạng thái
              </label>
              <select
                id="filter-status"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm font-medium appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive transition-colors cursor-pointer"
              >
                <option value="all">Trạng thái: Tất cả</option>
                <option value="active">Hoạt động</option>
                <option value="disabled">Vô hiệu hóa</option>
              </select>
              <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          </div>
        </section>

        {/* USERS DATA TABLE (Stitch 7b351f2cec7e432eb4d905186a7a978a) */}
        <section
          aria-label="Danh sách tài khoản người dùng"
          className="bg-surface border border-border rounded-lg overflow-hidden shadow-none flex flex-col justify-between"
        >
          <div className="overflow-x-auto w-full">
            <table className="w-full text-left border-collapse table-fixed min-w-[760px]">
              <thead>
                <tr className="h-11 bg-canvas/60 border-b border-border text-[13px] font-medium text-text-secondary uppercase tracking-wider">
                  <th scope="col" className="py-2.5 pl-6 pr-4 font-semibold" style={{ width: "18%" }}>
                    Tài khoản
                  </th>
                  <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "22%" }}>
                    Tên hiển thị
                  </th>
                  <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "18%" }}>
                    Vai trò
                  </th>
                  <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "16%" }}>
                    Trạng thái
                  </th>
                  <th scope="col" className="py-2.5 px-4 font-semibold" style={{ width: "16%" }}>
                    Đăng nhập gần nhất
                  </th>
                  <th scope="col" className="py-2.5 pr-6 pl-2 font-semibold text-right" style={{ width: "10%" }}>
                    Thao tác
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-border text-sm">
                {paginatedUsers.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="h-32 text-center text-text-secondary text-sm">
                      Không tìm thấy người dùng nào phù hợp với bộ lọc.
                    </td>
                  </tr>
                ) : (
                  paginatedUsers.map((u) => {
                    const roleMeta = ROLE_LABELS[u.role];
                    return (
                      <tr
                        key={u.id}
                        onClick={(e) => {
                          if ((e.target as HTMLElement).closest("button")) return;
                          router.push(`/users/${u.username}`);
                        }}
                        title={`Xem chi tiết tài khoản ${u.username}`}
                        className="h-12 hover:bg-interactive-subtle/40 transition-colors group cursor-pointer"
                      >
                        {/* 1. Tài khoản */}
                        <td className="py-3 pl-6 pr-4">
                          <span className="font-mono text-sm font-semibold text-interactive">
                            {u.username}
                          </span>
                        </td>

                        {/* 2. Tên hiển thị + Email */}
                        <td className="py-3 px-4">
                          <div className="flex flex-col">
                            <span className="font-medium text-text-primary text-sm">
                              {u.fullName}
                            </span>
                            <span className="text-xs text-text-secondary truncate max-w-[200px]">
                              {u.email}
                            </span>
                          </div>
                        </td>

                        {/* 3. Vai trò */}
                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${roleMeta.badgeClass}`}
                          >
                            {roleMeta.label.split(" (")[0]}
                          </span>
                        </td>

                        {/* 4. Trạng thái */}
                        <td className="py-3 px-4">
                          {u.status === "active" ? (
                            <div className="inline-flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full bg-state-connected shrink-0" />
                              <span className="text-[13px] font-medium text-state-connected">
                                Hoạt động
                              </span>
                            </div>
                          ) : (
                            <div className="inline-flex items-center gap-2">
                              <span className="w-2 h-2 rounded-full bg-text-secondary/60 shrink-0" />
                              <span className="text-[13px] font-medium text-text-secondary">
                                Vô hiệu hóa
                              </span>
                            </div>
                          )}
                        </td>

                        {/* 5. Đăng nhập gần nhất */}
                        <td className="py-3 px-4 font-mono text-xs text-text-secondary tabular-nums">
                          {u.lastLogin}
                        </td>

                        {/* 6. Thao tác (Action buttons directly available) */}
                        <td className="py-3 pr-6 pl-2 text-right">
                          <div className="inline-flex items-center justify-end gap-1">
                            {/* Role change button */}
                            <button
                              type="button"
                              onClick={() => openRoleModal(u)}
                              className="p-1.5 rounded hover:bg-canvas text-text-secondary hover:text-interactive transition-colors"
                              title="Đổi vai trò"
                            >
                              <ShieldCheck className="w-4 h-4" />
                            </button>

                            {/* Password reset button */}
                            <button
                              type="button"
                              onClick={() => openPasswordModal(u)}
                              className="p-1.5 rounded hover:bg-canvas text-text-secondary hover:text-interactive transition-colors"
                              title="Đặt lại mật khẩu"
                            >
                              <KeyRound className="w-4 h-4" />
                            </button>

                            {/* Disable / Enable toggle */}
                            <button
                              type="button"
                              onClick={() => openStatusModal(u)}
                              className={`p-1.5 rounded hover:bg-canvas transition-colors ${
                                u.status === "active"
                                  ? "text-text-secondary hover:text-state-critical"
                                  : "text-text-secondary hover:text-state-connected"
                              }`}
                              title={u.status === "active" ? "Vô hiệu hóa" : "Kích hoạt"}
                            >
                              {u.status === "active" ? (
                                <UserX className="w-4 h-4" />
                              ) : (
                                <UserCheck className="w-4 h-4" />
                              )}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          <div className="p-4 border-t border-border bg-surface flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-text-secondary">
            <div className="flex items-center gap-2">
              <label htmlFor="rows-user-select" className="text-xs font-medium text-text-secondary">
                Hiển thị
              </label>
              <div className="relative">
                <select
                  id="rows-user-select"
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
                {totalCount === 0
                  ? "0 / 0 người dùng"
                  : `${startIndex + 1}–${Math.min(startIndex + rowsPerPage, totalCount)} / ${totalCount} người dùng`}
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

        {/* ======================================================== */}
        {/* MODAL 1: ĐỔI VAI TRÒ (Stitch 7a2d7f7a00ea440f99bed618cabd0f6f) */}
        {/* ======================================================== */}
        {roleModalUser && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="role-modal-title"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm select-none"
          >
            <div className="w-full max-w-[560px] bg-surface rounded-xl shadow-none border border-border overflow-hidden flex flex-col">
              {/* Header */}
              <div className="px-6 py-4 border-b border-border flex items-start justify-between bg-canvas">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-lg bg-interactive/10 text-interactive flex items-center justify-center shrink-0">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 id="role-modal-title" className="text-base font-semibold text-text-primary leading-tight">
                      Đổi vai trò tài khoản
                    </h3>
                    <p className="text-xs text-text-secondary mt-0.5">
                      Phân quyền cấp độ truy cập hệ thống cho{" "}
                      <span className="font-semibold text-text-primary">{roleModalUser.username}</span> (
                      {roleModalUser.fullName})
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setRoleModalUser(null)}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-surface transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Body */}
              <div className="p-6 flex flex-col gap-4 text-sm max-h-[70vh] overflow-y-auto">
                <div className="flex items-center justify-between px-3.5 py-2.5 bg-canvas rounded-lg border border-border">
                  <span className="text-xs text-text-secondary">Vai trò đang áp dụng:</span>
                  <span className="text-xs font-medium px-2.5 py-0.5 rounded bg-surface text-text-primary border border-border flex items-center gap-1.5">
                    <Shield className="w-3.5 h-3.5 text-interactive" />
                    <span>{ROLE_LABELS[roleModalUser.role].label}</span>
                  </span>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <label className="text-xs font-semibold text-text-primary">
                    Chọn vai trò mới <span className="text-state-critical">*</span>
                  </label>
                  <span className="text-xs text-text-secondary">Chuẩn phân quyền RBAC IIoT</span>
                </div>

                {/* Radio list */}
                <div className="flex flex-col gap-2.5">
                  {(["ADMIN", "OPERATOR", "VIEWER"] as UserRole[]).map((r) => {
                    const isSelected = selectedNewRole === r;
                    const meta = ROLE_LABELS[r];
                    return (
                      <label
                        key={r}
                        onClick={() => setSelectedNewRole(r)}
                        className={`relative flex items-start gap-3 p-3.5 rounded-xl border transition-all cursor-pointer ${
                          isSelected
                            ? "bg-interactive/5 border-interactive"
                            : "bg-surface hover:bg-canvas border-border"
                        }`}
                      >
                        <div
                          className={`w-5 h-5 rounded-full mt-0.5 flex items-center justify-center shrink-0 border ${
                            isSelected
                              ? "bg-interactive border-interactive text-white"
                              : "border-border bg-canvas"
                          }`}
                        >
                          {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span
                              className={`text-sm font-semibold ${
                                isSelected ? "text-interactive" : "text-text-primary"
                              }`}
                            >
                              {meta.label}
                            </span>
                            <span className="text-[11px] font-medium text-text-secondary">
                              {meta.tag}
                            </span>
                          </div>
                          <p className="text-xs text-text-secondary mt-1 leading-relaxed">
                            {meta.description}
                          </p>
                        </div>
                      </label>
                    );
                  })}
                </div>

                {/* Security warning note */}
                <div className="p-3 rounded-lg bg-amber-500/10 text-amber-800 dark:text-amber-200 border border-amber-500/20 flex items-start gap-2.5 text-xs">
                  <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                  <p className="leading-relaxed">
                    <span className="font-semibold">Lưu ý quan trọng:</span> Thay đổi vai trò sẽ có hiệu lực ngay lập tức. Người dùng{" "}
                    <span className="font-semibold underline">{roleModalUser.username}</span> có thể cần đăng nhập lại để làm mới phạm vi quyền hạn được cấp.
                  </p>
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-border bg-canvas flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setRoleModalUser(null)}
                  className="h-10 px-4 rounded-lg border border-border bg-surface hover:bg-canvas text-text-primary text-xs font-medium transition-colors cursor-pointer"
                >
                  Hủy bỏ
                </button>
                <button
                  type="button"
                  onClick={confirmRoleChange}
                  className="h-10 px-5 rounded-lg bg-interactive hover:bg-interactive-hover text-white text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer shadow-none"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Cập nhật vai trò</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* MODAL 2: ĐẶT LẠI MẬT KHẨU (Stitch cbaf28f0406f4917a28587aa9) */}
        {/* ======================================================== */}
        {passwordModalUser && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="password-modal-title"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm select-none"
          >
            <div className="w-full max-w-[520px] bg-surface rounded-xl shadow-none border border-border overflow-hidden flex flex-col">
              {/* Header */}
              <div className="px-6 py-4 border-b border-border flex items-start justify-between bg-canvas">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-lg bg-interactive/10 text-interactive flex items-center justify-center shrink-0">
                    <KeyRound className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 id="password-modal-title" className="text-base font-semibold text-text-primary leading-tight">
                      Đặt lại mật khẩu
                    </h3>
                    <p className="text-xs text-text-secondary mt-0.5">
                      Cấp lại mật khẩu bảo mật mới cho tài khoản{" "}
                      <span className="font-semibold text-text-primary">{passwordModalUser.username}</span> (
                      {passwordModalUser.fullName})
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setPasswordModalUser(null)}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-surface transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Body */}
              <div className="p-6 flex flex-col gap-4 text-sm">
                {/* Method Selector Segment */}
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold text-text-primary">Phương thức cấp mật khẩu</span>
                  <div className="grid grid-cols-2 gap-1 p-1 bg-canvas rounded-lg border border-border">
                    <button
                      type="button"
                      onClick={() => setPasswordMode("auto")}
                      className={`h-8 rounded text-xs font-medium flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                        passwordMode === "auto"
                          ? "bg-surface text-interactive shadow-sm font-semibold border border-border"
                          : "text-text-secondary hover:text-text-primary"
                      }`}
                    >
                      <RotateCw className="w-3.5 h-3.5" />
                      <span>Tạo ngẫu nhiên</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setPasswordMode("manual")}
                      className={`h-8 rounded text-xs font-medium flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                        passwordMode === "manual"
                          ? "bg-surface text-interactive shadow-sm font-semibold border border-border"
                          : "text-text-secondary hover:text-text-primary"
                      }`}
                    >
                      <KeyRound className="w-3.5 h-3.5" />
                      <span>Đặt thủ công</span>
                    </button>
                  </div>
                </div>

                {/* Mode 1: Auto-generated Preview */}
                {passwordMode === "auto" && (
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-text-secondary">Mật khẩu tạm thời đề xuất (Chuẩn SCADA)</span>
                      <span className="text-state-connected font-medium flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Độ mạnh cao</span>
                      </span>
                    </div>

                    <div className="p-3 bg-canvas rounded-xl border border-border flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <KeyRound className="w-4 h-4 text-interactive shrink-0" />
                        <code className="font-mono text-base font-bold text-interactive tracking-wide select-all">
                          {generatedPassword}
                        </code>
                      </div>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => setGeneratedPassword(generateRandomPassword())}
                          className="p-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary transition-colors cursor-pointer"
                          title="Tạo chuỗi khác"
                        >
                          <RotateCw className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={copyToClipboard}
                          className="h-8 px-2.5 rounded bg-surface hover:bg-canvas border border-border text-interactive text-xs font-medium flex items-center gap-1 transition-colors cursor-pointer"
                        >
                          {copiedPassword ? (
                            <>
                              <Check className="w-3.5 h-3.5 text-state-connected" />
                              <span className="text-state-connected">Đã chép</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              <span>Sao chép</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Mode 2: Manual Input */}
                {passwordMode === "manual" && (
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-text-primary">Mật khẩu mới</label>
                      <div className="relative">
                        <input
                          type={showPasswordText ? "text" : "password"}
                          value={manualPassword}
                          onChange={(e) => setManualPassword(e.target.value)}
                          placeholder="Nhập tối thiểu 8 ký tự..."
                          className="w-full h-10 pl-3 pr-10 rounded-lg bg-surface border border-border text-sm text-text-primary focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPasswordText(!showPasswordText)}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary"
                        >
                          {showPasswordText ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>

                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-text-primary">Xác nhận mật khẩu</label>
                      <input
                        type={showPasswordText ? "text" : "password"}
                        value={manualConfirmPassword}
                        onChange={(e) => setManualConfirmPassword(e.target.value)}
                        placeholder="Nhập lại mật khẩu..."
                        className="w-full h-10 pl-3 pr-10 rounded-lg bg-surface border border-border text-sm text-text-primary focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                      />
                    </div>
                  </div>
                )}

                {/* Compliance checkboxes */}
                <div className="flex flex-col gap-2 pt-1 border-t border-border">
                  <label className="flex items-start gap-2.5 cursor-pointer text-xs">
                    <input
                      type="checkbox"
                      defaultChecked
                      className="w-4 h-4 mt-0.5 rounded text-interactive focus:ring-0 cursor-pointer accent-interactive"
                    />
                    <div className="flex flex-col">
                      <span className="text-text-primary font-medium">
                        Yêu cầu người dùng đổi mật khẩu ở lần đăng nhập tiếp theo
                      </span>
                      <span className="text-text-secondary text-[11px]">
                        Tuân thủ tiêu chuẩn an toàn an ninh công nghiệp ISO/IEC 27001
                      </span>
                    </div>
                  </label>

                  <label className="flex items-start gap-2.5 cursor-pointer text-xs">
                    <input
                      type="checkbox"
                      defaultChecked
                      className="w-4 h-4 mt-0.5 rounded text-interactive focus:ring-0 cursor-pointer accent-interactive"
                    />
                    <div className="flex flex-col">
                      <span className="text-text-primary font-medium">
                        Buộc đăng xuất khỏi tất cả phiên làm việc đang hoạt động
                      </span>
                      <span className="text-text-secondary text-[11px]">
                        Hủy bỏ vé xác thực Session Token trên mọi trình duyệt và trạm SCADA
                      </span>
                    </div>
                  </label>
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-border bg-canvas flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setPasswordModalUser(null)}
                  className="h-10 px-4 rounded-lg border border-border bg-surface hover:bg-canvas text-text-primary text-xs font-medium transition-colors cursor-pointer"
                >
                  Hủy bỏ
                </button>
                <button
                  type="button"
                  onClick={confirmPasswordReset}
                  className="h-10 px-5 rounded-lg bg-interactive hover:bg-interactive-hover text-white text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer shadow-none"
                >
                  <KeyRound className="w-4 h-4" />
                  <span>Xác nhận đặt lại</span>
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* MODAL 3: VÔ HIỆU HÓA / KÍCH HOẠT TÀI KHOẢN (Stitch 1843964b) */}
        {/* ======================================================== */}
        {statusModalUser && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="status-modal-title"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm select-none"
          >
            <div className="w-full max-w-[480px] bg-surface rounded-xl shadow-none border border-border overflow-hidden flex flex-col">
              {/* Header */}
              <div className="px-6 py-4 border-b border-border flex items-start justify-between bg-canvas">
                <div className="flex items-start gap-3">
                  <div
                    className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                      statusModalUser.status === "active"
                        ? "bg-red-500/10 text-state-critical"
                        : "bg-emerald-500/10 text-state-connected"
                    }`}
                  >
                    {statusModalUser.status === "active" ? (
                      <UserX className="w-5 h-5" />
                    ) : (
                      <UserCheck className="w-5 h-5" />
                    )}
                  </div>
                  <div>
                    <h3 id="status-modal-title" className="text-base font-semibold text-text-primary leading-tight">
                      {statusModalUser.status === "active"
                        ? "Vô hiệu hóa tài khoản"
                        : "Kích hoạt lại tài khoản"}
                    </h3>
                    <p className="text-xs text-text-secondary mt-0.5">
                      Cập nhật trạng thái truy cập cho người dùng{" "}
                      <span className="font-semibold text-text-primary">{statusModalUser.username}</span>
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setStatusModalUser(null)}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-surface transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Body */}
              <div className="p-6 flex flex-col gap-4 text-sm">
                <div className="p-3.5 bg-canvas rounded-lg border border-border text-xs space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Tài khoản:</span>
                    <span className="font-mono font-semibold text-text-primary">{statusModalUser.username}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Họ tên:</span>
                    <span className="font-medium text-text-primary">{statusModalUser.fullName}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Vai trò:</span>
                    <span className="text-text-primary">{ROLE_LABELS[statusModalUser.role].label.split(" (")[0]}</span>
                  </div>
                </div>

                <div
                  className={`p-3 rounded-lg border flex items-start gap-2.5 text-xs ${
                    statusModalUser.status === "active"
                      ? "bg-red-500/10 border-red-500/20 text-text-primary"
                      : "bg-emerald-500/10 border-emerald-500/20 text-text-primary"
                  }`}
                >
                  <AlertTriangle
                    className={`w-4 h-4 shrink-0 mt-0.5 ${
                      statusModalUser.status === "active" ? "text-state-critical" : "text-state-connected"
                    }`}
                  />
                  <p className="leading-relaxed">
                    {statusModalUser.status === "active" ? (
                      <>
                        <span className="font-semibold text-state-critical">Xác nhận:</span> Tài khoản này sẽ bị thu hồi toàn bộ quyền đăng nhập và các phiên kết nối đang mở sẽ bị đóng ngay lập tức.
                      </>
                    ) : (
                      <>
                        <span className="font-semibold text-state-connected">Xác nhận:</span> Tài khoản sẽ được phục hồi quyền truy cập và có thể đăng nhập bình thường vào hệ thống.
                      </>
                    )}
                  </p>
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-border bg-canvas flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setStatusModalUser(null)}
                  className="h-10 px-4 rounded-lg border border-border bg-surface hover:bg-canvas text-text-primary text-xs font-medium transition-colors cursor-pointer"
                >
                  Hủy bỏ
                </button>
                <button
                  type="button"
                  onClick={confirmStatusToggle}
                  className={`h-10 px-5 rounded-lg text-white text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer shadow-none ${
                    statusModalUser.status === "active"
                      ? "bg-state-critical hover:bg-red-700"
                      : "bg-state-connected hover:bg-emerald-700"
                  }`}
                >
                  {statusModalUser.status === "active" ? (
                    <>
                      <UserX className="w-4 h-4" />
                      <span>Xác nhận vô hiệu hóa</span>
                    </>
                  ) : (
                    <>
                      <UserCheck className="w-4 h-4" />
                      <span>Xác nhận kích hoạt</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ======================================================== */}
        {/* MODAL 4: THÊM NGƯỜI DÙNG MỚI                             */}
        {/* ======================================================== */}
        {showAddUserModal && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-user-modal-title"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm select-none"
          >
            <form
              onSubmit={handleAddUser}
              className="w-full max-w-[500px] bg-surface rounded-xl shadow-none border border-border overflow-hidden flex flex-col"
            >
              {/* Header */}
              <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-canvas">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-interactive/10 text-interactive flex items-center justify-center">
                    <User className="w-4 h-4" />
                  </div>
                  <h3 id="add-user-modal-title" className="text-base font-semibold text-text-primary">
                    Thêm tài khoản người dùng
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setShowAddUserModal(false);
                    resetAddUserForm();
                  }}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-surface transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Body */}
              <div className="p-6 flex flex-col gap-3.5 text-sm max-h-[75vh] overflow-y-auto">
                {addUserError && (
                  <div className="p-3 rounded-lg bg-state-critical/10 border border-state-critical/20 flex items-center gap-2 text-state-critical text-xs">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>{addUserError}</span>
                  </div>
                )}

                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-text-primary">
                    Tên tài khoản (Username) <span className="text-state-critical">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    placeholder="ví dụ: operator05"
                    className="w-full h-10 px-3 rounded-lg bg-surface border border-border text-sm text-text-primary focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-text-primary">
                    Họ và tên hiển thị <span className="text-state-critical">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={newFullName}
                    onChange={(e) => setNewFullName(e.target.value)}
                    placeholder="ví dụ: Nguyễn Hoàng Nam"
                    className="w-full h-10 px-3 rounded-lg bg-surface border border-border text-sm text-text-primary focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-text-primary">Hộp thư công vụ (Email)</label>
                  <input
                    type="email"
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    placeholder="ví dụ: nam.nh@iiot-lora.vn"
                    className="w-full h-10 px-3 rounded-lg bg-surface border border-border text-sm text-text-primary focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-text-primary">
                    Phân quyền vai trò <span className="text-state-critical">*</span>
                  </label>
                  <div className="relative">
                    <select
                      value={newRole}
                      onChange={(e) => setNewRole(e.target.value as UserRole)}
                      className="w-full h-10 pl-3 pr-8 bg-surface text-text-primary border border-border rounded-lg text-sm appearance-none focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive cursor-pointer"
                    >
                      <option value="OPERATOR">Vận hành viên (Operator)</option>
                      <option value="VIEWER">Người xem (Viewer / Auditor)</option>
                      <option value="ADMIN">Quản trị viên (Super Admin)</option>
                    </select>
                    <ChevronDown className="w-4 h-4 text-text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                  </div>
                </div>

                {/* Direct Password Input 1 */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-text-primary">
                    Mật khẩu <span className="text-state-critical">*</span>
                  </label>
                  <div className="relative">
                    <input
                      type={showNewPassword ? "text" : "password"}
                      required
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="Nhập mật khẩu (tối thiểu 8 ký tự)"
                      className="w-full h-10 pl-3 pr-10 rounded-lg bg-surface border border-border text-sm text-text-primary focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPassword(!showNewPassword)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary p-1 cursor-pointer"
                      title={showNewPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                    >
                      {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  {newPassword.length > 0 && newPassword.length < 8 && (
                    <span className="text-[11px] text-state-critical">
                      Mật khẩu phải có ít nhất 8 ký tự ({newPassword.length}/8).
                    </span>
                  )}
                </div>

                {/* Direct Password Input 2 (Confirm) */}
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-text-primary">
                    Nhập lại mật khẩu <span className="text-state-critical">*</span>
                  </label>
                  <div className="relative">
                    <input
                      type={showNewConfirmPassword ? "text" : "password"}
                      required
                      value={newConfirmPassword}
                      onChange={(e) => setNewConfirmPassword(e.target.value)}
                      placeholder="Nhập lại mật khẩu để xác thực trùng khớp"
                      className={`w-full h-10 pl-3 pr-10 rounded-lg bg-surface border text-sm text-text-primary focus:outline-none focus:ring-1 ${
                        newConfirmPassword.length > 0
                          ? newPassword === newConfirmPassword && newPassword.length >= 8
                            ? "border-emerald-500 focus:border-emerald-500 focus:ring-emerald-500"
                            : "border-state-critical focus:border-state-critical focus:ring-state-critical"
                          : "border-border focus:border-interactive focus:ring-interactive"
                      }`}
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewConfirmPassword(!showNewConfirmPassword)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-secondary hover:text-text-primary p-1 cursor-pointer"
                      title={showNewConfirmPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                    >
                      {showNewConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>

                  {/* Matching Feedback */}
                  {newConfirmPassword.length > 0 && (
                    <div className="flex items-center gap-1.5 mt-0.5 text-[11px]">
                      {newPassword === newConfirmPassword ? (
                        <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-medium">
                          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                          <span>Mật khẩu trùng khớp</span>
                        </span>
                      ) : (
                        <span className="text-state-critical flex items-center gap-1 font-medium">
                          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                          <span>Mật khẩu nhập lại không trùng khớp</span>
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-4 border-t border-border bg-canvas flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddUserModal(false);
                    resetAddUserForm();
                  }}
                  className="h-10 px-4 rounded-lg border border-border bg-surface hover:bg-canvas text-text-primary text-xs font-medium transition-colors cursor-pointer"
                >
                  Hủy bỏ
                </button>
                <button
                  type="submit"
                  disabled={
                    !newUsername.trim() ||
                    !newFullName.trim() ||
                    newPassword.length < 8 ||
                    newPassword !== newConfirmPassword ||
                    isSubmittingUser
                  }
                  className={`h-10 px-5 rounded-lg text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-none ${
                    newUsername.trim() &&
                    newFullName.trim() &&
                    newPassword.length >= 8 &&
                    newPassword === newConfirmPassword &&
                    !isSubmittingUser
                      ? "bg-interactive hover:bg-interactive-hover cursor-pointer"
                      : "bg-interactive/40 text-white/70 cursor-not-allowed"
                  }`}
                >
                  <Plus className="w-4 h-4" />
                  <span>{isSubmittingUser ? "Đang tạo..." : "Tạo tài khoản"}</span>
                </button>
              </div>
            </form>
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
      </div>
    </AppShell>
  );
}

export default function UsersPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-canvas">
          <div className="text-sm font-medium text-text-secondary">
            Đang tải dữ liệu người dùng...
          </div>
        </div>
      }
    >
      <UsersContent />
    </Suspense>
  );
}

