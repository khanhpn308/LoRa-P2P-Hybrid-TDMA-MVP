import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic tokens from clients/DESIGN.md
        canvas: {
          light: "#F5F7FA",
          dark: "#0B1220",
          DEFAULT: "var(--color-canvas)",
        },
        surface: {
          light: "#FFFFFF",
          dark: "#172335",
          DEFAULT: "var(--color-surface)",
        },
        chrome: {
          light: "#FFFFFF",
          dark: "#111C2E",
          DEFAULT: "var(--color-chrome)",
        },
        border: {
          light: "#E2E8F0",
          dark: "#334155",
          DEFAULT: "var(--color-border)",
        },
        "text-primary": {
          light: "#0F172A",
          dark: "#F8FAFC",
          DEFAULT: "var(--color-text-primary)",
        },
        "text-secondary": {
          light: "#475569",
          dark: "#CBD5E1",
          DEFAULT: "var(--color-text-secondary)",
        },
        interactive: {
          light: "#2563EB",
          dark: "#93C5FD",
          DEFAULT: "var(--color-interactive)",
        },
        "sidebar-selected": {
          light: "#DBEAFE",
          dark: "#1E3A5F",
          DEFAULT: "var(--color-sidebar-selected)",
        },
        "btn-primary": {
          DEFAULT: "#2563EB",
          hover: "#1D4ED8",
        },
        state: {
          active: {
            light: "#15803D",
            dark: "#4ADE80",
            DEFAULT: "var(--color-state-active)",
          },
          connected: {
            light: "#1D4ED8",
            dark: "#93C5FD",
            DEFAULT: "var(--color-state-connected)",
          },
          warning: {
            light: "#A16207",
            dark: "#FBBF24",
            DEFAULT: "var(--color-state-warning)",
          },
          critical: {
            light: "#B91C1C",
            dark: "#F87171",
            DEFAULT: "var(--color-state-critical)",
          },
          offline: {
            light: "#64748B",
            dark: "#94A3B8",
            DEFAULT: "var(--color-state-offline)",
          },
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "Arial", "sans-serif"],
      },
      fontSize: {
        "page-title": ["24px", { lineHeight: "32px", fontWeight: "600" }],
        "card-title": ["16px", { lineHeight: "24px", fontWeight: "600" }],
        "nav-button": ["14px", { lineHeight: "20px", fontWeight: "500" }],
        body: ["14px", { lineHeight: "20px", fontWeight: "400" }],
        "field-label": ["13px", { lineHeight: "20px", fontWeight: "500" }],
        metadata: ["12px", { lineHeight: "16px", fontWeight: "400" }],
        "kpi-value": ["32px", { lineHeight: "40px", fontWeight: "600" }],
      },
      borderRadius: {
        container: "8px",
        DEFAULT: "8px",
      },
      height: {
        header: "56px",
        control: "40px",
        "table-header": "44px",
        "table-row": "48px",
      },
      width: {
        "sidebar-expanded": "256px",
        "sidebar-collapsed": "64px",
      },
      spacing: {
        "layout-x": "24px",
        "component-gap": "16px",
      },
    },
  },
  plugins: [],
};

export default config;

