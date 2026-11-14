"use client";

import React from "react";
import { Radio } from "lucide-react";
import { formatRfAge } from "./formatters.ts";

export interface GatewayChannelRfCardProps {
  channelRssiDbm?: number | null;
  channelRfAt?: string | null;
  channelRfAgeSeconds?: number | null;
  channelRfStale?: boolean | null;
  channelIdx?: number | null;
  channelSampleContext?: string | null;
  channel?: string;
  frequency?: string;
  mode?: string;
  isLoading?: boolean;
  isError?: boolean;
  className?: string;
}

export const GatewayChannelRfCard: React.FC<GatewayChannelRfCardProps> = ({
  channelRssiDbm,
  channelRfAt,
  channelRfAgeSeconds,
  channelRfStale,
  channelIdx,
  channelSampleContext,
  channel = "CH01",
  frequency = "920.500 MHz",
  mode,
  isLoading,
  isError,
  className = "",
}) => {
  const hasRssi = channelRssiDbm !== null && channelRssiDbm !== undefined;
  const isOffline = mode === "OFFLINE";

  // Freshness status label and styling
  let freshnessLabel = "Mới nhận";
  let freshnessStyle = "text-emerald-600 dark:text-emerald-400";

  if (isOffline) {
    freshnessLabel = "Gateway ngoại tuyến";
    freshnessStyle = "text-text-secondary";
  } else if (isError) {
    freshnessLabel = "Lỗi kết nối API";
    freshnessStyle = "text-amber-600 dark:text-amber-400 font-medium";
  } else if (!hasRssi) {
    freshnessLabel = "Chưa có mẫu đo";
    freshnessStyle = "text-text-secondary";
  } else if (channelRfStale) {
    freshnessLabel = "Đã cũ (Stale)";
    freshnessStyle = "text-amber-600 dark:text-amber-400 font-medium";
  } else if (channelRfAgeSeconds !== null && channelRfAgeSeconds !== undefined) {
    freshnessLabel = formatRfAge(channelRfAgeSeconds);
  }

  return (
    <div
      className={`mt-4 bg-canvas rounded-lg p-4 border border-border ${className}`}
      data-testid="gateway-channel-rf-card"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-interactive shrink-0" />
          <span className="text-sm font-semibold text-text-primary">
            Năng lượng kênh LoRa (Channel RSSI)
          </span>
          <span
            className="text-[10px] font-medium px-2 py-0.5 rounded bg-surface border border-border text-text-secondary"
            data-testid="gateway-rf-badge"
          >
            LoRa PHY
          </span>
        </div>
        <div className="text-xs text-text-secondary font-mono" data-testid="gateway-channel-rf-context">
          Mẫu kênh: <span className="font-semibold text-text-primary">{channelSampleContext || "RX_IDLE"}</span>
          {channelIdx !== null && channelIdx !== undefined && (
            <span className="ml-2 text-text-secondary">(Chỉ số kênh: {channelIdx})</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-center">
        <div>
          <span className="text-xs text-text-secondary block">Mức năng lượng đo được</span>
          <div className="flex items-baseline mt-1">
            {hasRssi ? (
              <>
                <span
                  className="text-2xl font-bold font-mono text-text-primary tabular-nums"
                  data-testid="gateway-channel-rssi-value"
                >
                  {channelRssiDbm}
                </span>
                <span className="text-xs font-medium text-text-secondary ml-1" data-testid="gateway-channel-rssi-unit">
                  dBm
                </span>
              </>
            ) : (
              <span
                className="text-2xl font-bold font-mono text-text-secondary"
                data-testid="gateway-channel-rssi-value"
              >
                N/A
              </span>
            )}
          </div>
        </div>

        <div>
          <span className="text-xs text-text-secondary block">Kênh tần số giám sát</span>
          <span
            className="text-sm font-mono font-medium text-text-primary mt-1 block truncate"
            data-testid="gateway-channel-rf-freq"
          >
            {channel} · {frequency}
          </span>
        </div>

        <div>
          <span className="text-xs text-text-secondary block">Độ tươi dữ liệu</span>
          <div className="text-xs font-mono mt-1" data-testid="gateway-channel-rf-freshness">
            <span className={freshnessStyle}>
              {isLoading ? "Đang cập nhật..." : freshnessLabel}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-3 pt-2 border-t border-border/40 text-[11px] text-text-secondary flex flex-wrap items-center justify-between gap-2">
        <span>Mức năng lượng RF trên kênh LoRa (không đại diện cho riêng Node nào, tách biệt với Wi-Fi RSSI)</span>
        {channelRfAt && (
          <span className="font-mono text-[10px]" data-testid="gateway-channel-rf-at">
            Thời điểm đo: {channelRfAt}
          </span>
        )}
      </div>
    </div>
  );
};
