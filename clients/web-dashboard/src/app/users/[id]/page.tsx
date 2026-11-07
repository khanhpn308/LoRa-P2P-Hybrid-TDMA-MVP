"use client";

import React, { useState, use, Suspense } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import {
  ArrowLeft,
  ChevronRight,
  User,
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
  Edit3,
  Mail,
} from "lucide-react";
import { UserRole } from "@/types/api";

export type { UserRole };
export type UserStatus = "active" | "disabled";

interface UserItem {
  id: string;
  username: string;
  fullName: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  lastLogin: string;
}

const DEFAULT_USERS: UserItem[] = [
  {
    id: "U-001",
    username: "admin01",
    fullName: "Nguyễn Văn A",
    email: "nguyen.vana@iiot-lora.vn",
    role: "ADMIN",
    status: "active",
    lastLogin: "04/11/2026 14:20",
  },
  {
    id: "U-002",
    username: "operator01",
    fullName: "Trần Thị B",
    email: "tran.thib@iiot-lora.vn",
    role: "OPERATOR",
    status: "active",
    lastLogin: "04/11/2026 13:45",
  },
  {
    id: "U-003",
    username: "operator03",
    fullName: "Lê Hoàng C",
    email: "le.hoangc@iiot-lora.vn",
    role: "OPERATOR",
    status: "active",
    lastLogin: "04/11/2026 11:30",
  },
  {
    id: "U-004",
    username: "operator04",
    fullName: "Phạm Minh D",
    email: "pham.minhd@iiot-lora.vn",
    role: "OPERATOR",
    status: "active",
    lastLogin: "03/11/2026 17:10",
  },
  {
    id: "U-005",
    username: "viewer_scada",
    fullName: "Vũ Hoàng E",
    email: "vu.hoange@iiot-lora.vn",
    role: "VIEWER",
    status: "active",
    lastLogin: "02/11/2026 09:15",
  },
  {
    id: "U-006",
    username: "operator02",
    fullName: "Đỗ Quốc F",
    email: "do.quocf@iiot-lora.vn",
    role: "OPERATOR",
    status: "disabled",
    lastLogin: "28/10/2026 16:00",
  },
];

const ROLE_LABELS: Record<UserRole, { label: string; desc: string; badgeClass: string }> = {
  ADMIN: {
    label: "Quản trị viên",
    desc: "Toàn quyền quản trị Gateway, Node, Phân quyền & Cài đặt hệ thống",
    badgeClass: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-200 dark:border-purple-800",
  },
  OPERATOR: {
    label: "Vận hành viên",
    desc: "Giám sát thời gian thực, xác nhận cảnh báo lỗi và yêu cầu lịch TDMA",
    badgeClass: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800",
  },
  VIEWER: {
    label: "Người xem",
    desc: "Chỉ đọc dữ liệu giám sát và lịch sử cảnh báo, không có quyền thay đổi cấu hình",
    badgeClass: "bg-slate-500/10 text-text-secondary border-border",
  },
};

interface UserDetailPageProps {
  params: Promise<{ id: string }>;
}

