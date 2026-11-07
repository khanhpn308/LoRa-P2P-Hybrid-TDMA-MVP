package domain

import (
	"errors"
	"fmt"
	"time"
)

type HealthStatus string

const (
	HealthStatusOnline  HealthStatus = "ONLINE"
	HealthStatusOffline HealthStatus = "OFFLINE"
	HealthStatusUnknown HealthStatus = "UNKNOWN"
)

var (
	ErrInvalidHealthNodeID = errors.New("health node_id must be between 1 and 254")
	ErrInvalidHealthStatus = errors.New("invalid health status enum")
	ErrEmptyGatewayID      = errors.New("gateway_id cannot be empty")
)

// NodeHealth tracks the latest confirmed health report from UP_HEALTH_REPLY (0x44 21B).
type NodeHealth struct {
	GatewayID         string
	NodeID            uint8
	SessionSel        uint8
	FrameCounter      uint32
	MaintSeq          uint32
	StatusFlags       uint8
	PendingEventCount uint8
	HealthStatus      HealthStatus
	LastSeenAt        time.Time
	UpdatedAt         time.Time
}

// Validate validates the node health record.
func (h *NodeHealth) Validate() error {
	if h == nil {
		return errors.New("health record cannot be nil")
	}

	if h.GatewayID == "" {
		return ErrEmptyGatewayID
	}

	if h.NodeID < 1 || h.NodeID > 254 {
		return fmt.Errorf("%w: %d", ErrInvalidHealthNodeID, h.NodeID)
	}

	switch h.HealthStatus {
	case HealthStatusOnline, HealthStatusOffline, HealthStatusUnknown:
	default:
		return fmt.Errorf("%w: '%s'", ErrInvalidHealthStatus, h.HealthStatus)
	}

	return nil
}
