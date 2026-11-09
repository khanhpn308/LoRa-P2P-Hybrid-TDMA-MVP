"use client";

import React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Radio, Moon, Sun, Bell, LogOut, User as UserIcon } from "lucide-react";
import { useRealtime } from "@/lib/realtime/RealtimeContext";
import { useAuth } from "@/lib/auth/AuthContext";
import { useTheme } from "@/components/providers/ThemeProvider";

interface HeaderProps {
  darkMode?: boolean;
  onToggleDarkMode?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  darkMode: propDarkMode,
  onToggleDarkMode: propOnToggleDarkMode,
}) => {
  const router = useRouter();
  const { connectionState, reconnectCount } = useRealtime();
  const { user, role, logout, isAuthenticated } = useAuth();
  const { darkMode: contextDarkMode, toggleDarkMode } = useTheme();

  const darkMode = propDarkMode !== undefined ? propDarkMode : contextDarkMode;
  const handleToggleTheme = propOnToggleDarkMode || toggleDarkMode;

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  const renderWsBadge = () => {
    switch (connectionState) {
      case "CONNECTED":
        return (
          <div
            className="hidden sm:inline-flex items-center gap-2 text-xs text-text-secondary px-2.5 py-1 bg-canvas border border-border rounded"
            title="Đã kết nối an toàn với WebSocket Realtime Hub"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
            <span className="font-medium text-text-primary">Realtime: Đã kết nối</span>
          </div>
        );
      case "RECONNECTING":
        return (
          <div
            className="hidden sm:inline-flex items-center gap-2 text-xs text-text-secondary px-2.5 py-1 bg-canvas border border-border rounded"
            title={`Đang tự động kết nối lại WebSocket Hub (Lần thử: ${reconnectCount})`}
          >
            <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0 animate-pulse" />
            <span className="font-medium text-amber-600 dark:text-amber-400">
              Đang kết nối lại ({reconnectCount})...
            </span>
          </div>
        );
      case "CONNECTING":
        return (
          <div
            className="hidden sm:inline-flex items-center gap-2 text-xs text-text-secondary px-2.5 py-1 bg-canvas border border-border rounded"
            title="Đang mở bắt tay Single-Use Ticket qua WebSocket Hub"
          >
            <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0 animate-pulse" />
            <span className="font-medium text-interactive">Đang kết nối...</span>
          </div>
        );
      case "DISCONNECTED":
      default:
        return (
          <div
            className="hidden sm:inline-flex items-center gap-2 text-xs text-text-secondary px-2.5 py-1 bg-canvas border border-border rounded"
            title="Chưa kết nối tới WebSocket Hub (Yêu cầu đăng nhập hợp lệ)"
          >
            <span className="w-2 h-2 rounded-full bg-rose-500 shrink-0" />
            <span className="font-medium text-text-secondary">Realtime: Ngắt kết nối</span>
          </div>
        );
    }
  };

  const initials = user?.username ? user.username.slice(0, 2).toUpperCase() : "AD";
  const displayRole = role || "ADMIN";

  return (
    <header className="h-[56px] w-full bg-chrome border-b border-border flex items-center justify-between px-6 select-none shrink-0 z-20">
      {/* Brand Lockup: IIoT LoRa Network + Trạm giám sát (DESIGN.md §6) */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-md bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800 text-interactive flex items-center justify-center">
            <Radio className="w-4 h-4" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-[15px] text-text-primary tracking-tight">
              IIoT LoRa Network
            </span>
            <span className="text-[11px] font-medium text-interactive bg-blue-50 dark:bg-blue-950/60 border border-blue-200 dark:border-blue-800/80 px-1.5 py-0.5 rounded">
              Trạm giám sát
            </span>
          </div>
        </div>
      </div>

      {/* Right Controls: Realtime WS Status + Theme Toggle + User Profile + Logout */}
      <div className="flex items-center gap-3 sm:gap-4">
        {/* Realtime WebSocket Status Badge */}
        {renderWsBadge()}

        {/* Theme Toggle */}
        <button
          type="button"
          onClick={handleToggleTheme}
          className="w-9 h-9 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-canvas transition-colors border border-transparent hover:border-border"
          title="Chuyển đổi giao diện Sáng / Tối"
          aria-label="Toggle theme"
          suppressHydrationWarning
        >
          {darkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Notification Bell */}
        <Link
          href="/monitoring"
          className="w-9 h-9 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-canvas transition-colors border border-transparent hover:border-border relative"
          title="Xem danh sách cảnh báo sự cố"
          aria-label="Notifications"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-state-critical" />
        </Link>

        <div className="h-5 w-[1px] bg-border" />

        {/* User Profile & Role */}
        {isAuthenticated ? (
          <div className="flex items-center gap-2">
            <Link
              href="/users"
              className="flex items-center gap-2 pl-1 cursor-pointer hover:opacity-85 transition-opacity"
              title={`Tài khoản: ${user?.username || "admin"} (${displayRole})`}
            >
              <div className="w-7 h-7 rounded-full bg-border text-text-secondary flex items-center justify-center text-xs font-semibold">
                {initials}
              </div>
              <div className="hidden md:flex flex-col text-left">
                <span className="text-xs font-medium text-text-primary leading-tight">
                  {user?.username || "Quản trị viên"}
                </span>
                <span className="text-[10px] text-text-secondary tracking-tight">
                  {displayRole}
                </span>
              </div>
            </Link>

            {/* Logout button */}
            <button
              type="button"
              onClick={handleLogout}
              className="w-8 h-8 rounded-lg flex items-center justify-center text-text-secondary hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors border border-transparent hover:border-rose-200 dark:hover:border-rose-900"
              title="Đăng xuất khỏi hệ thống"
              aria-label="Logout"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <Link
            href="/login"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-interactive text-white rounded hover:bg-interactive-hover transition-colors"
          >
            <UserIcon className="w-3.5 h-3.5" />
            <span>Đăng nhập</span>
          </Link>
        )}
      </div>
    </header>
  );
};
