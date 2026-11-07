package mqtt_test

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockEventRepository struct {
	mu           sync.Mutex
	recorded     map[string]*domain.Event
	quarantined  []*storage.QuarantineRecord
	recordResult *storage.EventRecordResult
	recordErr    error
}

func newMockEventRepository() *mockEventRepository {
	return &mockEventRepository{
		recorded: make(map[string]*domain.Event),
	}
}

func (m *mockEventRepository) RecordEvent(ctx context.Context, event *domain.Event) (*storage.EventRecordResult, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.recordErr != nil {
		return nil, m.recordErr
	}

	key := event.GatewayID + ":" + event.EventID
	if existing, found := m.recorded[key]; found {
		h1 := existing.ComputePayloadSHA256()
		h2 := event.ComputePayloadSHA256()
		if h1 == h2 {
			return &storage.EventRecordResult{
				EventID:     100,
				IsDuplicate: true,
				Status:      "DEDUPLICATED",
			}, nil
		}
		return nil, storage.ErrConflictingPayload
	}

	m.recorded[key] = event
	return &storage.EventRecordResult{
		EventID:     101,
		IsDuplicate: false,
		Status:      "INSERTED",
	}, nil
}

func (m *mockEventRepository) GetEvent(ctx context.Context, gatewayID, eventID string) (*domain.Event, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	key := gatewayID + ":" + eventID
	if evt, ok := m.recorded[key]; ok {
		return evt, nil
	}
	return nil, storage.ErrEventNotFound
}

func (m *mockEventRepository) QuarantineEvent(ctx context.Context, q *storage.QuarantineRecord) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.quarantined = append(m.quarantined, q)
	return nil
}

func (m *mockEventRepository) RecordHealthUpdate(ctx context.Context, h *domain.NodeHealth) error {
	return nil
}

func (m *mockEventRepository) GetNodeHealth(ctx context.Context, gatewayID string, nodeID uint8) (*domain.NodeHealth, error) {
	return nil, storage.ErrHealthNotFound
}

func makeValidWirePayload() []byte {
	nowStr := time.Date(2026, 11, 7, 12, 0, 0, 0, time.UTC).Format(time.RFC3339)
	payload := mqtt.AlertEventPayload{
		SchemaVersion:      "1.0-draft",
		EventID:            "gw01:550e8400-e29b-41d4-a716-446655440000:42",
		GatewayID:          "gw01",
		GatewayEpoch:       "550e8400-e29b-41d4-a716-446655440000",
		EventSeq:           "42",
		ObservedAt:         &nowStr,
		ObservedTimeSource: "gateway_utc",
		RadioRxMonotonicUS: "987654321",
		Buffered:           false,
		NodeID:             1,
		SuperframeSeq:      10,
		SeqNum:             2,
		ScheduleVersion:    1,
		Severity:           "P1_HIGH",
		Data: mqtt.AlertDataPayload{
			SlotID:           1,
			SensorStatusMask: 0,
			Ch1Raw:           2000,
			Ch2Raw:           100,
			Ch3Raw:           50,
			BatteryMv:        3300,
			NodeDutyPermille: 5,
		},
		Trigger: &mqtt.AlertTriggerPayload{
			Channel:      1,
			ObservedRaw:  2000,
			ThresholdRaw: 1800,
		},
		RadioAckSent: true,
	}

	data, _ := json.Marshal(payload)
	return data
}

func TestEventConsumer_ValidFirstEvent(t *testing.T) {
	repo := newMockEventRepository()
	consumer := mqtt.NewEventConsumer(repo, mqtt.EventConsumerConfig{WorkerCount: 2, QueueDepth: 10})
	defer consumer.Close()

	msg := mqtt.IngestMessage{
		Topic:         "iot/v1/gw/gw01/uplink/alert",
		AuthPrincipal: "gw01",
		Payload:       makeValidWirePayload(),
	}

	err := consumer.ProcessSync(context.Background(), msg)
	if err != nil {
		t.Fatalf("expected successful ingestion, got: %v", err)
	}

	if len(repo.recorded) != 1 {
		t.Fatalf("expected 1 recorded event, got %d", len(repo.recorded))
	}
}

func TestEventConsumer_IdempotentExactDuplicate(t *testing.T) {
	repo := newMockEventRepository()
	consumer := mqtt.NewEventConsumer(repo, mqtt.EventConsumerConfig{WorkerCount: 2, QueueDepth: 10})
	defer consumer.Close()

	msg := mqtt.IngestMessage{
		Topic:         "iot/v1/gw/gw01/uplink/alert",
		AuthPrincipal: "gw01",
		Payload:       makeValidWirePayload(),
	}

	// First delivery
	if err := consumer.ProcessSync(context.Background(), msg); err != nil {
		t.Fatalf("first delivery failed: %v", err)
	}

	// QoS 1 duplicate delivery
	if err := consumer.ProcessSync(context.Background(), msg); err != nil {
		t.Fatalf("duplicate delivery should succeed idempotently, got: %v", err)
	}

	if len(repo.recorded) != 1 {
		t.Fatalf("duplicate must not create additional business record, got %d", len(repo.recorded))
	}
}

