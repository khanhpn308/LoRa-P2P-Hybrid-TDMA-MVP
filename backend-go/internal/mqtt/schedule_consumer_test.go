package mqtt_test

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

func setupTestLifecycleEngine(t *testing.T) (*scheduler.LifecycleEngine, *scheduler.MemoryScheduleRepository, *scheduler.Schedule) {
	repo := scheduler.NewMemoryScheduleRepository()
	validator := scheduler.NewFeasibilityValidator(nil)
	planner := scheduler.NewPlanner(validator)

	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate ed25519 key: %v", err)
	}

	nodeKeys := map[uint8][]byte{
		1: []byte("node-1-key-thirty-two-bytes-1234"),
		2: []byte("node-2-key-thirty-two-bytes-1234"),
	}
	keyDir := scheduler.NewMapNodeKeyDirectory(nodeKeys)
	signer, err := scheduler.NewScheduleSigner(priv, keyDir)
	if err != nil {
		t.Fatalf("failed to create signer: %v", err)
	}

	engine := scheduler.NewLifecycleEngine(repo, signer, planner)

	// Save an initial proposed schedule
	sched := validSchedule(time.Now().UTC())
	if err := repo.SaveSchedule(context.Background(), sched); err != nil {
		t.Fatalf("failed to save setup schedule: %v", err)
	}

	return engine, repo, sched
}

func buildAckPayload(stage string, reasonCode string, activateSeq *uint32, activatedSeq *uint32) mqtt.ScheduleAckPayload {
	epoch := "550e8400-e29b-41d4-a716-446655440000"
	seq := "101"
	eventID := "gw01:" + epoch + ":" + seq
	nowStr := time.Now().UTC().Format(time.RFC3339)

	return mqtt.ScheduleAckPayload{
		SchemaVersion:            scheduler.DefaultSchemaVersion,
		EventID:                  eventID,
		GatewayID:                "gw01",
		GatewayEpoch:             epoch,
		EventSeq:                 seq,
		ObservedAt:               &nowStr,
		ObservedTimeSource:       "gateway_utc",
		RadioRxMonotonicUS:       "1234567890",
		Buffered:                 false,
		RequestID:                "550e8400-e29b-41d4-a716-446655440000",
		ScheduleID:               "100",
		ScheduleVersion:          1,
		Stage:                    stage,
		ActivateAtSuperframeSeq:  activateSeq,
		ActivatedAtSuperframeSeq: activatedSeq,
		ReasonCode:               reasonCode,
	}
}

func TestNewScheduleAckConsumer(t *testing.T) {
	t.Run("nil engine returns error", func(t *testing.T) {
		c, err := mqtt.NewScheduleAckConsumer(nil)
		if !errors.Is(err, mqtt.ErrNilLifecycleEngine) {
			t.Fatalf("expected ErrNilLifecycleEngine, got: %v", err)
		}
		if c != nil {
			t.Fatal("expected nil consumer")
		}
	})

	t.Run("valid engine success", func(t *testing.T) {
		engine, _, _ := setupTestLifecycleEngine(t)
		c, err := mqtt.NewScheduleAckConsumer(engine)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if c == nil {
			t.Fatal("expected non-nil consumer")
		}
	})
}

