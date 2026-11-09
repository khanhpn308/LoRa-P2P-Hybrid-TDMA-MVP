"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useMemo,
} from "react";

export type ThemeMode = "light" | "dark" | "system";

export interface ThemeContextType {
  theme: ThemeMode;
  resolvedTheme: "light" | "dark";
  darkMode: boolean;
  setTheme: (theme: ThemeMode) => void;
  toggleDarkMode: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const THEME_STORAGE_KEY = "theme";

function getSystemPreference(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function getStoredTheme(): ThemeMode {
  if (typeof window === "undefined") return "system";
  try {
    const item = localStorage.getItem(THEME_STORAGE_KEY);
    if (item === "light" || item === "dark" || item === "system") {
      return item;
    }
  } catch {
    // ignore
  }
  return "system";
}

function resolveTheme(mode: ThemeMode): "light" | "dark" {
  if (mode === "dark") return "dark";
  if (mode === "light") return "light";
  return getSystemPreference();
}

function applyHtmlThemeClass(resolved: "light" | "dark") {
  if (typeof document === "undefined") return;
  if (resolved === "dark") {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Initialize state from DOM / localStorage if available on client
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    return getStoredTheme();
  });

  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">(() => {
    if (typeof document !== "undefined") {
      if (document.documentElement.classList.contains("dark")) {
        return "dark";
      }
    }
    return resolveTheme(getStoredTheme());
  });

  const updateTheme = useCallback((newTheme: ThemeMode) => {
    setThemeState(newTheme);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, newTheme);
    } catch {
      // ignore
    }
    const resolved = resolveTheme(newTheme);
    setResolvedTheme(resolved);
    applyHtmlThemeClass(resolved);
    window.dispatchEvent(new Event("theme-change"));
  }, []);

  const toggleDarkMode = useCallback(() => {
    // If currently dark, switch to light; otherwise dark
    const nextMode: ThemeMode = resolvedTheme === "dark" ? "light" : "dark";
    updateTheme(nextMode);
  }, [resolvedTheme, updateTheme]);

  // Sync with storage, custom event, and system preference
  useEffect(() => {
    const handleSync = () => {
      const currentStored = getStoredTheme();
      setThemeState(currentStored);
      const resolved = resolveTheme(currentStored);
      setResolvedTheme(resolved);
      applyHtmlThemeClass(resolved);
    };

    // Ensure DOM class aligns on mount
    handleSync();

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleMediaChange = () => {
      const currentStored = getStoredTheme();
      if (currentStored === "system") {
        handleSync();
      }
    };

    window.addEventListener("theme-change", handleSync);
    window.addEventListener("storage", handleSync);
    mediaQuery.addEventListener("change", handleMediaChange);

    return () => {
      window.removeEventListener("theme-change", handleSync);
      window.removeEventListener("storage", handleSync);
      mediaQuery.removeEventListener("change", handleMediaChange);
    };
  }, []);

  const value = useMemo(
    () => ({
      theme,
      resolvedTheme,
      darkMode: resolvedTheme === "dark",
      setTheme: updateTheme,
      toggleDarkMode,
    }),
    [theme, resolvedTheme, updateTheme, toggleDarkMode]
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextType {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
