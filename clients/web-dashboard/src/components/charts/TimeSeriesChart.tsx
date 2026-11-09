"use client";

import React, { useState, useMemo } from "react";
import { Activity, AlertTriangle, Calendar, TrendingUp } from "lucide-react";

export interface TimeSeriesPoint {
  id: string | number;
  timestamp: string | Date | number;
  value: number;
  code?: number;
  name?: string;
  severity?: "P0_EMERGENCY" | "P1_HIGH" | "P2_MEDIUM" | "P3_NORMAL" | string;
  unit?: string;
}

interface TimeSeriesChartProps {
  title?: string;
  description?: string;
  data: TimeSeriesPoint[];
  unit?: string;
  height?: number;
  emptyMessage?: string;
}

export function TimeSeriesChart({
  title = "Biểu đồ biến thiên sự kiện cảm biến",
  description = "Theo dõi chuỗi giá trị cảm biến theo thời gian từ các bản tin UP_EVENT",
  data = [],
  unit = "",
  height = 240,
  emptyMessage = "Chưa có dữ liệu sự kiện nào được ghi nhận cho thiết bị này.",
}: TimeSeriesChartProps) {
  const [hoveredPoint, setHoveredPoint] = useState<TimeSeriesPoint | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null);

  // Sort chronological
  const sortedData = useMemo(() => {
    return [...data].sort((a, b) => {
      const ta = new Date(a.timestamp).getTime();
      const tb = new Date(b.timestamp).getTime();
      return ta - tb;
    });
  }, [data]);

  // Compute scale bounds
  const stats = useMemo(() => {
    if (sortedData.length === 0) {
      return { min: 0, max: 100, avg: 0, latest: 0, total: 0 };
    }
    const values = sortedData.map((d) => d.value);
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const sum = values.reduce((acc, cur) => acc + cur, 0);
    const avg = Math.round(sum / values.length);
    const latest = sortedData[sortedData.length - 1].value;

    // Expand margin so line doesn't stick to the extreme border
    const range = maxVal - minVal;
    const padding = range === 0 ? Math.max(10, Math.abs(maxVal * 0.2)) : range * 0.15;
    return {
      min: Math.floor(minVal - padding),
      max: Math.ceil(maxVal + padding),
      rawMin: minVal,
      rawMax: maxVal,
      avg,
      latest,
      total: sortedData.length,
    };
  }, [sortedData]);

  // Chart Dimensions
  const svgWidth = 800;
  const svgHeight = height;
  const padLeft = 55;
  const padRight = 30;
  const padTop = 25;
  const padBottom = 35;
  const plotWidth = svgWidth - padLeft - padRight;
  const plotHeight = svgHeight - padTop - padBottom;

  // Coordinate mappers
  const getX = (idx: number, total: number) => {
    if (total <= 1) return padLeft + plotWidth / 2;
    return padLeft + (idx / (total - 1)) * plotWidth;
  };

  const getY = (val: number) => {
    const range = stats.max - stats.min;
    if (range === 0) return padTop + plotHeight / 2;
    const normalized = (val - stats.min) / range;
    return padTop + plotHeight - normalized * plotHeight;
  };

  // Generate SVG path points
  const points = useMemo(() => {
    return sortedData.map((d, i) => ({
      ...d,
      x: getX(i, sortedData.length),
      y: getY(d.value),
    }));
  }, [sortedData, stats]);

  // Generate SVG path string (d="M ... L ...")
  const linePath = useMemo(() => {
    if (points.length === 0) return "";
    return points.reduce((acc, p, i) => {
      return i === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`;
    }, "");
  }, [points]);

  // Generate Area fill path
  const areaPath = useMemo(() => {
    if (points.length === 0) return "";
    const firstX = points[0].x;
    const lastX = points[points.length - 1].x;
    const bottomY = padTop + plotHeight;
    return `${linePath} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;
  }, [points, linePath, plotHeight, padTop]);

  // Horizontal Grid Lines
  const gridTicks = 4;
  const yTicks = useMemo(() => {
    const ticks = [];
    const step = (stats.max - stats.min) / gridTicks;
    for (let i = 0; i <= gridTicks; i++) {
      const val = Math.round(stats.min + step * i);
      const y = getY(val);
      ticks.push({ val, y });
    }
    return ticks;
  }, [stats]);

  const getSeverityColor = (severity?: string) => {
    switch (severity) {
      case "P0_EMERGENCY":
        return "#f43f5e"; // rose-500
      case "P1_HIGH":
        return "#f59e0b"; // amber-500
      case "P2_MEDIUM":
        return "#3b82f6"; // blue-500
      default:
        return "#10b981"; // emerald-500
    }
  };

  return (
    <section className="bg-chrome rounded-lg border border-border overflow-hidden">
      {/* Header & KPI Summary */}
      <div className="p-5 pb-3 border-b border-border flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded bg-interactive/10 text-interactive flex items-center justify-center shrink-0">
            <TrendingUp className="w-4 h-4" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-text-primary">{title}</h2>
            <p className="text-xs text-text-secondary mt-0.5">{description}</p>
          </div>
        </div>

        {/* Realtime KPI Badges */}
        {sortedData.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <div className="px-2.5 py-1 rounded bg-canvas border border-border">
              <span className="text-text-secondary mr-1.5">Mới nhất:</span>
              <strong className="font-mono text-text-primary">
                {stats.latest} {unit}
              </strong>
            </div>
            <div className="px-2.5 py-1 rounded bg-canvas border border-border">
              <span className="text-text-secondary mr-1.5">Đỉnh:</span>
              <strong className="font-mono text-state-critical">
                {stats.rawMax} {unit}
              </strong>
            </div>
            <div className="px-2.5 py-1 rounded bg-canvas border border-border">
              <span className="text-text-secondary mr-1.5">Đáy:</span>
              <strong className="font-mono text-text-primary">
                {stats.rawMin} {unit}
              </strong>
            </div>
            <div className="px-2.5 py-1 rounded bg-interactive/10 border border-interactive/20 text-interactive font-medium">
              <span>{stats.total} sự kiện</span>
            </div>
          </div>
        )}
      </div>

      {/* Main Chart Canvas Area */}
      <div className="relative p-4 w-full select-none">
        {sortedData.length === 0 ? (
          <div className="h-44 flex flex-col items-center justify-center text-center px-4">
            <Activity className="w-8 h-8 text-text-secondary/40 mb-2" />
            <p className="text-sm font-medium text-text-secondary">{emptyMessage}</p>
            <span className="text-xs text-text-secondary/60 mt-1">
              Hệ thống sẽ cập nhật tự động khi có gói tin UP_EVENT gửi lên từ nút cảm biến.
            </span>
          </div>
        ) : (
          <div className="relative w-full overflow-x-auto">
            <svg
              viewBox={`0 0 ${svgWidth} ${svgHeight}`}
              className="w-full h-auto min-w-[580px] overflow-visible"
            >
              <defs>
                {/* Gradient area fill */}
                <linearGradient id="eventGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2563eb" stopOpacity="0.28" />
                  <stop offset="100%" stopColor="#2563eb" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Grid Lines & Y-Axis Labels */}
              {yTicks.map((tick, idx) => (
                <g key={idx}>
                  <line
                    x1={padLeft}
                    y1={tick.y}
                    x2={svgWidth - padRight}
                    y2={tick.y}
                    stroke="currentColor"
                    className="text-border"
                    strokeDasharray="4 4"
                    strokeWidth="1"
                  />
                  <text
                    x={padLeft - 10}
                    y={tick.y + 4}
                    textAnchor="end"
                    className="text-[11px] font-mono fill-current text-text-secondary/80"
                  >
                    {tick.val}
                  </text>
                </g>
              ))}

              {/* Bottom Baseline */}
              <line
                x1={padLeft}
                y1={padTop + plotHeight}
                x2={svgWidth - padRight}
                y2={padTop + plotHeight}
                stroke="currentColor"
                className="text-border"
                strokeWidth="1.5"
              />

              {/* Area Fill */}
              {areaPath && (
                <path d={areaPath} fill="url(#eventGradient)" />
              )}

              {/* Main Trend Line */}
              {linePath && (
                <path
                  d={linePath}
                  fill="none"
                  stroke="#3b82f6"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}

              {/* Data Points */}
              {points.map((pt) => {
                const color = getSeverityColor(pt.severity);
                const isHovered = hoveredPoint?.id === pt.id;
                return (
                  <g
                    key={pt.id}
                    className="cursor-pointer transition-transform"
                    onMouseEnter={() => {
                      setHoveredPoint(pt);
                      setTooltipPos({ x: pt.x, y: pt.y });
                    }}
                    onMouseLeave={() => {
                      setHoveredPoint(null);
                      setTooltipPos(null);
                    }}
                  >
                    {/* Hover Pulse Ring */}
                    {isHovered && (
                      <circle
                        cx={pt.x}
                        cy={pt.y}
                        r="10"
                        fill={color}
                        opacity="0.25"
                      />
                    )}
                    {/* Outer Circle */}
                    <circle
                      cx={pt.x}
                      cy={pt.y}
                      r={isHovered ? "6" : "4.5"}
                      fill="var(--surface, #0f172a)"
                      stroke={color}
                      strokeWidth="2.5"
                    />
                    {/* Inner Center Dot */}
                    <circle
                      cx={pt.x}
                      cy={pt.y}
                      r={isHovered ? "3" : "2"}
                      fill={color}
                    />
                  </g>
                );
              })}

              {/* Time Labels on X-Axis */}
              {points.map((pt, idx) => {
                // Show at most 6 labels along the axis
                const total = points.length;
                const shouldShow =
                  total <= 6 ||
                  idx === 0 ||
                  idx === total - 1 ||
                  idx % Math.ceil(total / 5) === 0;

                if (!shouldShow) return null;
                const dateObj = new Date(pt.timestamp);
                const timeStr = dateObj.toLocaleTimeString("vi-VN", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                });

                return (
                  <text
                    key={idx}
                    x={pt.x}
                    y={svgHeight - 8}
                    textAnchor="middle"
                    className="text-[10px] font-mono fill-current text-text-secondary/70"
                  >
                    {timeStr}
                  </text>
                );
              })}
            </svg>

            {/* Floating Tooltip */}
            {hoveredPoint && tooltipPos && (
              <div
                className="absolute pointer-events-none z-20 bg-slate-900 text-white rounded-lg p-2.5 text-xs shadow-xl border border-slate-700 min-w-[170px]"
                style={{
                  left: `${(tooltipPos.x / svgWidth) * 100}%`,
                  top: `${tooltipPos.y}px`,
                  transform: "translate(-50%, -125%)",
                }}
              >
                <div className="font-semibold text-slate-100 flex items-center justify-between gap-2 border-b border-slate-800 pb-1 mb-1.5">
                  <span>{hoveredPoint.name || `Sự kiện #${hoveredPoint.id}`}</span>
                  <span
                    className="px-1.5 py-0.2 rounded text-[10px] font-semibold"
                    style={{
                      backgroundColor: `${getSeverityColor(hoveredPoint.severity)}22`,
                      color: getSeverityColor(hoveredPoint.severity),
                    }}
                  >
                    {hoveredPoint.severity || "NORMAL"}
                  </span>
                </div>
                <div className="flex justify-between items-center text-slate-300 py-0.5">
                  <span className="text-slate-400">Giá trị đo:</span>
                  <span className="font-mono font-bold text-white">
                    {hoveredPoint.value} {unit}
                  </span>
                </div>
                {hoveredPoint.code !== undefined && (
                  <div className="flex justify-between items-center text-slate-300 py-0.5">
                    <span className="text-slate-400">Mã vi phạm:</span>
                    <span className="font-mono text-slate-200">
                      0x{hoveredPoint.code.toString(16).padStart(2, "0").toUpperCase()}
                    </span>
                  </div>
                )}
                <div className="flex justify-between items-center text-slate-400 text-[10px] pt-1 mt-1 border-t border-slate-800/80">
                  <span>Thời gian:</span>
                  <span className="font-mono">
                    {new Date(hoveredPoint.timestamp).toLocaleString("vi-VN")}
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