function UserDetailContent({ params }: { params: Promise<{ id: string }> }) {
  const unwrappedParams = use(params);
  const rawId = decodeURIComponent(unwrappedParams.id || "admin01");
  const router = useRouter();

  // Find user by id or username
  const initialUser =
    DEFAULT_USERS.find((u) => u.id === rawId || u.username === rawId) || {
      id: rawId,
      username: rawId,
      fullName: "Nguyễn Văn A",
      email: `${rawId}@iiot-lora.vn`,
      role: "ADMIN" as UserRole,
      status: "active" as UserStatus,
      lastLogin: "04/11/2026 14:20",
    };

  const [user, setUser] = useState<UserItem>(initialUser);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Modal States
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isRoleModalOpen, setIsRoleModalOpen] = useState(false);
  const [isResetPwModalOpen, setIsResetPwModalOpen] = useState(false);
  const [isToggleStatusModalOpen, setIsToggleStatusModalOpen] = useState(false);

  // Form states for modals
  const [editFullName, setEditFullName] = useState(user.fullName);
  const [editEmail, setEditEmail] = useState(user.email);
  const [selectedRole, setSelectedRole] = useState<UserRole>(user.role);

  // Reset password form states
  const [pwMode, setPwMode] = useState<"auto" | "manual">("auto");
  const [manualPassword, setManualPassword] = useState("");
  const [showManualPassword, setShowManualPassword] = useState(false);
  const [generatedPassword, setGeneratedPassword] = useState("LoRa#923MHz@2026");
  const [copied, setCopied] = useState(false);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleSaveEdit = () => {
    setUser((prev) => ({
      ...prev,
      fullName: editFullName.trim() || prev.fullName,
      email: editEmail.trim() || prev.email,
    }));
    setIsEditModalOpen(false);
    showToast(`Đã cập nhật thông tin tài khoản ${user.username}`);
  };

  const handleSaveRole = () => {
    setUser((prev) => ({
      ...prev,
      role: selectedRole,
    }));
    setIsRoleModalOpen(false);
    showToast(`Đã đổi vai trò của ${user.username} thành ${ROLE_LABELS[selectedRole].label}`);
  };

  const handleGenerateRandomPassword = () => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%";
    let pwd = "";
    for (let i = 0; i < 14; i++) {
      pwd += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    setGeneratedPassword(pwd);
  };

  const handleSaveResetPw = () => {
    setIsResetPwModalOpen(false);
    setManualPassword("");
    showToast(
      pwMode === "auto"
        ? `Đã đặt lại mật khẩu mới cho ${user.username}`
        : `Mật khẩu mới đã được cập nhật trực tiếp cho ${user.username}`
    );
  };

  const handleCopyPassword = () => {
    navigator.clipboard.writeText(generatedPassword);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleToggleStatus = () => {
    const nextStatus: UserStatus = user.status === "active" ? "disabled" : "active";
    setUser((prev) => ({
      ...prev,
      status: nextStatus,
    }));
    setIsToggleStatusModalOpen(false);
    showToast(
      nextStatus === "disabled"
        ? `Đã vô hiệu hóa tài khoản ${user.username}`
        : `Đã kích hoạt lại tài khoản ${user.username}`
    );
  };

  const currentRoleMeta = ROLE_LABELS[user.role];

  return (
    <AppShell activeRoute="users">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 bg-slate-900 text-white dark:bg-white dark:text-slate-900 px-4 py-3 rounded-lg shadow-lg border border-border text-sm font-medium animate-in fade-in slide-in-from-bottom-2 duration-200">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 dark:text-emerald-600 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Main Container - 840px max width matching Stitch screen 450a9b4a39f7465e85022355bdc34e41 */}
      <div className="max-w-[840px] w-full flex flex-col gap-6">
        {/* Breadcrumb Navigation */}
        <nav aria-label="Đường dẫn trang" className="flex items-center gap-1.5 text-xs text-text-secondary">
          <button
            type="button"
            onClick={() => router.push("/users")}
            className="flex items-center gap-1 hover:text-interactive transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Quản lý</span>
          </button>
          <ChevronRight className="w-3.5 h-3.5 text-text-secondary/60" />
          <Link href="/users" className="hover:text-interactive transition-colors">
            Người dùng
          </Link>
          <ChevronRight className="w-3.5 h-3.5 text-text-secondary/60" />
          <span className="font-mono font-medium text-text-primary">{user.username}</span>
        </nav>

        {/* Page Title & Profile Header Lockup */}
        <div className="flex flex-col gap-4">
          <h1 className="text-2xl font-semibold text-text-primary tracking-tight">
            Chi tiết người dùng
          </h1>

          <div className="flex flex-wrap items-center justify-between gap-4">
            {/* User Identity */}
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-interactive flex items-center justify-center">
                <User className="w-6 h-6" />
              </div>
              <div className="flex flex-col">
                <div className="text-lg font-semibold text-text-primary leading-tight">
                  {user.fullName}
                </div>
                <div className="text-xs font-mono font-medium text-text-secondary mt-0.5">
                  @{user.username}
                </div>
              </div>
            </div>

            {/* Action Buttons Toolbar */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Button 1: Chỉnh sửa thông tin */}
              <button
                type="button"
                onClick={() => {
                  setEditFullName(user.fullName);
                  setEditEmail(user.email);
                  setIsEditModalOpen(true);
                }}
                className="h-9 px-3.5 bg-interactive hover:bg-interactive-hover text-white text-xs font-medium rounded-lg flex items-center gap-1.5 transition-colors shadow-sm"
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span>Chỉnh sửa thông tin</span>
              </button>

              {/* Button 2: Đổi vai trò */}
              <button
                type="button"
                onClick={() => {
                  setSelectedRole(user.role);
                  setIsRoleModalOpen(true);
                }}
                className="h-9 px-3 bg-canvas hover:bg-canvas/80 text-text-primary text-xs font-medium rounded-lg border border-border flex items-center gap-1.5 transition-colors shadow-none"
              >
                <ShieldCheck className="w-3.5 h-3.5 text-interactive" />
                <span>Đổi vai trò</span>
              </button>

              {/* Button 3: Đặt lại mật khẩu */}
              <button
                type="button"
                onClick={() => {
                  handleGenerateRandomPassword();
                  setIsResetPwModalOpen(true);
                }}
                className="h-9 px-3 bg-canvas hover:bg-canvas/80 text-text-primary text-xs font-medium rounded-lg border border-border flex items-center gap-1.5 transition-colors shadow-none"
              >
                <KeyRound className="w-3.5 h-3.5 text-amber-500" />
                <span>Đặt lại mật khẩu</span>
              </button>

              {/* Button 4: Vô hiệu hóa / Kích hoạt tài khoản */}
              <button
                type="button"
                onClick={() => setIsToggleStatusModalOpen(true)}
                className={`h-9 px-3 text-xs font-medium rounded-lg border flex items-center gap-1.5 transition-colors ${
                  user.status === "active"
                    ? "bg-canvas border-red-200 dark:border-red-900/60 text-state-critical hover:bg-red-50 dark:hover:bg-red-950/40"
                    : "bg-canvas border-emerald-200 dark:border-emerald-900/60 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/40"
                }`}
              >
                {user.status === "active" ? (
                  <>
                    <UserX className="w-3.5 h-3.5" />
                    <span>Vô hiệu hóa tài khoản</span>
                  </>
                ) : (
                  <>
                    <UserCheck className="w-3.5 h-3.5" />
                    <span>Kích hoạt lại</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Read-Only Account Information Card */}
        <section className="bg-chrome rounded-lg p-6 border border-border shadow-none flex flex-col gap-6">
          <div className="pb-3 border-b border-border flex items-center justify-between">
            <h2 className="text-base font-semibold text-text-primary">
              Thông tin tài khoản
            </h2>
            <span className="text-xs text-text-secondary">
              Mã người dùng: <strong className="font-mono text-text-primary">{user.id}</strong>
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-6">
            {/* Field 1: Tài khoản */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-text-secondary">Tài khoản (Username)</span>
              <span className="text-sm font-mono font-medium text-text-primary">{user.username}</span>
            </div>

            {/* Field 2: Tên hiển thị */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-text-secondary">Họ và tên</span>
              <span className="text-sm font-medium text-text-primary">{user.fullName}</span>
            </div>

            {/* Field 3: Email */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-text-secondary">Email liên hệ</span>
              <span className="text-sm font-mono text-text-primary flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-text-secondary" />
                <span>{user.email}</span>
              </span>
            </div>

            {/* Field 4: Vai trò */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-text-secondary">Vai trò phân quyền</span>
              <div>
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium border ${currentRoleMeta.badgeClass}`}>
                  {currentRoleMeta.label}
                </span>
                <p className="text-[11px] text-text-secondary mt-1">{currentRoleMeta.desc}</p>
              </div>
            </div>

            {/* Field 5: Trạng thái */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-text-secondary">Trạng thái hoạt động</span>
              <div className="inline-flex items-center gap-2 mt-0.5">
                {user.status === "active" ? (
                  <>
                    <span className="w-2.5 h-2.5 rounded-full bg-state-connected" />
                    <span className="text-sm font-medium text-state-connected">Đang hoạt động</span>
                  </>
                ) : (
                  <>
                    <span className="w-2.5 h-2.5 rounded-full bg-state-critical" />
                    <span className="text-sm font-medium text-state-critical">Đã vô hiệu hóa</span>
                  </>
                )}
              </div>
            </div>

            {/* Field 6: Đăng nhập gần nhất */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-text-secondary">Đăng nhập gần nhất</span>
              <span className="text-sm font-mono text-text-primary tabular-nums">{user.lastLogin}</span>
            </div>
          </div>
        </section>
      </div>

      {/* MODAL 1: CHỈNH SỬA THÔNG TIN */}
      {isEditModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 animate-in fade-in duration-150">
          <div className="bg-chrome w-full max-w-[480px] rounded-lg border border-border shadow-xl p-6 flex flex-col gap-4">
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-interactive" />
                <h3 className="text-base font-semibold text-text-primary">Chỉnh sửa thông tin</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsEditModalOpen(false)}
                className="w-7 h-7 rounded flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-canvas"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-xs font-medium text-text-secondary mb-1 block">Tài khoản</label>
                <input
                  type="text"
                  disabled
                  value={user.username}
                  className="w-full h-10 px-3 rounded-lg border border-border bg-canvas text-text-secondary font-mono text-xs cursor-not-allowed"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-text-secondary mb-1 block">Họ và tên *</label>
                <input
                  type="text"
                  value={editFullName}
                  onChange={(e) => setEditFullName(e.target.value)}
                  className="w-full h-10 px-3 rounded-lg border border-border bg-chrome text-text-primary text-sm focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-text-secondary mb-1 block">Email liên hệ *</label>
                <input
                  type="email"
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  className="w-full h-10 px-3 rounded-lg border border-border bg-chrome text-text-primary text-sm focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive font-mono"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
              <button
                type="button"
                onClick={() => setIsEditModalOpen(false)}
                className="h-9 px-4 rounded-lg border border-border text-xs font-medium text-text-secondary hover:bg-canvas"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                className="h-9 px-4 rounded-lg bg-interactive hover:bg-interactive-hover text-white text-xs font-medium"
              >
                Lưu thay đổi
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: ĐỔI VAI TRÒ */}
      {isRoleModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 animate-in fade-in duration-150">
          <div className="bg-chrome w-full max-w-[520px] rounded-lg border border-border shadow-xl p-6 flex flex-col gap-4">
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-interactive" />
                <h3 className="text-base font-semibold text-text-primary">Đổi vai trò phân quyền</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsRoleModalOpen(false)}
                className="w-7 h-7 rounded flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-canvas"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-text-secondary">
              Chọn vai trò mới cho tài khoản <strong className="font-mono text-text-primary">{user.username}</strong>:
            </p>

            <div className="space-y-2.5">
              {(["ADMIN", "OPERATOR", "VIEWER"] as UserRole[]).map((r) => {
                const meta = ROLE_LABELS[r];
                const isSelected = selectedRole === r;
                return (
                  <label
                    key={r}
                    onClick={() => setSelectedRole(r)}
                    className={`p-3 rounded-lg border flex items-start gap-3 cursor-pointer transition-colors ${
                      isSelected
                        ? "bg-sidebar-selected border-interactive/60"
                        : "border-border hover:bg-canvas"
                    }`}
                  >
                    <input
                      type="radio"
                      name="role-select"
                      checked={isSelected}
                      onChange={() => setSelectedRole(r)}
                      className="mt-0.5 text-interactive focus:ring-interactive"
                    />
                    <div className="flex flex-col">
                      <span className="text-sm font-semibold text-text-primary flex items-center gap-2">
                        <span>{meta.label}</span>
                        {isSelected && <span className="text-[11px] font-medium text-interactive">(Đang chọn)</span>}
                      </span>
                      <span className="text-xs text-text-secondary mt-0.5">{meta.desc}</span>
                    </div>
                  </label>
                );
              })}
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
              <button
                type="button"
                onClick={() => setIsRoleModalOpen(false)}
                className="h-9 px-4 rounded-lg border border-border text-xs font-medium text-text-secondary hover:bg-canvas"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={handleSaveRole}
                className="h-9 px-4 rounded-lg bg-interactive hover:bg-interactive-hover text-white text-xs font-medium"
              >
                Cập nhật vai trò
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: ĐẶT LẠI MẬT KHẨU */}
      {isResetPwModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 animate-in fade-in duration-150">
          <div className="bg-chrome w-full max-w-[500px] rounded-lg border border-border shadow-xl p-6 flex flex-col gap-4">
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-amber-500" />
                <h3 className="text-base font-semibold text-text-primary">Đặt lại mật khẩu</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsResetPwModalOpen(false)}
                className="w-7 h-7 rounded flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-canvas"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex items-center gap-2 p-1 bg-canvas border border-border rounded-lg">
              <button
                type="button"
                onClick={() => setPwMode("auto")}
                className={`flex-1 h-8 rounded text-xs font-medium transition-colors ${
                  pwMode === "auto"
                    ? "bg-interactive text-white shadow-sm font-semibold"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                Sinh tự động ngẫu nhiên
              </button>
              <button
                type="button"
                onClick={() => setPwMode("manual")}
                className={`flex-1 h-8 rounded text-xs font-medium transition-colors ${
                  pwMode === "manual"
                    ? "bg-interactive text-white shadow-sm font-semibold"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                Nhập mật khẩu thủ công
              </button>
            </div>

            {pwMode === "auto" ? (
              <div className="space-y-3 pt-2">
                <p className="text-xs text-text-secondary">
                  Mật khẩu ngẫu nhiên có độ dài 14 ký tự với độ bảo mật cao:
                </p>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={generatedPassword}
                    className="flex-1 h-10 px-3 rounded-lg border border-border bg-canvas font-mono text-sm font-semibold text-text-primary select-all"
                  />
                  <button
                    type="button"
                    onClick={handleGenerateRandomPassword}
                    title="Sinh mã khác"
                    className="h-10 w-10 flex items-center justify-center rounded-lg border border-border bg-canvas hover:bg-canvas/80 text-text-secondary hover:text-text-primary"
                  >
                    <RotateCw className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={handleCopyPassword}
                    title="Sao chép mật khẩu"
                    className="h-10 px-3 flex items-center gap-1.5 rounded-lg border border-border bg-canvas hover:bg-canvas/80 text-text-secondary hover:text-text-primary text-xs font-medium"
                  >
                    {copied ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                    <span>{copied ? "Đã chép" : "Chép"}</span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-3 pt-2">
                <label className="text-xs font-medium text-text-secondary block">
                  Nhập mật khẩu mới cho tài khoản:
                </label>
                <div className="relative flex items-center">
                  <input
                    type={showManualPassword ? "text" : "password"}
                    value={manualPassword}
                    onChange={(e) => setManualPassword(e.target.value)}
                    placeholder="Ít nhất 8 ký tự..."
                    className="w-full h-10 px-3 pr-10 rounded-lg border border-border bg-chrome text-text-primary text-sm focus:outline-none focus:border-interactive focus:ring-1 focus:ring-interactive font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowManualPassword(!showManualPassword)}
                    className="absolute right-2.5 text-text-secondary hover:text-text-primary"
                  >
                    {showManualPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
              <button
                type="button"
                onClick={() => setIsResetPwModalOpen(false)}
                className="h-9 px-4 rounded-lg border border-border text-xs font-medium text-text-secondary hover:bg-canvas"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={handleSaveResetPw}
                disabled={pwMode === "manual" && manualPassword.length < 6}
                className="h-9 px-4 rounded-lg bg-interactive hover:bg-interactive-hover disabled:opacity-50 text-white text-xs font-medium"
              >
                Xác nhận đặt lại
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 4: VÔ HIỆU HÓA / KÍCH HOẠT */}
      {isToggleStatusModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 animate-in fade-in duration-150">
          <div className="bg-chrome w-full max-w-[460px] rounded-lg border border-border shadow-xl p-6 flex flex-col gap-4">
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-500" />
                <h3 className="text-base font-semibold text-text-primary">
                  {user.status === "active" ? "Vô hiệu hóa tài khoản" : "Kích hoạt lại tài khoản"}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsToggleStatusModalOpen(false)}
                className="w-7 h-7 rounded flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-canvas"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-text-secondary leading-relaxed">
              {user.status === "active" ? (
                <>
                  Bạn có chắc chắn muốn vô hiệu hóa tài khoản{" "}
                  <strong className="font-mono text-text-primary">{user.username}</strong>? Người dùng
                  sẽ không thể đăng nhập vào trạm giám sát SCADA cho đến khi được kích hoạt lại.
                </>
              ) : (
                <>
                  Bạn có muốn kích hoạt lại tài khoản{" "}
                  <strong className="font-mono text-text-primary">{user.username}</strong>? Người dùng
                  sẽ có thể đăng nhập bình thường theo vai trò đã phân quyền.
                </>
              )}
            </p>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
              <button
                type="button"
                onClick={() => setIsToggleStatusModalOpen(false)}
                className="h-9 px-4 rounded-lg border border-border text-xs font-medium text-text-secondary hover:bg-canvas"
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                onClick={handleToggleStatus}
                className={`h-9 px-4 rounded-lg text-white text-xs font-medium ${
                  user.status === "active"
                    ? "bg-red-600 hover:bg-red-700"
                    : "bg-emerald-600 hover:bg-emerald-700"
                }`}
              >
                {user.status === "active" ? "Xác nhận vô hiệu hóa" : "Kích hoạt tài khoản"}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

export default function UserDetailPage({ params }: UserDetailPageProps) {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-canvas">
          <div className="flex items-center gap-3 text-text-secondary text-sm">
            <div className="w-5 h-5 border-2 border-interactive border-t-transparent rounded-full animate-spin" />
            <span>Đang tải thông tin người dùng...</span>
          </div>
        </div>
      }
    >
      <UserDetailContent params={params} />
    </Suspense>
  );
}
