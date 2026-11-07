"use client";

import React, { useState, useEffect } from "react";
import { Header } from "./Header";
import { Sidebar, NavItemKey } from "./Sidebar";

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
  const [darkMode, setDarkMode] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Sync theme with localStorage and system preference
  useEffect(() => {
    const applyTheme = () => {
      const savedTheme = localStorage.getItem("theme") || "system";
      let isDark: boolean;
      if (savedTheme === "dark") {
        isDark = true;
      } else if (savedTheme === "light") {
        isDark = false;
      } else {
        // system preference
        isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      }

      setDarkMode(isDark);
      if (isDark) {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    };

    applyTheme();

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleSystemChange = () => {
      if (localStorage.getItem("theme") === "system" || !localStorage.getItem("theme")) {
        applyTheme();
      }
    };

    const handleCustomChange = () => {
      applyTheme();
    };

    window.addEventListener("theme-change", handleCustomChange);
    window.addEventListener("storage", handleCustomChange);
    mediaQuery.addEventListener("change", handleSystemChange);

    return () => {
      window.removeEventListener("theme-change", handleCustomChange);
      window.removeEventListener("storage", handleCustomChange);
      mediaQuery.removeEventListener("change", handleSystemChange);
    };
  }, []);

  const toggleDarkMode = () => {
    const nextDark = !darkMode;
    setDarkMode(nextDark);
    const mode = nextDark ? "dark" : "light";
    localStorage.setItem("theme", mode);
    if (nextDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    window.dispatchEvent(new Event("theme-change"));
  };

  return (
    <div className={`min-h-screen flex flex-col ${darkMode ? "dark" : ""}`}>
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

