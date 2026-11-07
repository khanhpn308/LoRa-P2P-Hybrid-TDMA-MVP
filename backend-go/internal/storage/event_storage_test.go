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
	if evt.NodeID != 1 || evt.Data.EventRef != 1 {
		t.Fatalf("unexpected node or event ref: node=%d, event_ref=%d", evt.NodeID, evt.Data.EventRef)
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

func TestListEvents_Success(t *testing.T) {
	db := initMockDB("events_ok")
	repo := storage.NewPostgresEventStorage(db)

	events, nextCursor, err := repo.ListEvents(context.Background(), 0, 50)
	if err != nil {
		t.Fatalf("expected successful ListEvents, got: %v", err)
	}
	if len(events) != 2 {
		t.Fatalf("expected 2 events, got %d", len(events))
	}
	if nextCursor != 0 {
		t.Fatalf("expected nextCursor=0 when less than limit, got %d", nextCursor)
	}
	if events[0].ID != 102 || events[1].ID != 101 {
		t.Fatalf("unexpected events returned: %+v", events)
	}
}

func TestAcknowledgeEvent_Success(t *testing.T) {
	db := initMockDB("ack_ok")
	repo := storage.NewPostgresEventStorage(db)

	evt, err := repo.AcknowledgeEvent(context.Background(), 101, "operator1")
	if err != nil {
		t.Fatalf("expected successful AcknowledgeEvent, got: %v", err)
	}
	if evt.AckStatus != domain.AckStatusAcknowledged {
		t.Fatalf("expected AckStatus=ACKNOWLEDGED, got %s", evt.AckStatus)
	}
	if evt.AcknowledgedBy == nil || *evt.AcknowledgedBy != "operator1" {
		t.Fatalf("expected AcknowledgedBy=operator1, got %v", evt.AcknowledgedBy)
	}
}

func TestAcknowledgeEvent_AlreadyAcknowledged(t *testing.T) {
	db := initMockDB("ack_already_acked")
	repo := storage.NewPostgresEventStorage(db)

	_, err := repo.AcknowledgeEvent(context.Background(), 101, "operator1")
	if !errors.Is(err, storage.ErrAlreadyAcknowledged) {
		t.Fatalf("expected ErrAlreadyAcknowledged, got: %v", err)
	}
}

func TestAcknowledgeEvent_NotFound(t *testing.T) {
	db := initMockDB("ack_not_found")
	repo := storage.NewPostgresEventStorage(db)

	_, err := repo.AcknowledgeEvent(context.Background(), 999, "operator1")
	if !errors.Is(err, storage.ErrEventNotFound) {
		t.Fatalf("expected ErrEventNotFound, got: %v", err)
	}
}

func TestListNodeHealth_Success(t *testing.T) {
	db := initMockDB("node_health_ok")
	repo := storage.NewPostgresEventStorage(db)

	nodes, err := repo.ListNodeHealth(context.Background(), "gw01", 50)
	if err != nil {
		t.Fatalf("expected successful ListNodeHealth, got: %v", err)
	}
	if len(nodes) != 2 {
		t.Fatalf("expected 2 nodes, got %d", len(nodes))
	}
	if nodes[0].NodeID != 1 || nodes[1].NodeID != 2 {
		t.Fatalf("unexpected nodes returned: %+v", nodes)
	}
}
