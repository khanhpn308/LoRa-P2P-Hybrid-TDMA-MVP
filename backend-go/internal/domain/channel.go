package domain

import (
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"
)

// Channel plan constants for VN920 V1.
const (
	// ChannelPlanVN920V1 is the approved project-specific channel plan version for VN920.
	ChannelPlanVN920V1 = "VN920_V1"

	// DefaultBandwidthHz is 125 kHz per VN920 PHY baseline.
	DefaultBandwidthHz int64 = 125000

	// ChannelCountVN920 is the exact count of approved channels in the catalogue (CH00..CH10).
	ChannelCountVN920 = 11

	// Status constants for channels and allocations.
	StatusAvailable = "AVAILABLE"
	StatusAllocated = "ALLOCATED"
	StatusReleased  = "RELEASED"
	StatusDisabled  = "DISABLED"

	// RegulatoryNotice documents the legal/regulatory boundary per Issue #154 acceptance criteria.
	RegulatoryNotice = "VN920 project channel plan is not a substitute for effective Vietnamese ERP/duty cycle/emissions rules or antenna/RF/HIL compliance."
)

// Domain error definitions.
var (
	ErrChannelNotFound         = errors.New("channel not found in catalogue")
	ErrChannelDisabled         = errors.New("channel is administratively disabled")
	ErrChannelInUse            = errors.New("channel is already allocated to another gateway")
	ErrGatewayAlreadyAllocated = errors.New("gateway already holds an active channel allocation")
	ErrInvalidChannelPlan      = errors.New("invalid or unsupported channel plan version")
	ErrInvalidChannelID        = errors.New("invalid channel id")
	ErrInvalidGatewayID        = errors.New("invalid gateway id")
	ErrInvalidRequestID        = errors.New("invalid request id")
	ErrAllocationNotFound      = errors.New("active allocation not found")
	ErrAlreadyReleased         = errors.New("allocation is already released")
	ErrUnauthorized            = errors.New("unauthorized gateway request")
)

var (
	gatewayIDRegex = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,64}$`)
	requestIDRegex = regexp.MustCompile(`^[a-zA-Z0-9_.-]{1,128}$`)
)

// ApprovedVN920Catalogue contains the 11 approved VN920_V1 channels with exact integer Hz center frequencies.
// Spacing is 250 kHz (250000 Hz), bandwidth is 125 kHz (125000 Hz).
var ApprovedVN920Catalogue = map[string]int64{
	"CH00": 920250000,
	"CH01": 920500000,
	"CH02": 920750000,
	"CH03": 921000000,
	"CH04": 921250000,
	"CH05": 921500000,
	"CH06": 921750000,
	"CH07": 922000000,
	"CH08": 922250000,
	"CH09": 922500000,
	"CH10": 922750000,
}

// RFChannel represents a registered RF channel entry in the catalogue.
type RFChannel struct {
	ChannelID          string    `json:"channel_id"`
	ChannelPlanVersion string    `json:"channel_plan_version"`
	CenterFrequencyHz  int64     `json:"center_frequency_hz"`
	BandwidthHz        int64     `json:"bandwidth_hz"`
	IsEnabled          bool      `json:"is_enabled"`
	CreatedAt          time.Time `json:"created_at"`
	UpdatedAt          time.Time `json:"updated_at"`
}

// ChannelAllocation records an exclusive assignment of an RF channel to a Gateway.
type ChannelAllocation struct {
	ID                   int64      `json:"id"`
	GatewayID            string     `json:"gateway_id"`
	ChannelID            string     `json:"channel_id"`
	Status               string     `json:"status"` // ALLOCATED or RELEASED
	RequestID            string     `json:"request_id"`
	AllocationGeneration int64      `json:"allocation_generation"`
	GrantedBy            string     `json:"granted_by"`
	ReleasedBy           string     `json:"released_by,omitempty"`
	ReleaseReason        string     `json:"release_reason,omitempty"`
	CreatedAt            time.Time  `json:"created_at"`
	UpdatedAt            time.Time  `json:"updated_at"`
	ReleasedAt           *time.Time `json:"released_at,omitempty"`
}

// ChannelView combines channel definition with dynamic allocation status,
// without leaking the identity of other Gateways holding allocated channels.
type ChannelView struct {
	ChannelID          string `json:"channel_id"`
	ChannelPlanVersion string `json:"channel_plan_version"`
	CenterFrequencyHz  int64  `json:"center_frequency_hz"`
	BandwidthHz        int64  `json:"bandwidth_hz"`
	IsEnabled          bool   `json:"is_enabled"`
	State              string `json:"state"` // AVAILABLE, ALLOCATED, or DISABLED
}

// AllocateRequest contains validated inputs to request exclusive channel allocation.
type AllocateRequest struct {
	GatewayID          string `json:"gateway_id"`
	ChannelID          string `json:"channel_id"`
	ChannelPlanVersion string `json:"channel_plan_version"`
	RequestID          string `json:"request_id"`
	GrantedBy          string `json:"granted_by"`
}

// ReleaseRequest contains validated inputs to release an active channel allocation.
type ReleaseRequest struct {
	GatewayID     string `json:"gateway_id"`
	ChannelID     string `json:"channel_id"`
	RequestID     string `json:"request_id"`
	ReleasedBy    string `json:"released_by"`
	ReleaseReason string `json:"release_reason"`
}

// ValidateChannelID verifies the channel ID against the approved catalogue.
func ValidateChannelID(channelID string) error {
	normalized := strings.TrimSpace(channelID)
	if normalized == "" {
		return fmt.Errorf("%w: empty channel id", ErrInvalidChannelID)
	}
	if _, ok := ApprovedVN920Catalogue[normalized]; !ok {
		return fmt.Errorf("%w: unknown channel %q (must be CH00..CH10)", ErrChannelNotFound, normalized)
	}
	return nil
}

// ValidateChannelPlanVersion checks if the plan version is supported.
func ValidateChannelPlanVersion(version string) error {
	if strings.TrimSpace(version) != ChannelPlanVN920V1 {
		return fmt.Errorf("%w: expected %q, got %q", ErrInvalidChannelPlan, ChannelPlanVN920V1, version)
	}
	return nil
}

// ValidateGatewayID validates the Gateway identity string.
func ValidateGatewayID(gatewayID string) error {
	trimmed := strings.TrimSpace(gatewayID)
	if trimmed == "" || !gatewayIDRegex.MatchString(trimmed) {
		return fmt.Errorf("%w: invalid gateway identifier format", ErrInvalidGatewayID)
	}
	return nil
}

// ValidateRequestID validates the request idempotency key.
func ValidateRequestID(requestID string) error {
	trimmed := strings.TrimSpace(requestID)
	if trimmed == "" || !requestIDRegex.MatchString(trimmed) {
		return fmt.Errorf("%w: invalid request id format", ErrInvalidRequestID)
	}
	return nil
}

// GetApprovedFrequencyHz returns the center frequency in integer Hz for a given channel.
func GetApprovedFrequencyHz(channelID string) (int64, error) {
	freq, ok := ApprovedVN920Catalogue[channelID]
	if !ok {
		return 0, fmt.Errorf("%w: %q", ErrChannelNotFound, channelID)
	}
	return freq, nil
}
