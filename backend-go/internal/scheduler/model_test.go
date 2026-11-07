package scheduler_test

import (
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

func TestSlotGeometry(t *testing.T) {
	// Verify slot 1 geometry: reserved 0..600ms, usable 50..550ms
	rStart, uStart, uEnd, rEnd, err := scheduler.SlotGeometry(1, 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if rStart != 0 || uStart != 50 || uEnd != 550 || rEnd != 600 {
		t.Errorf("slot 1 geometry miscalculated: rStart=%d uStart=%d uEnd=%d rEnd=%d",
			rStart, uStart, uEnd, rEnd)
	}

	// Verify slot 2 geometry: reserved 600..1200ms, usable 650..1150ms
	rStart, uStart, uEnd, rEnd, err = scheduler.SlotGeometry(2, 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if rStart != 600 || uStart != 650 || uEnd != 1150 || rEnd != 1200 {
		t.Errorf("slot 2 geometry miscalculated: rStart=%d uStart=%d uEnd=%d rEnd=%d",
			rStart, uStart, uEnd, rEnd)
	}

	// Verify slot 15 geometry: reserved 8400..9000ms, usable 8450..8950ms
	rStart, uStart, uEnd, rEnd, err = scheduler.SlotGeometry(15, 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if rStart != 8400 || uStart != 8450 || uEnd != 8950 || rEnd != 9000 {
		t.Errorf("slot 15 geometry miscalculated: rStart=%d uStart=%d uEnd=%d rEnd=%d",
			rStart, uStart, uEnd, rEnd)
	}
	if rEnd != scheduler.TotalDataRegionMs {
		t.Errorf("expected 15 slots to span exactly %d ms, got %d ms",
			scheduler.TotalDataRegionMs, rEnd)
	}

	// Out of bounds tests
	if _, _, _, _, err := scheduler.SlotGeometry(0, 0); err == nil {
		t.Errorf("expected error for slot 0")
	}
	if _, _, _, _, err := scheduler.SlotGeometry(16, 0); err == nil {
		t.Errorf("expected error for slot 16")
	}
}

func TestReadyGeometry(t *testing.T) {
	// Verify READY slot 1: reserved 0..500ms, usable 50..450ms
	rStart, uStart, uEnd, rEnd, err := scheduler.ReadyGeometry(1, 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if rStart != 0 || uStart != 50 || uEnd != 450 || rEnd != 500 {
		t.Errorf("ready slot 1 miscalculated: rStart=%d uStart=%d uEnd=%d rEnd=%d",
			rStart, uStart, uEnd, rEnd)
	}

	// Verify READY slot 15: reserved 7000..7500ms, usable 7050..7450ms
	rStart, uStart, uEnd, rEnd, err = scheduler.ReadyGeometry(15, 0)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if rStart != 7000 || uStart != 7050 || uEnd != 7450 || rEnd != 7500 {
		t.Errorf("ready slot 15 miscalculated: rStart=%d uStart=%d uEnd=%d rEnd=%d",
			rStart, uStart, uEnd, rEnd)
	}
	if rEnd != scheduler.TotalReadyRegionMs {
		t.Errorf("expected 15 ready slots to span exactly %d ms, got %d ms",
			scheduler.TotalReadyRegionMs, rEnd)
	}

	// Out of bounds
	if _, _, _, _, err := scheduler.ReadyGeometry(0, 0); err == nil {
		t.Errorf("expected error for slot 0")
	}
	if _, _, _, _, err := scheduler.ReadyGeometry(16, 0); err == nil {
		t.Errorf("expected error for slot 16")
	}
}

func TestScheduleValidate(t *testing.T) {
	now := time.Now().UTC()
	validSlots := []scheduler.SlotConfig{
		{NodeID: 1, SlotID: 1, OffsetMs: 50, DurationMs: 500},
		{NodeID: 2, SlotID: 2, OffsetMs: 650, DurationMs: 500},
	}

	s := &scheduler.Schedule{
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
		Slots:                  validSlots,
		AffectedNodeSet:        []uint8{1, 2},
	}

	if err := s.Validate(); err != nil {
		t.Fatalf("valid schedule failed validation: %v", err)
	}

	// Test invalid profile
	sInvalid := *s
	sInvalid.ProfileID = "INVALID_PROFILE"
	if err := sInvalid.Validate(); err == nil {
		t.Errorf("expected error for invalid profile")
	}

	// Test invalid superframe duration
	sInvalid = *s
	sInvalid.SuperframeMs = 10000
	if err := sInvalid.Validate(); err == nil {
		t.Errorf("expected error for non-9000ms superframe")
	}

	// Test slot ID != node ID
	sInvalid = *s
	sInvalid.Slots = []scheduler.SlotConfig{
		{NodeID: 1, SlotID: 2, OffsetMs: 50, DurationMs: 500},
	}
	if err := sInvalid.Validate(); err == nil {
		t.Errorf("expected error when slot_id != node_id")
	}

	// Test duplicate node ID
	sInvalid = *s
	sInvalid.Slots = []scheduler.SlotConfig{
		{NodeID: 1, SlotID: 1, OffsetMs: 50, DurationMs: 500},
		{NodeID: 1, SlotID: 1, OffsetMs: 50, DurationMs: 500},
	}
	if err := sInvalid.Validate(); err == nil {
		t.Errorf("expected error for duplicate node ID")
	}

	// Test misaligned offset
	sInvalid = *s
	sInvalid.Slots = []scheduler.SlotConfig{
		{NodeID: 1, SlotID: 1, OffsetMs: 100, DurationMs: 500}, // Should be 50
	}
	if err := sInvalid.Validate(); err == nil {
		t.Errorf("expected error for misaligned offset")
	}

	// Test expiry ordering
	sInvalid = *s
	sInvalid.ExpiresAt = now.Add(-1 * time.Minute)
	if err := sInvalid.Validate(); err == nil {
		t.Errorf("expected error when created_at >= expires_at")
	}
}
