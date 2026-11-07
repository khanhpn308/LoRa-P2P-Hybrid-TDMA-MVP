"use client";

import React from "react";
import Link from "next/link";
import { Radio, Moon, Sun, Bell } from "lucide-react";

interface HeaderProps {
  darkMode?: boolean;
  onToggleDarkMode?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  darkMode = false,
  onToggleDarkMode,
}) => {
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

      {/* Right Controls: System Health Pill + Theme Toggle + User Profile */}
      <div className="flex items-center gap-4">
        {/* System Health Status Pill */}
        <div
          className="hidden sm:inline-flex items-center gap-2 text-xs text-text-secondary px-2.5 py-1 bg-canvas border border-border rounded"
          title="Hệ thống đang đồng bộ liên tục với mạng LoRa TDMA"
        >
          <span className="w-2 h-2 rounded-full bg-state-active shrink-0 animate-pulse" />
          <span className="font-medium text-text-primary">Hệ thống bình thường</span>
        </div>

        {/* Theme Toggle */}
        <button
          type="button"
          onClick={onToggleDarkMode}
          className="w-9 h-9 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-canvas transition-colors border border-transparent hover:border-border"
          title="Chuyển đổi giao diện Sáng / Tối"
          aria-label="Toggle theme"
        >
          {darkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Notification Bell */}
        <button
          type="button"
          className="w-9 h-9 rounded-lg flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-canvas transition-colors border border-transparent hover:border-border relative"
          title="Thông báo sự cố"
          aria-label="Notifications"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-state-critical" />
        </button>

        <div className="h-5 w-[1px] bg-border" />

        {/* User Profile */}
        <Link
          href="/users/admin01"
          className="flex items-center gap-2 pl-1 cursor-pointer hover:opacity-85 transition-opacity"
          title="Xem chi tiết tài khoản Quản trị viên"
        >
          <div className="w-7 h-7 rounded-full bg-border text-text-secondary flex items-center justify-center text-xs font-semibold">
            AD
          </div>
          <span className="text-xs font-medium text-text-primary hidden md:inline">
            Quản trị viên
          </span>
        </Link>
      </div>
    </header>
  );
};


