"use client";

import React, { useState } from "react";
import { Header } from "./Header";
import { Sidebar, NavItemKey } from "./Sidebar";
import { useTheme } from "@/components/providers/ThemeProvider";

interface AppShellProps {
  children: React.ReactNode;
  activeRoute?: NavItemKey;
  onRouteChange?: (route: NavItemKey) => void;
}

export const AppShell: React.FC<AppShellProps> = ({
  children,
  activeRoute = "overview",
  onRouteChange,
}) => {
  const { darkMode, toggleDarkMode } = useTheme();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div
      className={`min-h-screen flex flex-col ${darkMode ? "dark" : ""}`}
      suppressHydrationWarning
    >
      {/* 56px Header across full width */}
      <Header
        darkMode={darkMode}
        onToggleDarkMode={toggleDarkMode}
      />

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar at left edge */}
        <Sidebar
          currentRoute={activeRoute}
          onRouteChange={onRouteChange}
          collapsed={sidebarCollapsed}
          onToggleCollapsed={() => setSidebarCollapsed(!sidebarCollapsed)}
        />

        {/* Main Content Area: formula Usable = 1440 - 256 - 48 = 1136px (DESIGN.md §5) */}
        <main className="flex-1 overflow-y-auto bg-canvas p-6">
          <div className="max-w-[1136px] w-full mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

