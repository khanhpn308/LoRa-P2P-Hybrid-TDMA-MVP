package domain

import (
	"errors"
	"fmt"
	"regexp"
	"time"
)

var (
	// GatewayIDPattern matches the canonical gateway identifier.
	GatewayIDPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)
	// ChannelIDPattern matches the VN920 exclusive channel allocations CH00..CH10.
	ChannelIDPattern = regexp.MustCompile(`^CH(0[0-9]|10)$`)
	// UUIDPattern matches standard 36-character canonical UUID format.
	UUIDPattern = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

	ErrInvalidGatewayMode     = errors.New("mode must be one of BOOTSTRAP, ACTIVE, AUTONOMOUS, RECOVERY, FAULT, OFFLINE")
	ErrInvalidRFDuty          = errors.New("rf_duty_permille must be between 0 and 1000")
	ErrInvalidNodeCount       = errors.New("node_count must be between 0 and 254")
	ErrInvalidLimit           = errors.New("limit must be between 1 and 100")
	ErrInvalidCursor          = errors.New("cursor must be a valid non-negative integer")
	ErrInvalidNodeHealthState = errors.New("status must be ONLINE, OFFLINE, UNSYNCED, or UNKNOWN")
)

// GatewayMode represents the operating mode of a Gateway.
type GatewayMode string

const (
	GatewayModeBootstrap  GatewayMode = "BOOTSTRAP"
	GatewayModeActive     GatewayMode = "ACTIVE"
	GatewayModeAutonomous GatewayMode = "AUTONOMOUS"
	GatewayModeRecovery   GatewayMode = "RECOVERY"
	GatewayModeFault      GatewayMode = "FAULT"
	GatewayModeOffline    GatewayMode = "OFFLINE"
)

// GatewayStatusRecord encapsulates operational telemetry and hardware state for a Gateway.
type GatewayStatusRecord struct {
	GatewayID             string
	GatewayEpoch          string
	Mode                  GatewayMode
	ActiveScheduleVersion uint32
	ChannelID             *string
	RFDutyPermille        int
	NodeCount             int
	FreeHeapBytes         uint64
	OfflineQueueCount     uint32
	PendingEventCount     uint8
	DroppedEventCount     uint64
	LastSeenAt            time.Time
	UpdatedAt             time.Time
}

// Validate verifies domain invariants for GatewayStatusRecord.
func (r *GatewayStatusRecord) Validate() error {
	if !GatewayIDPattern.MatchString(r.GatewayID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayID, r.GatewayID)
	}
	if !UUIDPattern.MatchString(r.GatewayEpoch) {
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayEpoch, r.GatewayEpoch)
	}
	switch r.Mode {
	case GatewayModeBootstrap, GatewayModeActive, GatewayModeAutonomous,
		GatewayModeRecovery, GatewayModeFault, GatewayModeOffline:
	default:
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayMode, r.Mode)
	}
	if r.RFDutyPermille < 0 || r.RFDutyPermille > 1000 {
		return fmt.Errorf("%w: %d", ErrInvalidRFDuty, r.RFDutyPermille)
	}
	if r.NodeCount < 0 || r.NodeCount > 254 {
		return fmt.Errorf("%w: %d", ErrInvalidNodeCount, r.NodeCount)
	}
	if r.ChannelID != nil && *r.ChannelID != "" && !ChannelIDPattern.MatchString(*r.ChannelID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidChannelID, *r.ChannelID)
	}
	return nil
}

// GatewayStatusView represents the REST DTO returned by GET /api/v1/gateways/{gw_id}/status.
// Aligned with components.schemas.GatewayStatus in openapi.yaml.
type GatewayStatusView struct {
	GatewayID             string  `json:"gateway_id"`
	Mode                  string  `json:"mode"`
	ActiveScheduleVersion uint32  `json:"active_schedule_version"`
	LastSeenAt            *string `json:"last_seen_at"`
	RFDutyPermille        int     `json:"rf_duty_permille"`
	NodeCount             int     `json:"node_count"`
}

// NodeFilter defines query filtering and cursor pagination options for node listings.
type NodeFilter struct {
	GatewayID string
	Status    string
	Cursor    string
	Limit     int
}

// Validate checks query parameters bounds and formats.
func (f *NodeFilter) Validate() error {
	if f.Limit <= 0 || f.Limit > 100 {
		return ErrInvalidLimit
	}
	if f.GatewayID != "" && !GatewayIDPattern.MatchString(f.GatewayID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayID, f.GatewayID)
	}
	if f.Status != "" {
		switch f.Status {
		case "ONLINE", "OFFLINE", "UNSYNCED", "UNKNOWN":
		default:
			return fmt.Errorf("%w: '%s'", ErrInvalidNodeHealthState, f.Status)
		}
	}
	return nil
}

// NodeSummary represents an individual node item matching components.schemas.NodeSummary in openapi.yaml.
type NodeSummary struct {
	NodeID         int      `json:"node_id"`
	GatewayID      string   `json:"gateway_id"`
	Name           *string  `json:"name,omitempty"`
	AssignedSlotID *int     `json:"assigned_slot_id"`
	LastSeenAt     *string  `json:"last_seen_at"`
	LastRssiDbm    *int     `json:"last_rssi_dbm,omitempty"`
	LastSnrDb      *float64 `json:"last_snr_db,omitempty"`
	BatteryMv      *int     `json:"battery_mv,omitempty"`
	Status         string   `json:"status"`
}

// NodePage represents cursor-paginated nodes matching components.schemas.NodePage in openapi.yaml.
type NodePage struct {
	Items      []NodeSummary `json:"items"`
	NextCursor *string       `json:"next_cursor"`
}
