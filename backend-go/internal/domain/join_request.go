package domain

import (
	"time"
)

// DeviceJoinRequest represents an over-the-air node join request awaiting or processed by user approval.
type DeviceJoinRequest struct {
	ID             int64     `json:"id"`
	DeviceMAC      string    `json:"device_mac"`
	GatewayID      string    `json:"gateway_id"`
	RSSI           int       `json:"rssi"`
	SNR            float64   `json:"snr"`
	RawFrameHex    string    `json:"raw_frame_hex,omitempty"`
	Status         string    `json:"status"` // PENDING, APPROVED, REJECTED
	AssignedNodeID *int      `json:"assigned_node_id,omitempty"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}
