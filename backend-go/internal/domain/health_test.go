package domain_test

import (
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

func TestNodeHealth_Validation_Success(t *testing.T) {
	h := &domain.NodeHealth{
		GatewayID:         "gw01",
		NodeID:            2,
		SessionSel:        1,
		FrameCounter:      100,
		MaintSeq:          10,
		StatusFlags:       0,
		PendingEventCount: 0,
		HealthStatus:      domain.HealthStatusOnline,
		LastSeenAt:        time.Now().UTC(),
		UpdatedAt:         time.Now().UTC(),
	}

	if err := h.Validate(); err != nil {
		t.Fatalf("expected valid node health, got: %v", err)
	}
}

func TestNodeHealth_Validation_InvalidNodeID(t *testing.T) {
	h := &domain.NodeHealth{
		GatewayID:    "gw01",
		NodeID:       0,
		HealthStatus: domain.HealthStatusOnline,
	}

	if err := h.Validate(); err == nil {
		t.Fatalf("expected error for node_id=0")
	}
}

func TestNodeHealth_Validation_InvalidStatus(t *testing.T) {
	h := &domain.NodeHealth{
		GatewayID:    "gw01",
		NodeID:       5,
		HealthStatus: "INVALID_STATUS",
	}

	if err := h.Validate(); err == nil {
		t.Fatalf("expected error for invalid health status")
	}
}