func TestEventConsumer_ConflictingPayloadDetected(t *testing.T) {
	repo := newMockEventRepository()
	consumer := mqtt.NewEventConsumer(repo, mqtt.EventConsumerConfig{WorkerCount: 2, QueueDepth: 10})
	defer consumer.Close()

	payload1 := makeValidWirePayload()
	msg1 := mqtt.IngestMessage{
		Topic:         "iot/v1/gw/gw01/uplink/alert",
		AuthPrincipal: "gw01",
		Payload:       payload1,
	}

	if err := consumer.ProcessSync(context.Background(), msg1); err != nil {
		t.Fatalf("first delivery failed: %v", err)
	}

	// Change payload business metric under same event_id
	var wire mqtt.AlertEventPayload
	_ = json.Unmarshal(payload1, &wire)
	wire.Data.Ch1Raw = 9999
	payload2, _ := json.Marshal(wire)

	msg2 := mqtt.IngestMessage{
		Topic:         "iot/v1/gw/gw01/uplink/alert",
		AuthPrincipal: "gw01",
		Payload:       payload2,
	}

	err := consumer.ProcessSync(context.Background(), msg2)
	if !errors.Is(err, storage.ErrConflictingPayload) {
		t.Fatalf("expected ErrConflictingPayload, got: %v", err)
	}
}

func TestEventConsumer_UnauthorizedGatewayPrincipal(t *testing.T) {
	repo := newMockEventRepository()
	consumer := mqtt.NewEventConsumer(repo, mqtt.EventConsumerConfig{WorkerCount: 2, QueueDepth: 10})
	defer consumer.Close()

	msg := mqtt.IngestMessage{
		Topic:         "iot/v1/gw/gw01/uplink/alert",
		AuthPrincipal: "gw-attacker", // Spoofing attempt
		Payload:       makeValidWirePayload(),
	}

	err := consumer.ProcessSync(context.Background(), msg)
	if !errors.Is(err, mqtt.ErrUnauthorizedPrincipal) {
		t.Fatalf("expected ErrUnauthorizedPrincipal, got: %v", err)
	}

	if len(repo.quarantined) != 1 {
		t.Fatalf("expected spoofing attempt to be quarantined")
	}
	if repo.quarantined[0].ConflictReason != "UNAUTHORIZED_GATEWAY_NODE" {
		t.Fatalf("unexpected conflict reason: %s", repo.quarantined[0].ConflictReason)
	}
}

func TestEventConsumer_InvalidTopicNamespace(t *testing.T) {
	repo := newMockEventRepository()
	consumer := mqtt.NewEventConsumer(repo, mqtt.EventConsumerConfig{WorkerCount: 2, QueueDepth: 10})
	defer consumer.Close()

	msg := mqtt.IngestMessage{
		Topic:         "invalid/namespace/topic",
		AuthPrincipal: "gw01",
		Payload:       makeValidWirePayload(),
	}

	err := consumer.ProcessSync(context.Background(), msg)
	if !errors.Is(err, mqtt.ErrInvalidTopicNamespace) {
		t.Fatalf("expected ErrInvalidTopicNamespace, got: %v", err)
	}
}

func TestEventConsumer_UnsupportedSchemaVersion(t *testing.T) {
	repo := newMockEventRepository()
	consumer := mqtt.NewEventConsumer(repo, mqtt.EventConsumerConfig{WorkerCount: 2, QueueDepth: 10})
	defer consumer.Close()

	var wire mqtt.AlertEventPayload
	_ = json.Unmarshal(makeValidWirePayload(), &wire)
	wire.SchemaVersion = "2.0-unapproved"
	payload, _ := json.Marshal(wire)

	msg := mqtt.IngestMessage{
		Topic:         "iot/v1/gw/gw01/uplink/alert",
		AuthPrincipal: "gw01",
		Payload:       payload,
	}

	err := consumer.ProcessSync(context.Background(), msg)
	if !errors.Is(err, mqtt.ErrUnsupportedSchemaVersion) {
		t.Fatalf("expected ErrUnsupportedSchemaVersion, got: %v", err)
	}
}

func TestEventConsumer_QueueBackpressure(t *testing.T) {
	repo := newMockEventRepository()
	// Consumer with small queue
	consumer := mqtt.NewEventConsumer(repo, mqtt.EventConsumerConfig{WorkerCount: 1, QueueDepth: 2})
	defer consumer.Close()

	msg := mqtt.IngestMessage{
		Topic:         "iot/v1/gw/gw01/uplink/alert",
		AuthPrincipal: "gw01",
		Payload:       makeValidWirePayload(),
	}

	// Submit multiple messages rapidly to verify submit mechanism
	for i := 0; i < 5; i++ {
		_ = consumer.Submit(context.Background(), msg)
	}
}
