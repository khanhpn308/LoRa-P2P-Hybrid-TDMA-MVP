package mqtt_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockStatusStorage struct {
	records   map[string]*domain.GatewayStatusRecord
	upsertErr error
}

func newMockStatusStorage() *mockStatusStorage {
	return &mockStatusStorage{
		records: make(map[string]*domain.GatewayStatusRecord),
	}
}

func (m *mockStatusStorage) UpsertGatewayStatus(ctx context.Context, status *domain.GatewayStatusRecord) error {
	if m.upsertErr != nil {
		return m.upsertErr
	}
	m.records[status.GatewayID] = status
	return nil
}

func (m *mockStatusStorage) GetGatewayStatus(ctx context.Context, gatewayID string) (*domain.GatewayStatusRecord, error) {
	rec, ok := m.records[gatewayID]
	if !ok {
		return nil, storage.ErrGatewayStatusNotFound
	}
	return rec, nil
}

func (m *mockStatusStorage) ListNodes(ctx context.Context, filter domain.NodeFilter) (*domain.NodePage, error) {
	return &domain.NodePage{
		Items:      nil,
		NextCursor: nil,
	}, nil
}

func (m *mockStatusStorage) ListGateways(ctx context.Context) ([]*domain.GatewayItem, error) {
	return nil, nil
}

func (m *mockStatusStorage) CreateGateway(ctx context.Context, gatewayID, name, location, ipAddress string) error {
	return nil
}

func validStatusPayload(gwID string) (string, []byte) {
	epoch := "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
	seq := "100"
	eventID := fmt.Sprintf("%s:%s:%s", gwID, epoch, seq)
	now := time.Now().UTC().Format(time.RFC3339Nano)
	ch := "CH03"
	pending := uint8(2)
	dropped := "5"

	payload := mqtt.StatusEventPayload{
		SchemaVersion:         "1.0-draft",
		EventID:               eventID,
		GatewayID:             gwID,
		GatewayEpoch:          epoch,
		EventSeq:              seq,
		ObservedAt:            &now,
		ObservedTimeSource:    "gateway_utc",
		RadioRxMonotonicUS:    "123456789",
		Buffered:              false,
		ActiveScheduleVersion: 4,
		Mode:                  "ACTIVE",
		RFDutyPermille:        50,
		FreeHeapBytes:         180000,
		OfflineQueueCount:     0,
		OfflineDroppedAlert:   "0",
		NodeCount:             3,
		PendingEventCount:     &pending,
		DroppedEventCount:     &dropped,
		ChannelID:             &ch,
	}

	raw, _ := json.Marshal(payload)
	topic := fmt.Sprintf("iot/v1/gw/%s/uplink/status", gwID)
	return topic, raw
}

