package scheduler_test

import (
	"context"
	"math"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

type mockChannelChecker struct {
	allocations map[string]*scheduler.ChannelAllocation
}

func (m *mockChannelChecker) GetActiveAllocationByGateway(ctx context.Context, gatewayID string) (*scheduler.ChannelAllocation, error) {
	return m.allocations[gatewayID], nil
}

func TestCalculateToA(t *testing.T) {
	phySF7 := scheduler.DefaultVN920PHY()

	// 1. Check UP_HEALTH_REPLY (21 octets) at SF7
	// Expected from specification.md §3.3.6: ~56.6 ms (56.576 ms)
	toaHealth, err := scheduler.CalculateToA(scheduler.BytesUpHealthReply, phySF7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	toaHealthMs := toaHealth.Seconds() * 1000.0
	if math.Abs(toaHealthMs-56.576) > 0.1 {
		t.Errorf("expected UP_HEALTH_REPLY ToA ~56.6 ms, got %.3f ms", toaHealthMs)
	}

	// 2. Check UP_EVENT (26 octets) at SF7
	toaEvent, err := scheduler.CalculateToA(scheduler.BytesUpEvent, phySF7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	toaEventMs := toaEvent.Seconds() * 1000.0
	if toaEventMs <= 0 || toaEventMs > 100.0 {
		t.Errorf("unreasonable UP_EVENT ToA: %.3f ms", toaEventMs)
	}

	// 3. Check DOWN_EVENT_ACK (19 octets) at SF7
	toaAck, err := scheduler.CalculateToA(scheduler.BytesDownEventAck, phySF7)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	toaAckMs := toaAck.Seconds() * 1000.0
	if toaAckMs <= 0 || toaAckMs > 100.0 {
		t.Errorf("unreasonable DOWN_EVENT_ACK ToA: %.3f ms", toaAckMs)
	}

	// 4. Check SF8 ToA is strictly greater than SF7
	phySF8 := scheduler.SF8VN920PHY()
	toaEventSF8, err := scheduler.CalculateToA(scheduler.BytesUpEvent, phySF8)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if toaEventSF8 <= toaEvent {
		t.Errorf("expected SF8 ToA (%v) to be strictly greater than SF7 (%v)", toaEventSF8, toaEvent)
	}
}

func TestValidateScheduleFeasibility(t *testing.T) {
	checker := &mockChannelChecker{
		allocations: map[string]*scheduler.ChannelAllocation{
			"gw01": {
				GatewayID: "gw01",
				ChannelID: "CH00",
				Status:    scheduler.StatusAllocated,
			},
		},
	}
	validator := scheduler.NewFeasibilityValidator(checker)

	now := time.Now().UTC()
	sched := &scheduler.Schedule{
		SchemaVersion:          scheduler.DefaultSchemaVersion,
		RequestID:              "3f3f88dc-80a5-4bc7-92c8-1dc97aa0797b",
		GatewayID:              "gw01",
		ScheduleID:             "1",
		ScheduleVersion:        1,
		ScheduleGeneration:     1,
		CreatedAt:              now,
		ExpiresAt:              now.Add(10 * time.Minute),
		ProfileID:              scheduler.ProfileV2VN920Static15N,
		SuperframeMs:           scheduler.TotalDataRegionMs,
		MinAnnounceSuperframes: 3,
		ChannelID:              "CH00",
		NetworkID:              1,
		Slots: []scheduler.SlotConfig{
			{NodeID: 1, SlotID: 1, OffsetMs: 50, DurationMs: 500},
		},
		AffectedNodeSet: []uint8{1},
	}

	// Test SF7 feasibility
	report, err := validator.ValidateScheduleFeasibility(context.Background(), sched, scheduler.DefaultVN920PHY())
	if err != nil {
		t.Fatalf("feasibility check failed: %v", err)
	}
	if !report.IsFeasible {
		t.Errorf("expected schedule to be feasible")
	}
	if !report.ChannelVerified {
		t.Errorf("expected channel to be verified")
	}
	if report.UsableSlotMarginMs <= 0 {
		t.Errorf("expected positive usable slot margin, got %.2f ms", report.UsableSlotMarginMs)
	}
	if report.GuardMarginMs <= 0 {
		t.Errorf("expected positive guard margin, got %.2f ms", report.GuardMarginMs)
	}

	// Test SF8 feasibility
	reportSF8, err := validator.ValidateScheduleFeasibility(context.Background(), sched, scheduler.SF8VN920PHY())
	if err != nil {
		t.Fatalf("SF8 feasibility check failed: %v", err)
	}
	if !reportSF8.IsFeasible {
		t.Errorf("expected SF8 schedule to be feasible")
	}

	// Test channel mismatch
	schedMismatched := *sched
	schedMismatched.ChannelID = "CH01"
	if _, err := validator.ValidateScheduleFeasibility(context.Background(), &schedMismatched, scheduler.DefaultVN920PHY()); err == nil {
		t.Errorf("expected error when gateway holds CH00 but schedule requests CH01")
	}
}
