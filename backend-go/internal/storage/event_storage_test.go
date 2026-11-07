package storage_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

func validStorageEvent() *domain.Event {
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
			SlotID:           1,
			SensorStatusMask: 0,
			Ch1Raw:           2500,
			Ch2Raw:           500,
			Ch3Raw:           300,
			BatteryMv:        3300,
			NodeDutyPermille: 10,
		},
		Trigger: &domain.EventTrigger{
			Channel:      1,
			ObservedRaw:  2500,
			ThresholdRaw: 2000,
		},
		AckStatus: domain.AckStatusUnacknowledged,
	}
}

func TestRecordEvent_NewEvent(t *testing.T) {
	db := initMockDB("event_new")
	repo := storage.NewPostgresEventStorage(db)

	evt := validStorageEvent()
	res, err := repo.RecordEvent(context.Background(), evt)
	if err != nil {
		t.Fatalf("expected successful insert of new event, got: %v", err)
	}

	if res.IsDuplicate {
		t.Fatalf("expected IsDuplicate=false for new event")
	}
	if res.EventID != 101 {
		t.Fatalf("expected EventID=101, got: %d", res.EventID)
	}
	if res.Status != "INSERTED" {
		t.Fatalf("expected Status=INSERTED, got: %s", res.Status)
	}
}

func TestRecordEvent_IdempotentDuplicate(t *testing.T) {
	db := initMockDB("event_idempotent_duplicate")
	repo := storage.NewPostgresEventStorage(db)

	evt := validStorageEvent()
	res, err := repo.RecordEvent(context.Background(), evt)
	if err != nil {
		t.Fatalf("expected successful duplicate deduplication, got: %v", err)
	}

	if !res.IsDuplicate {
		t.Fatalf("expected IsDuplicate=true for duplicate replay")
	}
	if res.EventID != 42 {
		t.Fatalf("expected existing EventID=42, got: %d", res.EventID)
	}
	if res.Status != "DEDUPLICATED" {
		t.Fatalf("expected Status=DEDUPLICATED, got: %s", res.Status)
	}
}

func TestRecordEvent_ConflictingPayload(t *testing.T) {
	db := initMockDB("event_conflicting_payload")
	repo := storage.NewPostgresEventStorage(db)

	evt := validStorageEvent()
	res, err := repo.RecordEvent(context.Background(), evt)
	if !errors.Is(err, storage.ErrConflictingPayload) {
		t.Fatalf("expected ErrConflictingPayload, got res=%v, err=%v", res, err)
	}
}

func TestGetEvent_Success(t *testing.T) {
	db := initMockDB("event_get_ok")
	repo := storage.NewPostgresEventStorage(db)

	evt, err := repo.GetEvent(context.Background(), "gw01", "gw01:550e8400-e29b-41d4-a716-446655440000:42")
	if err != nil {
		t.Fatalf("expected successful GetEvent, got: %v", err)
	}

	if evt.EventID != "gw01:550e8400-e29b-41d4-a716-446655440000:42" {
		t.Fatalf("unexpected event_id: %s", evt.EventID)
	}
	if evt.NodeID != 1 || evt.Data.SlotID != 1 {
		t.Fatalf("unexpected node or slot ID: node=%d, slot=%d", evt.NodeID, evt.Data.SlotID)
	}
}

func TestGetEvent_NotFound(t *testing.T) {
	db := initMockDB("event_not_found")
	repo := storage.NewPostgresEventStorage(db)

	_, err := repo.GetEvent(context.Background(), "gw01", "nonexistent")
	if !errors.Is(err, storage.ErrEventNotFound) {
		t.Fatalf("expected ErrEventNotFound, got: %v", err)
	}
}

func TestRecordHealthUpdate_Success(t *testing.T) {
	db := initMockDB("health_ok")
	repo := storage.NewPostgresEventStorage(db)

	h := &domain.NodeHealth{
		GatewayID:         "gw01",
		NodeID:            1,
		SessionSel:        1,
		FrameCounter:      100,
		MaintSeq:          10,
		StatusFlags:       0,
		PendingEventCount: 0,
		HealthStatus:      domain.HealthStatusOnline,
	}

	if err := repo.RecordHealthUpdate(context.Background(), h); err != nil {
		t.Fatalf("expected successful RecordHealthUpdate, got: %v", err)
	}
}

func TestGetNodeHealth_Success(t *testing.T) {
	db := initMockDB("health_get_ok")
	repo := storage.NewPostgresEventStorage(db)

	h, err := repo.GetNodeHealth(context.Background(), "gw01", 1)
	if err != nil {
		t.Fatalf("expected successful GetNodeHealth, got: %v", err)
	}

	if h.GatewayID != "gw01" || h.NodeID != 1 {
		t.Fatalf("unexpected health record: %+v", h)
	}
	if h.HealthStatus != domain.HealthStatusOnline {
		t.Fatalf("unexpected health status: %s", h.HealthStatus)
	}
}

func TestGetNodeHealth_NotFound(t *testing.T) {
	db := initMockDB("health_not_found")
	repo := storage.NewPostgresEventStorage(db)

	_, err := repo.GetNodeHealth(context.Background(), "gw01", 99)
	if !errors.Is(err, storage.ErrHealthNotFound) {
		t.Fatalf("expected ErrHealthNotFound, got: %v", err)
	}
}

func TestQuarantineEvent_Success(t *testing.T) {
	db := initMockDB("quarantine_ok")
	repo := storage.NewPostgresEventStorage(db)

	q := &storage.QuarantineRecord{
		GatewayID:         "gw01",
		EventID:           "gw01:550e8400-e29b-41d4-a716-446655440000:42",
		ConflictReason:    "CONFLICTING_PAYLOAD_HASH",
		ExpectedSHA256:    []byte{1, 2, 3},
		ConflictingSHA256: []byte{4, 5, 6},
		RawPayload:        "sample invalid payload",
	}

	if err := repo.QuarantineEvent(context.Background(), q); err != nil {
		t.Fatalf("expected successful quarantine, got: %v", err)
	}
}
