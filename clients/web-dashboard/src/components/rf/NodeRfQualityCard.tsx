"use client";

import React from "react";
import { Radio } from "lucide-react";
import { formatRfSource, formatRfAge } from "./formatters.ts";

export { formatRfSource, formatRfAge };

export interface NodeRfQualityCardProps {
  lastRssiDbm?: number | null;
  lastSnrDb?: number | null;
  rfSource?: string | null;
  rfAgeSeconds?: number | null;
  lastRfAt?: string | null;
  rfStale?: boolean | null;
  status?: string; // e.g. "ONLINE" | "OFFLINE"
  isLoading?: boolean;
  isError?: boolean;
  className?: string;
}

export const NodeRfQualityCard: React.FC<NodeRfQualityCardProps> = ({
  lastRssiDbm,
  lastSnrDb,
  rfSource,
  rfAgeSeconds,
  rfStale,
  status,
  isLoading,
  isError,
  className = "",
}) => {
  const hasRssi = lastRssiDbm !== null && lastRssiDbm !== undefined;
  const hasSnr = lastSnrDb !== null && lastSnrDb !== undefined;
  const isOffline = status === "OFFLINE";

  // Freshness status label and styling
  let freshnessLabel = "Mới nhận";
  let freshnessStyle = "text-emerald-600 dark:text-emerald-400";

  if (isOffline) {
    freshnessLabel = "Node ngoại tuyến";
    freshnessStyle = "text-text-secondary";
  } else if (isError) {
    freshnessLabel = "Lỗi kết nối API";
    freshnessStyle = "text-amber-600 dark:text-amber-400 font-medium";
  } else if (!hasRssi && !hasSnr) {
    freshnessLabel = "Chưa có dữ liệu";
    freshnessStyle = "text-text-secondary";
  } else if (rfStale) {
    freshnessLabel = "Đã cũ (Stale)";
    freshnessStyle = "text-amber-600 dark:text-amber-400 font-medium";
  } else if (rfAgeSeconds !== null && rfAgeSeconds !== undefined) {
    freshnessLabel = formatRfAge(rfAgeSeconds);
  }

  // SNR display: real 0 dB remains "0 dB" (quarter-dB precision preserved)
  let snrDisplay = "N/A";
  if (hasSnr) {
    // Preserve exact numeric precision (e.g. -7.75)
    snrDisplay = `${lastSnrDb} dB`;
  }

  return (
    <div
      className={`bg-chrome rounded-lg p-5 border border-border flex flex-col justify-between ${className}`}
      data-testid="rf-quality-card"
    >
      <div className="flex items-center justify-between text-text-secondary">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs font-medium">Chất lượng RF</span>
          <span
            className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-surface border border-border text-text-secondary"
            title="Đo lường gói tin chiều tải lên từ Node đến Gateway"
            data-testid="rf-direction-label"
          >
            Node → Gateway
          </span>
        </div>
        <Radio className="w-4 h-4 text-interactive shrink-0" />
      </div>

      <div className="my-2">
        {hasRssi ? (
          <div className="flex items-baseline">
            <span
              className="text-3xl font-semibold font-mono tabular-nums text-text-primary tracking-tight"
              data-testid="rf-rssi-value"
            >
              {lastRssiDbm}
            </span>
            <span className="text-sm font-medium text-text-secondary ml-1.5" data-testid="rf-rssi-unit">
              dBm
            </span>
          </div>
        ) : (
          <div className="flex items-baseline">
            <span
              className="text-3xl font-semibold font-mono tabular-nums text-text-secondary tracking-tight"
              data-testid="rf-rssi-value"
            >
              N/A
            </span>
          </div>
        )}
      </div>

      <div className="space-y-1 text-xs text-text-secondary font-mono">
        <div className="flex items-center justify-between">
          <span>SNR:</span>
          <span className="font-semibold text-text-primary" data-testid="rf-snr-value">
            {snrDisplay}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <span>Nguồn:</span>
          <span className="text-text-primary truncate max-w-[150px]" data-testid="rf-source-value">
            {formatRfSource(rfSource)}
          </span>
        </div>

        <div className="flex items-center justify-between pt-1 border-t border-border/50 text-[11px]">
          <span>Độ tươi:</span>
          <span className={freshnessStyle} data-testid="rf-freshness-status">
            {isLoading ? "Đang cập nhật..." : freshnessLabel}
          </span>
        </div>
      </div>
    </div>
  );
};
