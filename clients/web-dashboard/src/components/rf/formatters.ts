/**
 * LoRa RF Metrics Presentation & Formatting Utilities (#394)
 */

export function formatRfSource(source?: string | null): string {
  if (!source) return "N/A";
  if (source === "UP_EVENT") return "Sự kiện (UP_EVENT)";
  if (source === "UP_HEARTBEAT_ACK") return "Heartbeat ACK";
  return source;
}

export function formatRfAge(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return "Mới nhận";
  if (seconds < 0) return "Mới nhận";
  if (seconds < 60) return `${Math.round(seconds)}s trước`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m trước`;
  return `${Math.floor(seconds / 3600)}h trước`;
}
