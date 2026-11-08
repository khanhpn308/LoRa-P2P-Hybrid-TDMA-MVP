/**
 * LoRa Hybrid TDMA MVP — Frontend API Contracts & DTOs
 * Strictly aligned with contracts/api/openapi.yaml, ADR-0005, and Event-Only V2 architecture.
 */

// ==========================================
// 1. Authentication & RBAC (ADR-0005)
// ==========================================

export type UserRole = "ADMIN" | "OPERATOR" | "VIEWER";

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "Bearer";
  expires_in: number; // in seconds (e.g., 3600)
  role: UserRole;
}

export interface WsTicketResponse {
  ticket: string;
  expires_in: number; // in seconds (e.g., 30)
}

export interface User {
  id: string;
  username: string;
  full_name?: string;
  email?: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface CreateUserRequest {
  username: string;
  full_name?: string;
  email?: string;
  password: string;
  role: UserRole;
}

// ==========================================
// 2. Gateway Contracts (OpenAPI 3.0.3)
// ==========================================

export type GatewayMode =
  | "BOOTSTRAP"
  | "ACTIVE"
  | "AUTONOMOUS"
  | "RECOVERY"
  | "FAULT"
  | "OFFLINE";

export interface GatewayStatus {
  gateway_id: string;
  mode: GatewayMode;
  active_schedule_version: number;
  last_seen_at: string | null;
  rf_duty_permille: number; // 0..1000
  node_count: number; // 0..254
}

export interface GatewayItem extends GatewayStatus {
  name: string;
  location?: string;
  ip_address?: string;
  online: boolean;
  operating: boolean;
  channel_id: string; // e.g. "CH01"
  frequency_hz: number; // 920250000..922750000
}

// ==========================================
// 3. Node & Device Contracts (Event-Only V2)
// ==========================================

export type NodeStatus = "ONLINE" | "OFFLINE" | "UNSYNCED" | "UNKNOWN";

export interface NodeSummary {
  node_id: number; // 1..254
  gateway_id: string;
  name?: string;
  assigned_slot_id: number | null; // 1..15
  last_seen_at: string | null;
  last_rssi_dbm: number | null;
  last_snr_db: number | null;
  battery_mv: number | null;
  status: NodeStatus;
}

export interface NodeItem extends NodeSummary {
  connected: boolean;
  operating: boolean;
  state: "NORMAL" | "FAULT" | "MAINTENANCE" | "OFFLINE";
  last_event_type?: string;
}

// ==========================================
// 4. Alerts & Fault Events (UP_EVENT 0x41)
// ==========================================

export type AlertSeverity =
  | "P0_EMERGENCY"
  | "P1_HIGH"
  | "P2_MEDIUM"
  | "P3_NORMAL";

export type AlertAckStatus = "UNACKNOWLEDGED" | "ACKNOWLEDGED";

export interface AlertTrigger {
  channel: number;
  observed_raw: number;
  threshold_raw: number;
}

export interface Alert {
  alert_id: string;
  node_id: number;
  gateway_id: string;
  event_ref: number;
  event_code: number;
  event_value: number;
  severity: AlertSeverity;
  triggered_at: string | null;
  received_at: string;
  ack_status: AlertAckStatus;
  acked_at: string | null;
  trigger?: AlertTrigger;
}

// ==========================================
// 5. Schedules (TDMA Superframe Management)
// ==========================================

export type ScheduleState =
  | "PROPOSED"
  | "SENT"
  | "STAGED"
  | "ACTIVE"
  | "REJECTED"
  | "EXPIRED";

export type ScheduleReviewState = "PENDING" | "APPROVED" | "REJECTED";

export interface ScheduleSummary {
  schedule_id: string;
  gateway_id: string;
  version: number;
  state: ScheduleState;
  activate_at_superframe_seq: number | null;
  created_at: string;
  activated_at: string | null;
  reject_reason?: string | null;
  review_state?: ScheduleReviewState;
}

export interface ScheduleReviewRequest {
  decision: "APPROVE" | "REJECT";
  note?: string;
}

export interface ScheduleActivationRequest {
  expected_version: number;
}

// ==========================================
// 6. Channel Allocation (VN920_V1)
// ==========================================

export interface ChannelInfo {
  channel_id: string; // CH00..CH10
  frequency_hz: number; // 920.25 - 922.75 MHz
  bandwidth_hz: 125000;
  status: "AVAILABLE" | "ALLOCATED";
  assigned_gateway_id?: string | null;
}

export interface ChannelAllocation {
  gateway_id: string;
  channel_id: string;
  frequency_hz: number;
  bandwidth_hz: 125000;
  allocation_generation: number;
  allocated_at: string;
  rf_authorized: boolean;
  state: "ALLOCATED" | "RELEASED";
}

// ==========================================
// 7. Provisioning Contracts (Issue #242)
// ==========================================

export interface DeviceProvisionRequest {
  network_id: number;
  device_mac: string;
  k_join: string;
  generation?: number;
  initial_join_counter?: number;
}

export interface DeviceProvisionResponse {
  device_mac: string;
  network_id: number;
  generation: number;
  status: string;
  created_at: string;
}

export interface AcknowledgeAlertRequest {
  acknowledged_by?: string;
}

// ==========================================
// 8. Realtime WebSocket Contracts (Issue #15, #251)
// ==========================================

export type RealtimeEventType =
  | "ALERT_TRIGGERED"
  | "SCHEDULE_STATE_CHANGED"
  | "GATEWAY_STATUS_CHANGED"
  | "TELEMETRY_UPDATE"
  | "COMMAND_STATE_CHANGED";

export type WsConnectionState =
  | "CONNECTING"
  | "CONNECTED"
  | "RECONNECTING"
  | "DISCONNECTED";

export interface AlertTriggeredPayload {
  gateway_id: string;
  node_id: number;
  alert_id: string;
  event_ref: number;
  event_code: number;
  event_value: number;
  severity: AlertSeverity;
  triggered_at: string | null;
}

export interface ScheduleStateChangedPayload {
  gateway_id: string;
  schedule_id: string;
  version: number;
  state: ScheduleState;
}

export interface GatewayStatusChangedPayload {
  gateway_id: string;
  mode: GatewayMode;
  last_seen_at: string | null;
}

export interface TelemetryUpdatePayload {
  gateway_id: string;
  node_id: number;
  reading_id: string;
  event_id: string;
  observed_at: string | null;
  data: Record<string, unknown>;
}

export interface RealtimeEnvelope<T = unknown> {
  schema_version: string;
  event_id: string;
  type: RealtimeEventType;
  emitted_at: string;
  cursor?: string | null;
  payload: T;
}

// ==========================================
// 9. Generic API Types
// ==========================================

export interface ApiError {
  code: string;
  message: string;
  request_id?: string;
  details?: Record<string, unknown>;
}

export interface PageResponse<T> {
  items: T[];
  next_cursor: string | null;
}