func TestStatusConsumer_ProcessSync_Table(t *testing.T) {
	ctx := context.Background()

	tests := []struct {
		name          string
		topic         string
		authPrincipal string
		payloadMod    func(p *mqtt.StatusEventPayload)
		rawJSON       string
		wantErr       bool
		errCheck      func(err error) bool
	}{
		{
			name:          "successful valid status ingest",
			authPrincipal: "gw-alpha",
			wantErr:       false,
		},
		{
			name:          "invalid topic namespace",
			topic:         "iot/v1/gw/gw-alpha/invalid/status",
			authPrincipal: "gw-alpha",
			wantErr:       true,
			errCheck: func(err error) bool {
				return errors.Is(err, mqtt.ErrInvalidStatusTopicNamespace)
			},
		},
		{
			name:          "principal mismatch with topic",
			authPrincipal: "gw-bravo",
			wantErr:       true,
			errCheck: func(err error) bool {
				return errors.Is(err, mqtt.ErrUnauthorizedPrincipal)
			},
		},
		{
			name:          "principal mismatch with payload",
			authPrincipal: "gw-alpha",
			payloadMod: func(p *mqtt.StatusEventPayload) {
				p.GatewayID = "gw-bravo"
			},
			wantErr: true,
			errCheck: func(err error) bool {
				return errors.Is(err, mqtt.ErrUnauthorizedPrincipal)
			},
		},
		{
			name:          "malformed JSON payload",
			authPrincipal: "gw-alpha",
			rawJSON:       "{not-valid-json",
			wantErr:       true,
		},
		{
			name:          "unsupported schema version",
			authPrincipal: "gw-alpha",
			payloadMod: func(p *mqtt.StatusEventPayload) {
				p.SchemaVersion = "2.0"
			},
			wantErr: true,
			errCheck: func(err error) bool {
				return errors.Is(err, mqtt.ErrUnsupportedSchemaVersion)
			},
		},
		{
			name:          "event_id component mismatch",
			authPrincipal: "gw-alpha",
			payloadMod: func(p *mqtt.StatusEventPayload) {
				p.EventID = "gw-alpha:a1b2c3d4-e5f6-7890-abcd-ef1234567890:999"
			},
			wantErr: true,
			errCheck: func(err error) bool {
				return errors.Is(err, mqtt.ErrInvalidStatusPayload)
			},
		},
		{
			name:          "invalid mode enum",
			authPrincipal: "gw-alpha",
			payloadMod: func(p *mqtt.StatusEventPayload) {
				p.Mode = "INVALID_MODE"
			},
			wantErr: true,
			errCheck: func(err error) bool {
				return errors.Is(err, domain.ErrInvalidGatewayMode)
			},
		},
		{
			name:          "unknown time source with non-null timestamp",
			authPrincipal: "gw-alpha",
			payloadMod: func(p *mqtt.StatusEventPayload) {
				p.ObservedTimeSource = "unknown"
				ts := time.Now().UTC().Format(time.RFC3339)
				p.ObservedAt = &ts
			},
			wantErr: true,
			errCheck: func(err error) bool {
				return errors.Is(err, mqtt.ErrInvalidStatusPayload)
			},
		},
		{
			name:          "valid unknown time source with null timestamp",
			authPrincipal: "gw-alpha",
			payloadMod: func(p *mqtt.StatusEventPayload) {
				p.ObservedTimeSource = "unknown"
				p.ObservedAt = nil
			},
			wantErr: false,
		},
		{
			name:          "invalid channel id",
			authPrincipal: "gw-alpha",
			payloadMod: func(p *mqtt.StatusEventPayload) {
				badCh := "CH99"
				p.ChannelID = &badCh
			},
			wantErr: true,
			errCheck: func(err error) bool {
				return errors.Is(err, domain.ErrInvalidChannelID)
			},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			store := newMockStatusStorage()
			consumer := mqtt.NewStatusConsumer(store, mqtt.StatusConsumerConfig{
				WorkerCount: 2,
				QueueDepth:  10,
			})
			defer consumer.Close()

			defaultTopic, rawPayload := validStatusPayload("gw-alpha")
			topic := defaultTopic
			if tc.topic != "" {
				topic = tc.topic
			}

			if tc.rawJSON != "" {
				rawPayload = []byte(tc.rawJSON)
			} else if tc.payloadMod != nil {
				var wire mqtt.StatusEventPayload
				_ = json.Unmarshal(rawPayload, &wire)
				tc.payloadMod(&wire)
				rawPayload, _ = json.Marshal(wire)
			}

			msg := mqtt.IngestMessage{
				Topic:         topic,
				AuthPrincipal: tc.authPrincipal,
				Payload:       rawPayload,
			}

			err := consumer.ProcessSync(ctx, msg)
			if (err != nil) != tc.wantErr {
				t.Fatalf("expected wantErr=%v, got: %v", tc.wantErr, err)
			}
			if tc.errCheck != nil && !tc.errCheck(err) {
				t.Fatalf("error failed errCheck: %v", err)
			}

			if !tc.wantErr {
				rec, err := store.GetGatewayStatus(ctx, "gw-alpha")
				if err != nil {
					t.Fatalf("expected stored record, got: %v", err)
				}
				if rec.GatewayID != "gw-alpha" {
					t.Fatalf("unexpected stored gateway_id: %s", rec.GatewayID)
				}
			}
		})
	}
}

func TestStatusConsumer_AsyncWorker(t *testing.T) {
	ctx := context.Background()
	store := newMockStatusStorage()
	consumer := mqtt.NewStatusConsumer(store, mqtt.StatusConsumerConfig{
		WorkerCount: 2,
		QueueDepth:  10,
	})
	defer consumer.Close()

	topic, payload := validStatusPayload("gw-async")
	resChan := make(chan error, 1)

	msg := mqtt.IngestMessage{
		Topic:         topic,
		AuthPrincipal: "gw-async",
		Payload:       payload,
		ResultChan:    resChan,
	}

	if err := consumer.Submit(ctx, msg); err != nil {
		t.Fatalf("Submit failed: %v", err)
	}

	select {
	case err := <-resChan:
		if err != nil {
			t.Fatalf("async worker failed: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("timed out waiting for async worker")
	}

	rec, err := store.GetGatewayStatus(ctx, "gw-async")
	if err != nil {
		t.Fatalf("expected stored record, got: %v", err)
	}
	if rec.GatewayID != "gw-async" {
		t.Fatalf("unexpected gateway_id: %s", rec.GatewayID)
	}
}
