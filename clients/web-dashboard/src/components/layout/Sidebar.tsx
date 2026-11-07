"use client";

import React, { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Activity,
  Sliders,
  Router,
  Cpu,
  Users,
  Settings,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

export type NavItemKey =
  | "overview"
  | "monitoring"
  | "gateways"
  | "nodes"
  | "users"
  | "settings";

interface SidebarProps {
  currentRoute?: NavItemKey;
  onRouteChange?: (route: NavItemKey) => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentRoute,
  onRouteChange,
  collapsed = false,
  onToggleCollapsed,
}) => {
  const router = useRouter();
  const pathname = usePathname();

  // Deduce active route from pathname if not provided
  const activeRoute =
    currentRoute ||
    (pathname === "/monitoring"
      ? "monitoring"
      : pathname === "/gateways"
      ? "gateways"
      : pathname === "/nodes"
      ? "nodes"
      : pathname === "/users"
      ? "users"
      : pathname === "/settings"
      ? "settings"
      : "overview");

  // DESIGN.md §6: Quản lý is expandable containing Gateway, Node, Người dùng
  const isManagementActive =
    activeRoute === "gateways" ||
    activeRoute === "nodes" ||
    activeRoute === "users";
  const [managementExpanded, setManagementExpanded] = useState<boolean>(true);

  const handleNavigate = (route: NavItemKey, path?: string) => {
    onRouteChange?.(route);
    if (path) {
      router.push(path);
    }
  };

  return (
    <aside
      className={`h-[calc(100vh-56px)] bg-chrome border-r border-border flex flex-col justify-between transition-all duration-200 shrink-0 select-none z-10 ${
        collapsed ? "w-[64px]" : "w-[256px]"
      }`}
    >
      {/* Navigation List - Strictly follows DESIGN.md §6 (4 top-level entries) */}
      <nav className="p-3 space-y-1">
        {/* 1. Tổng quan - Direct navigation */}
        <button
          type="button"
          onClick={() => handleNavigate("overview", "/")}
          title={collapsed ? "Tổng quan" : undefined}
          className={`w-full h-10 px-3 rounded-lg flex items-center gap-3 text-sm font-medium transition-colors ${
            activeRoute === "overview"
              ? "bg-sidebar-selected text-interactive font-semibold"
              : "text-text-secondary hover:text-text-primary hover:bg-canvas"
          } ${collapsed ? "justify-center px-0" : ""}`}
        >
          <LayoutDashboard className="w-5 h-5 shrink-0" />
          {!collapsed && <span className="truncate">Tổng quan</span>}
        </button>

        {/* 2. Theo dõi - Direct navigation to single event-monitoring table (NO submenu) */}
        <button
          type="button"
          onClick={() => handleNavigate("monitoring", "/monitoring")}
          title={collapsed ? "Theo dõi" : undefined}
          className={`w-full h-10 px-3 rounded-lg flex items-center gap-3 text-sm font-medium transition-colors ${
            activeRoute === "monitoring"
              ? "bg-sidebar-selected text-interactive font-semibold"
              : "text-text-secondary hover:text-text-primary hover:bg-canvas"
          } ${collapsed ? "justify-center px-0" : ""}`}
        >
          <Activity className="w-5 h-5 shrink-0" />
          {!collapsed && <span className="truncate">Theo dõi</span>}
        </button>

        {/* 3. Quản lý - Expandable with Gateway, Node, Người dùng */}
        <div className="flex flex-col">
          <button
            type="button"
            onClick={() => {
              if (collapsed) {
                onToggleCollapsed?.();
                setManagementExpanded(true);
              } else {
                setManagementExpanded(!managementExpanded);
              }
            }}
            title={collapsed ? "Quản lý" : undefined}
            className={`w-full h-10 px-3 rounded-lg flex items-center justify-between text-sm font-medium transition-colors ${
              isManagementActive && !collapsed
                ? "text-text-primary"
                : "text-text-secondary hover:text-text-primary hover:bg-canvas"
            } ${collapsed ? "justify-center px-0" : ""}`}
          >
            <div className="flex items-center gap-3">
              <Sliders className="w-5 h-5 shrink-0" />
              {!collapsed && <span className="truncate">Quản lý</span>}
            </div>
            {!collapsed && (
              <ChevronDown
                className={`w-4 h-4 text-text-secondary transition-transform duration-200 ${
                  managementExpanded ? "rotate-180" : ""
                }`}
              />
            )}
          </button>

          {/* Submenu List */}
          {!collapsed && managementExpanded && (
            <div className="pl-9 pr-2 py-1 space-y-1">
              <button
                type="button"
                onClick={() => handleNavigate("gateways", "/gateways")}
                className={`w-full h-8 px-2.5 rounded-md flex items-center gap-2.5 text-xs font-medium transition-colors ${
                  activeRoute === "gateways"
                    ? "bg-sidebar-selected text-interactive font-semibold"
                    : "text-text-secondary hover:text-text-primary hover:bg-canvas"
                }`}
              >
                <Router className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">Gateway</span>
              </button>

              <button
                type="button"
                onClick={() => handleNavigate("nodes", "/nodes")}
                className={`w-full h-8 px-2.5 rounded-md flex items-center gap-2.5 text-xs font-medium transition-colors ${
                  activeRoute === "nodes"
                    ? "bg-sidebar-selected text-interactive font-semibold"
                    : "text-text-secondary hover:text-text-primary hover:bg-canvas"
                }`}
              >
                <Cpu className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">Node</span>
              </button>

              <button
                type="button"
                onClick={() => handleNavigate("users", "/users")}
                className={`w-full h-8 px-2.5 rounded-md flex items-center gap-2.5 text-xs font-medium transition-colors ${
                  activeRoute === "users"
                    ? "bg-sidebar-selected text-interactive font-semibold"
                    : "text-text-secondary hover:text-text-primary hover:bg-canvas"
                }`}
              >
                <Users className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">Người dùng</span>
              </button>
            </div>
          )}
        </div>

        {/* 4. Cài đặt - Settings */}
        <button
          type="button"
          onClick={() => handleNavigate("settings", "/settings")}
          title={collapsed ? "Cài đặt" : undefined}
          className={`w-full h-10 px-3 rounded-lg flex items-center gap-3 text-sm font-medium transition-colors ${
            activeRoute === "settings"
              ? "bg-sidebar-selected text-interactive font-semibold"
              : "text-text-secondary hover:text-text-primary hover:bg-canvas"
          } ${collapsed ? "justify-center px-0" : ""}`}
        >
          <Settings className="w-5 h-5 shrink-0" />
          {!collapsed && <span className="truncate">Cài đặt</span>}
        </button>
      </nav>

      {/* Collapse Toggle Footer */}
      <div className="p-3 border-t border-border">
        <button
          type="button"
          onClick={onToggleCollapsed}
          className={`w-full h-10 px-3 rounded-lg flex items-center gap-3 text-text-secondary hover:text-text-primary hover:bg-canvas transition-colors ${
            collapsed ? "justify-center px-0" : ""
          }`}
          title={collapsed ? "Mở rộng danh mục" : "Thu gọn danh mục"}
        >
          {collapsed ? (
            <ChevronRight className="w-5 h-5" />
          ) : (
            <>
              <ChevronLeft className="w-5 h-5" />
              <span className="text-xs font-medium">Thu gọn danh mục</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
};