func TestScheduleAckConsumer_HandleMessage_Table(t *testing.T) {
	seq42 := uint32(42)
	seq100 := uint32(100)

	tests := []struct {
		name          string
		topic         string
		payloadFn     func() []byte
		wantErr       bool
		expectedErr   error
		checkSchedule func(t *testing.T, repo *scheduler.MemoryScheduleRepository)
	}{
		{
			name:  "success STAGE_ACK does not promote to ACTIVE",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("STAGE_ACK", "NONE", &seq42, nil)
				b, _ := json.Marshal(p)
				return b
			},
			wantErr: false,
			checkSchedule: func(t *testing.T, repo *scheduler.MemoryScheduleRepository) {
				act, err := repo.GetActiveScheduleByGateway(context.Background(), "gw01")
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				if act != nil {
					t.Fatalf("STAGE_ACK must NEVER promote schedule to ACTIVE, got: %+v", act)
				}
			},
		},
		{
			name:  "success ACTIVE_REPORT promotes schedule to ACTIVE",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("ACTIVE_REPORT", "NONE", &seq42, &seq42)
				b, _ := json.Marshal(p)
				return b
			},
			wantErr: false,
			checkSchedule: func(t *testing.T, repo *scheduler.MemoryScheduleRepository) {
				act, err := repo.GetActiveScheduleByGateway(context.Background(), "gw01")
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				if act == nil {
					t.Fatal("expected active schedule after ACTIVE_REPORT")
				}
				if act.ScheduleID != "100" || act.SuperframeSeq != 42 {
					t.Errorf("unexpected active schedule: %+v", act)
				}
			},
		},
		{
			name:  "duplicate ACTIVE_REPORT handled idempotently",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("ACTIVE_REPORT", "NONE", &seq42, &seq42)
				b, _ := json.Marshal(p)
				return b
			},
			wantErr: false,
		},
		{
			name:  "VERIFY_NACK reports gateway rejection",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("VERIFY_NACK", "AIRTIME_LIMIT", nil, nil)
				b, _ := json.Marshal(p)
				return b
			},
			wantErr: true,
			checkSchedule: func(t *testing.T, repo *scheduler.MemoryScheduleRepository) {
				act, _ := repo.GetActiveScheduleByGateway(context.Background(), "gw01")
				if act != nil && act.ScheduleID == "999" {
					t.Fatal("VERIFY_NACK must not activate schedule")
				}
			},
		},
		{
			name:  "malformed topic format",
			topic: "iot/v1/gw/gw01/invalid/topic",
			payloadFn: func() []byte {
				p := buildAckPayload("STAGE_ACK", "NONE", &seq42, nil)
				b, _ := json.Marshal(p)
				return b
			},
			wantErr:     true,
			expectedErr: mqtt.ErrMalformedScheduleAckTopic,
		},
		{
			name:  "malformed json payload",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				return []byte("{invalid-json")
			},
			wantErr:     true,
			expectedErr: mqtt.ErrInvalidAckPayload,
		},
		{
			name:  "unsupported schema_version",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("STAGE_ACK", "NONE", &seq42, nil)
				p.SchemaVersion = "2.0-unsupported"
				b, _ := json.Marshal(p)
				return b
			},
			wantErr:     true,
			expectedErr: mqtt.ErrUnsupportedSchemaVersion,
		},
		{
			name:  "gateway_id mismatch between topic and payload",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("STAGE_ACK", "NONE", &seq42, nil)
				p.GatewayID = "gw-other"
				p.EventID = "gw-other:" + p.GatewayEpoch + ":" + p.EventSeq
				b, _ := json.Marshal(p)
				return b
			},
			wantErr:     true,
			expectedErr: mqtt.ErrIdentityMismatch,
		},
		{
			name:  "semantic event_id mismatch",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("STAGE_ACK", "NONE", &seq42, nil)
				p.EventID = "mismatched-event-id"
				b, _ := json.Marshal(p)
				return b
			},
			wantErr:     true,
			expectedErr: mqtt.ErrEventIDSemanticMismatch,
		},
		{
			name:  "STAGE_ACK with error reason_code rejected",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("STAGE_ACK", "BAD_AUTH", &seq42, nil)
				b, _ := json.Marshal(p)
				return b
			},
			wantErr:     true,
			expectedErr: mqtt.ErrStageReasonMismatch,
		},
		{
			name:  "VERIFY_NACK with NONE reason_code rejected",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("VERIFY_NACK", "NONE", nil, nil)
				b, _ := json.Marshal(p)
				return b
			},
			wantErr:     true,
			expectedErr: mqtt.ErrStageReasonMismatch,
		},
		{
			name:  "ACTIVE_REPORT missing activated_at_superframe_seq rejected",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("ACTIVE_REPORT", "NONE", &seq100, nil)
				b, _ := json.Marshal(p)
				return b
			},
			wantErr:     true,
			expectedErr: mqtt.ErrActivatedSeqMismatch,
		},
		{
			name:  "STAGE_ACK with non-null activated_at_superframe_seq rejected",
			topic: "iot/v1/gw/gw01/uplink/schedule-ack",
			payloadFn: func() []byte {
				p := buildAckPayload("STAGE_ACK", "NONE", &seq42, &seq42)
				b, _ := json.Marshal(p)
				return b
			},
			wantErr:     true,
			expectedErr: mqtt.ErrActivatedSeqMismatch,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			engine, repo, _ := setupTestLifecycleEngine(t)
			consumer, err := mqtt.NewScheduleAckConsumer(engine)
			if err != nil {
				t.Fatalf("failed to create consumer: %v", err)
			}

			payloadBytes := tt.payloadFn()
			err = consumer.HandleMessage(context.Background(), tt.topic, payloadBytes)
			if (err != nil) != tt.wantErr {
				t.Fatalf("HandleMessage() error = %v, wantErr %v", err, tt.wantErr)
			}
			if tt.expectedErr != nil && !errors.Is(err, tt.expectedErr) {
				t.Fatalf("expected error %v, got: %v", tt.expectedErr, err)
			}
			if tt.checkSchedule != nil {
				tt.checkSchedule(t, repo)
			}
		})
	}
}
