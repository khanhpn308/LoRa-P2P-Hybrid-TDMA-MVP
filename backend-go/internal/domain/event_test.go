package domain_test

import (
	"bytes"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

func validTestEvent() *domain.Event {
	now := time.Date(2026, 11, 7, 12, 0, 0, 0, time.UTC)
	gwID := "gw01"
	epoch := "550e8400-e29b-41d4-a716-446655440000"
	seq := "42"
	eventID := gwID + ":" + epoch + ":" + seq

	return &domain.Event{
		SchemaVersion:      "1.0-draft",
		EventID:            eventID,
		GatewayID:          gwID,
		GatewayEpoch:       epoch,
		EventSeq:           seq,
		NodeID:             1,
		SuperframeSeq:      100,
		SeqNum:             5,
		ScheduleVersion:    1,
		Severity:           domain.SeverityP1High,
		ObservedAt:         &now,
		ObservedTimeSource: domain.TimeSourceGatewayUTC,
		RadioRxMonotonicUS: "123456789",
		Buffered:           false,
		RadioAckSent:       true,
		Data: domain.EventData{
			EventRef:   1,
			EventCode:  1,
			EventValue: 1,
		},
		Trigger: &domain.EventTrigger{
			Channel:      1,
			ObservedRaw:  2500,
			ThresholdRaw: 2000,
		},
		AckStatus: domain.AckStatusUnacknowledged,
	}
}

func TestEvent_Validation_Success(t *testing.T) {
	evt := validTestEvent()
	if err := evt.Validate(); err != nil {
		t.Fatalf("expected valid event, got: %v", err)
	}

	hash1 := evt.ComputePayloadSHA256()
	hash2 := evt.ComputePayloadSHA256()
	if !bytes.Equal(hash1[:], hash2[:]) {
		t.Fatalf("expected deterministic payload hash, got mismatch")
	}
}

func TestEvent_Validation_UnknownTimeSourceWithNull(t *testing.T) {
	evt := validTestEvent()
	evt.ObservedTimeSource = domain.TimeSourceUnknown
	evt.ObservedAt = nil

	if err := evt.Validate(); err != nil {
		t.Fatalf("expected valid event with unknown time and null observed_at, got: %v", err)
	}
}

func TestEvent_Validation_UnknownTimeSourceWithNonNull(t *testing.T) {
	evt := validTestEvent()
	evt.ObservedTimeSource = domain.TimeSourceUnknown
	// evt.ObservedAt is non-nil

	if err := evt.Validate(); err == nil {
		t.Fatalf("expected error for unknown time source with non-null observed_at")
	}
}

func TestEvent_Validation_MissingRadioACK(t *testing.T) {
	evt := validTestEvent()
	evt.RadioAckSent = false

	if err := evt.Validate(); err == nil {
		t.Fatalf("expected error for missing radio_ack_sent")
	}
}

func TestEvent_Validation_InvalidEventID(t *testing.T) {
	evt := validTestEvent()
	evt.EventID = "mismatched:id:123"

	if err := evt.Validate(); err == nil {
		t.Fatalf("expected error for mismatched event_id")
	}
}

func TestEvent_Validation_InvalidNodeID(t *testing.T) {
	evt := validTestEvent()
	evt.NodeID = 0

	if err := evt.Validate(); err == nil {
		t.Fatalf("expected error for node_id=0")
	}

	evt.NodeID = 255
	if err := evt.Validate(); err == nil {
		t.Fatalf("expected error for node_id=255")
	}
}

func TestEvent_ComputePayloadSHA256_DifferentPayloadDiffers(t *testing.T) {
	evt1 := validTestEvent()
	evt2 := validTestEvent()

	hash1 := evt1.ComputePayloadSHA256()

	// Change a business measurement
	evt2.Data.EventValue = 9999
	hash2 := evt2.ComputePayloadSHA256()

	if bytes.Equal(hash1[:], hash2[:]) {
		t.Fatalf("expected different hashes for different payloads, got identical")
	}
}
