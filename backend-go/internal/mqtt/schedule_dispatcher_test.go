package mqtt_test

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

type mockMQTTPublisher struct {
	lastTopic          string
	lastQoS            byte
	lastRetain         bool
	lastExpiryInterval uint32
	lastPayload        []byte
	publishErr         error
}

func (m *mockMQTTPublisher) Publish(ctx context.Context, topic string, qos byte, retain bool, expiryInterval uint32, payload []byte) error {
	if m.publishErr != nil {
		return m.publishErr
	}
	m.lastTopic = topic
	m.lastQoS = qos
	m.lastRetain = retain
	m.lastExpiryInterval = expiryInterval
	m.lastPayload = payload
	return nil
}

func validSchedule(baseTime time.Time) *scheduler.Schedule {
	return &scheduler.Schedule{
		SchemaVersion:          scheduler.DefaultSchemaVersion,
		RequestID:              "550e8400-e29b-41d4-a716-446655440000",
		GatewayID:              "gw01",
		ScheduleID:             "100",
		ScheduleVersion:        1,
		ScheduleGeneration:     1,
		CreatedAt:              baseTime,
		ExpiresAt:              baseTime.Add(3600 * time.Second),
		ProfileID:              scheduler.ProfileV2VN920Static15N,
		SuperframeMs:           9000,
		MinAnnounceSuperframes: 3,
		ChannelID:              "CH00",
		NetworkID:              1,
		Slots: []scheduler.SlotConfig{
			{NodeID: 1, SlotID: 1, OffsetMs: 50, DurationMs: 500},
			{NodeID: 2, SlotID: 2, OffsetMs: 650, DurationMs: 500},
		},
		AffectedNodeSet: []uint8{1, 2},
	}
}

func TestNewScheduleDispatcher(t *testing.T) {
	t.Run("nil publisher returns error", func(t *testing.T) {
		d, err := mqtt.NewScheduleDispatcher(nil)
		if !errors.Is(err, mqtt.ErrNilPublisher) {
			t.Fatalf("expected ErrNilPublisher, got: %v", err)
		}
		if d != nil {
			t.Fatal("expected nil dispatcher")
		}
	})

	t.Run("valid publisher success", func(t *testing.T) {
		pub := &mockMQTTPublisher{}
		d, err := mqtt.NewScheduleDispatcher(pub)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if d == nil {
			t.Fatal("expected non-nil dispatcher")
		}
	})
}

func TestScheduleDispatcher_DispatchSchedule_Table(t *testing.T) {
	now := time.Date(2026, 11, 8, 12, 0, 0, 0, time.UTC)

	tests := []struct {
		name                 string
		sched                func() *scheduler.Schedule
		nowTime              time.Time
		publishErr           error
		wantErr              bool
		expectedErr          error
		expectedTopic        string
		expectedQoS          byte
		expectedRetain       bool
		minExpectedExpirySec uint32
	}{
		{
			name: "success standard dispatch",
			sched: func() *scheduler.Schedule {
				return validSchedule(now)
			},
			nowTime:              now,
			wantErr:              false,
			expectedTopic:        "iot/v1/gw/gw01/downlink/schedule",
			expectedQoS:          1,
			expectedRetain:       false,
			minExpectedExpirySec: 3600,
		},
		{
			name:        "nil schedule returns error",
			sched:       func() *scheduler.Schedule { return nil },
			nowTime:     now,
			wantErr:     true,
			expectedErr: mqtt.ErrNilScheduleToDispatch,
		},
		{
			name: "expired schedule returns ErrScheduleExpired",
			sched: func() *scheduler.Schedule {
				s := validSchedule(now.Add(-30 * time.Second))
				s.ExpiresAt = now.Add(-10 * time.Second)
				return s
			},
			nowTime:     now,
			wantErr:     true,
			expectedErr: mqtt.ErrScheduleExpired,
		},
		{
			name: "less than 1s remaining returns ErrScheduleExpired",
			sched: func() *scheduler.Schedule {
				s := validSchedule(now)
				s.ExpiresAt = now.Add(500 * time.Millisecond)
				return s
			},
			nowTime:     now,
			wantErr:     true,
			expectedErr: mqtt.ErrScheduleExpired,
		},
		{
			name: "invalid gateway id returns error",
			sched: func() *scheduler.Schedule {
				s := validSchedule(now)
				s.GatewayID = "invalid/slash/id"
				return s
			},
			nowTime: now,
			wantErr: true,
		},
		{
			name: "invalid schedule invariants returns error",
			sched: func() *scheduler.Schedule {
				s := validSchedule(now)
				s.ProfileID = "UNSUPPORTED_PROFILE"
				return s
			},
			nowTime: now,
			wantErr: true,
		},
		{
			name: "publisher error propagates",
			sched: func() *scheduler.Schedule {
				return validSchedule(now)
			},
			nowTime:    now,
			publishErr: errors.New("mqtt broker offline"),
			wantErr:    true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			pub := &mockMQTTPublisher{publishErr: tt.publishErr}
			disp, err := mqtt.NewScheduleDispatcher(pub)
			if err != nil {
				t.Fatalf("failed to create dispatcher: %v", err)
			}
			disp.SetNowFunc(func() time.Time { return tt.nowTime })

			sched := tt.sched()
			err = disp.DispatchSchedule(context.Background(), sched)
			if (err != nil) != tt.wantErr {
				t.Fatalf("DispatchSchedule() error = %v, wantErr %v", err, tt.wantErr)
			}
			if tt.expectedErr != nil && !errors.Is(err, tt.expectedErr) {
				t.Fatalf("expected error %v, got %v", tt.expectedErr, err)
			}

			if !tt.wantErr {
				if pub.lastTopic != tt.expectedTopic {
					t.Errorf("got topic %s, want %s", pub.lastTopic, tt.expectedTopic)
				}
				if pub.lastQoS != tt.expectedQoS {
					t.Errorf("got QoS %d, want %d", pub.lastQoS, tt.expectedQoS)
				}
				if pub.lastRetain != tt.expectedRetain {
					t.Errorf("got Retain %v, want %v", pub.lastRetain, tt.expectedRetain)
				}
				if pub.lastExpiryInterval < tt.minExpectedExpirySec {
					t.Errorf("got expiry interval %d, want >= %d", pub.lastExpiryInterval, tt.minExpectedExpirySec)
				}

				// Verify payload deserialization against schema
				var payload mqtt.ScheduleDownlinkPayload
				if err := json.Unmarshal(pub.lastPayload, &payload); err != nil {
					t.Fatalf("failed to unmarshal published payload: %v", err)
				}
				if payload.SchemaVersion != "1.0-draft" {
					t.Errorf("unexpected schema_version: %s", payload.SchemaVersion)
				}
				if payload.GatewayID != sched.GatewayID {
					t.Errorf("payload gateway_id %s != %s", payload.GatewayID, sched.GatewayID)
				}
				if payload.ScheduleID != sched.ScheduleID {
					t.Errorf("payload schedule_id %s != %s", payload.ScheduleID, sched.ScheduleID)
				}
				if len(payload.Slots) != len(sched.Slots) {
					t.Errorf("payload slots count %d != %d", len(payload.Slots), len(sched.Slots))
				}
			}
		})
	}
}
