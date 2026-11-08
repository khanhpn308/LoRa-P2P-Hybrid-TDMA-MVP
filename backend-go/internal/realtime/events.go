package realtime

import (
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"time"
)

const (
	// SchemaVersionDraft matches contracts/api/schemas/realtime-event.schema.json.
	SchemaVersionDraft = "1.0-draft"

	// EventTypeAlertTriggered indicates an urgent edge alert from a node (Issue #232).
	EventTypeAlertTriggered = "ALERT_TRIGGERED"
	// EventTypeScheduleStateChanged indicates a TDMA schedule lifecycle state change.
	EventTypeScheduleStateChanged = "SCHEDULE_STATE_CHANGED"
	// EventTypeGatewayStatusChanged indicates gateway operational mode transition.
	EventTypeGatewayStatusChanged = "GATEWAY_STATUS_CHANGED"
	// EventTypeTelemetryUpdate indicates historical/deprecated telemetry playback.
	EventTypeTelemetryUpdate = "TELEMETRY_UPDATE"
)

var (
	gatewayIDPattern   = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)
	decimalIDPattern   = regexp.MustCompile(`^(0|[1-9][0-9]{0,19})$`)
	sourceEventPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}:(0|[1-9][0-9]{0,19})$`)

	ErrInvalidGatewayID     = errors.New("invalid gateway_id: must match ^[A-Za-z0-9_-]{1,32}$")
	ErrInvalidNodeID        = errors.New("invalid node_id: must be between 1 and 254")
	ErrInvalidAlertID       = errors.New("invalid alert_id: must match ^(0|[1-9][0-9]{0,19})$")
	ErrInvalidSeverity      = errors.New("invalid severity: must be P0_EMERGENCY, P1_HIGH, P2_MEDIUM, or P3_NORMAL")
	ErrInvalidScheduleID    = errors.New("invalid schedule_id: must match ^(0|[1-9][0-9]{0,19})$")
	ErrInvalidScheduleState = errors.New("invalid state: must be PROPOSED, SENT, STAGED, ACTIVE, REJECTED, or EXPIRED")
	ErrInvalidGatewayMode   = errors.New("invalid mode: must be BOOTSTRAP, ACTIVE, AUTONOMOUS, RECOVERY, FAULT, or OFFLINE")
	ErrInvalidReadingID     = errors.New("invalid reading_id: must match ^(0|[1-9][0-9]{0,19})$")
	ErrInvalidSourceEventID = errors.New("invalid source event_id format")
	ErrInvalidEventType     = errors.New("invalid or unsupported realtime event type")
)

// RealtimeEnvelope defines the standardized WebSocket notification envelope
// according to contracts/api/schemas/realtime-event.schema.json.
type RealtimeEnvelope struct {
	SchemaVersion string          `json:"schema_version"`
	EventID       string          `json:"event_id"`
	Type          string          `json:"type"`
	EmittedAt     string          `json:"emitted_at"`
	Cursor        *string         `json:"cursor,omitempty"`
	Payload       json.RawMessage `json:"payload"`
}

// AlertTriggeredPayload defines the payload for ALERT_TRIGGERED events.
type AlertTriggeredPayload struct {
	GatewayID   string  `json:"gateway_id"`
	NodeID      uint8   `json:"node_id"`
	AlertID     string  `json:"alert_id"`
	EventRef    uint32  `json:"event_ref"`
	EventCode   uint8   `json:"event_code"`
	EventValue  int16   `json:"event_value"`
	Severity    string  `json:"severity"`
	TriggeredAt *string `json:"triggered_at"`
}

// Validate verifies domain constraints according to realtime-event.schema.json.
func (p *AlertTriggeredPayload) Validate() error {
	if !gatewayIDPattern.MatchString(p.GatewayID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayID, p.GatewayID)
	}
	if p.NodeID < 1 || p.NodeID > 254 {
		return fmt.Errorf("%w: %d", ErrInvalidNodeID, p.NodeID)
	}
	if !decimalIDPattern.MatchString(p.AlertID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidAlertID, p.AlertID)
	}
	switch p.Severity {
	case "P0_EMERGENCY", "P1_HIGH", "P2_MEDIUM", "P3_NORMAL":
	default:
		return fmt.Errorf("%w: '%s'", ErrInvalidSeverity, p.Severity)
	}
	return nil
}

// ScheduleStateChangedPayload defines the payload for SCHEDULE_STATE_CHANGED events.
type ScheduleStateChangedPayload struct {
	GatewayID  string `json:"gateway_id"`
	ScheduleID string `json:"schedule_id"`
	Version    uint32 `json:"version"`
	State      string `json:"state"`
}

// Validate verifies domain constraints according to realtime-event.schema.json.
func (p *ScheduleStateChangedPayload) Validate() error {
	if !gatewayIDPattern.MatchString(p.GatewayID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayID, p.GatewayID)
	}
	if !decimalIDPattern.MatchString(p.ScheduleID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidScheduleID, p.ScheduleID)
	}
	switch p.State {
	case "PROPOSED", "SENT", "STAGED", "ACTIVE", "REJECTED", "EXPIRED":
	default:
		return fmt.Errorf("%w: '%s'", ErrInvalidScheduleState, p.State)
	}
	return nil
}

// GatewayStatusChangedPayload defines the payload for GATEWAY_STATUS_CHANGED events.
type GatewayStatusChangedPayload struct {
	GatewayID  string  `json:"gateway_id"`
	Mode       string  `json:"mode"`
	LastSeenAt *string `json:"last_seen_at"`
}

// Validate verifies domain constraints according to realtime-event.schema.json.
func (p *GatewayStatusChangedPayload) Validate() error {
	if !gatewayIDPattern.MatchString(p.GatewayID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayID, p.GatewayID)
	}
	switch p.Mode {
	case "BOOTSTRAP", "ACTIVE", "AUTONOMOUS", "RECOVERY", "FAULT", "OFFLINE":
	default:
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayMode, p.Mode)
	}
	return nil
}

// TelemetryData defines telemetry sensor readings for TELEMETRY_UPDATE.
type TelemetryData struct {
	Ch1Raw    int16  `json:"ch1_raw"`
	Ch2Raw    uint16 `json:"ch2_raw"`
	Ch3Raw    uint16 `json:"ch3_raw"`
	BatteryMv uint16 `json:"battery_mv"`
}

// TelemetryUpdatePayload defines the payload for historical TELEMETRY_UPDATE events.
type TelemetryUpdatePayload struct {
	GatewayID  string        `json:"gateway_id"`
	NodeID     uint8         `json:"node_id"`
	ReadingID  string        `json:"reading_id"`
	EventID    string        `json:"event_id"`
	ObservedAt *string       `json:"observed_at"`
	Data       TelemetryData `json:"data"`
}

// Validate verifies domain constraints according to realtime-event.schema.json.
func (p *TelemetryUpdatePayload) Validate() error {
	if !gatewayIDPattern.MatchString(p.GatewayID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayID, p.GatewayID)
	}
	if p.NodeID < 1 || p.NodeID > 254 {
		return fmt.Errorf("%w: %d", ErrInvalidNodeID, p.NodeID)
	}
	if !decimalIDPattern.MatchString(p.ReadingID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidReadingID, p.ReadingID)
	}
	if !sourceEventPattern.MatchString(p.EventID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidSourceEventID, p.EventID)
	}
	return nil
}

// GenerateUUIDv4 generates an RFC 4122 variant 4 UUID string.
func GenerateUUIDv4() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", fmt.Errorf("failed to generate random uuid: %w", err)
	}
	b[6] = (b[6] & 0x0f) | 0x40 // Version 4
	b[8] = (b[8] & 0x3f) | 0x80 // RFC 4122 variant
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16]), nil
}

// FormatUTCZ formats time in UTC RFC3339 with guaranteed trailing 'Z'.
func FormatUTCZ(t time.Time) string {
	return t.UTC().Format("2006-01-02T15:04:05Z")
}

// BuildEnvelope encapsulates a validated payload into a RealtimeEnvelope.
func BuildEnvelope(eventType string, payloadObj any, cursor *string) (*RealtimeEnvelope, error) {
	payloadBytes, err := json.Marshal(payloadObj)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal payload: %w", err)
	}

	eventID, err := GenerateUUIDv4()
	if err != nil {
		return nil, err
	}

	return &RealtimeEnvelope{
		SchemaVersion: SchemaVersionDraft,
		EventID:       eventID,
		Type:          eventType,
		EmittedAt:     FormatUTCZ(time.Now()),
		Cursor:        cursor,
		Payload:       payloadBytes,
	}, nil
}

// NewAlertTriggeredEvent constructs and validates an ALERT_TRIGGERED RealtimeEnvelope.
func NewAlertTriggeredEvent(payload AlertTriggeredPayload, cursor *string) (*RealtimeEnvelope, error) {
	if err := payload.Validate(); err != nil {
		return nil, err
	}
	return BuildEnvelope(EventTypeAlertTriggered, payload, cursor)
}

// NewScheduleStateChangedEvent constructs and validates a SCHEDULE_STATE_CHANGED RealtimeEnvelope.
func NewScheduleStateChangedEvent(payload ScheduleStateChangedPayload, cursor *string) (*RealtimeEnvelope, error) {
	if err := payload.Validate(); err != nil {
		return nil, err
	}
	return BuildEnvelope(EventTypeScheduleStateChanged, payload, cursor)
}

// NewGatewayStatusChangedEvent constructs and validates a GATEWAY_STATUS_CHANGED RealtimeEnvelope.
func NewGatewayStatusChangedEvent(payload GatewayStatusChangedPayload, cursor *string) (*RealtimeEnvelope, error) {
	if err := payload.Validate(); err != nil {
		return nil, err
	}
	return BuildEnvelope(EventTypeGatewayStatusChanged, payload, cursor)
}

// NewTelemetryUpdateEvent constructs and validates a TELEMETRY_UPDATE RealtimeEnvelope.
func NewTelemetryUpdateEvent(payload TelemetryUpdatePayload, cursor *string) (*RealtimeEnvelope, error) {
	if err := payload.Validate(); err != nil {
		return nil, err
	}
	return BuildEnvelope(EventTypeTelemetryUpdate, payload, cursor)
}
