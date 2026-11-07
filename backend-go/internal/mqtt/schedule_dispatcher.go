package mqtt

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

const (
	// TopicSuffixScheduleDownlink is the canonical MQTT 5.0 suffix for schedule dispatch.
	TopicSuffixScheduleDownlink = "/downlink/schedule"
)

var (
	// ErrNilPublisher indicates a nil MQTTPublisher was supplied.
	ErrNilPublisher = errors.New("mqtt publisher cannot be nil")
	// ErrNilScheduleToDispatch indicates a nil schedule was supplied for dispatch.
	ErrNilScheduleToDispatch = errors.New("schedule to dispatch cannot be nil")
	// ErrScheduleExpired indicates the schedule has already expired or has <1s remaining.
	ErrScheduleExpired = errors.New("schedule has expired or has less than 1 second remaining")
)

// MQTTPublisher defines an abstract MQTT 5.0 publisher interface.
type MQTTPublisher interface {
	Publish(ctx context.Context, topic string, qos byte, retain bool, expiryInterval uint32, payload []byte) error
}

// ScheduleDownlinkPayload matches the wire JSON contract in contracts/mqtt/schemas/schedule.schema.json.
type ScheduleDownlinkPayload struct {
	SchemaVersion          string                    `json:"schema_version"`
	RequestID              string                    `json:"request_id"`
	GatewayID              string                    `json:"gateway_id"`
	ScheduleID             string                    `json:"schedule_id"`
	ScheduleVersion        uint32                    `json:"schedule_version"`
	CreatedAt              string                    `json:"created_at"`
	ExpiresAt              string                    `json:"expires_at"`
	ProfileID              string                    `json:"profile_id"`
	SuperframeMs           int                       `json:"superframe_ms"`
	MinAnnounceSuperframes int                       `json:"min_announce_superframes,omitempty"`
	Slots                  []ScheduleDownlinkSlotDTO `json:"slots"`
}

// ScheduleDownlinkSlotDTO describes a slot within the schedule downlink payload.
type ScheduleDownlinkSlotDTO struct {
	NodeID     uint8 `json:"node_id"`
	SlotID     uint8 `json:"slot_id"`
	OffsetMs   int   `json:"offset_ms"`
	DurationMs int   `json:"duration_ms"`
}

// BuildScheduleDownlinkTopic formats the canonical downlink topic for a gateway.
func BuildScheduleDownlinkTopic(gatewayID string) string {
	return TopicPrefixGw + gatewayID + TopicSuffixScheduleDownlink
}

// ScheduleDispatcher publishes versioned TDMA schedules to Gateways over MQTT 5.0.
type ScheduleDispatcher struct {
	publisher MQTTPublisher
	nowFn     func() time.Time
}

// NewScheduleDispatcher constructs a new ScheduleDispatcher.
func NewScheduleDispatcher(publisher MQTTPublisher) (*ScheduleDispatcher, error) {
	if publisher == nil {
		return nil, ErrNilPublisher
	}
	return &ScheduleDispatcher{
		publisher: publisher,
		nowFn:     time.Now,
	}, nil
}

// SetNowFunc overrides the clock for deterministic testing.
func (d *ScheduleDispatcher) SetNowFunc(nowFn func() time.Time) {
	if nowFn != nil {
		d.nowFn = nowFn
	}
}

// DispatchSchedule constructs and transmits the schedule downlink message with MQTT 5.0 Message Expiry.
// Invariants enforced (MQ-004):
// - Topic: iot/v1/gw/{gateway_id}/downlink/schedule
// - QoS: 1
// - Retain: false (ALWAYS false)
// - Message Expiry Interval: floor(expires_at - now) in whole seconds
// - Rejects if remaining expiry < 1 second
func (d *ScheduleDispatcher) DispatchSchedule(ctx context.Context, sched *scheduler.Schedule) error {
	if sched == nil {
		return ErrNilScheduleToDispatch
	}
	if err := domain.ValidateGatewayID(sched.GatewayID); err != nil {
		return fmt.Errorf("invalid gateway_id in schedule: %w", err)
	}
	now := d.nowFn().UTC()
	remaining := sched.ExpiresAt.UTC().Sub(now)
	if remaining < time.Second {
		return fmt.Errorf("%w: expires_at %s is not at least 1s after now %s",
			ErrScheduleExpired, sched.ExpiresAt.Format(time.RFC3339), now.Format(time.RFC3339))
	}

	if err := sched.Validate(); err != nil {
		return fmt.Errorf("invalid schedule invariants: %w", err)
	}

	expiryIntervalSeconds := uint32(remaining.Seconds())

	slotsDTO := make([]ScheduleDownlinkSlotDTO, len(sched.Slots))
	for i, s := range sched.Slots {
		slotsDTO[i] = ScheduleDownlinkSlotDTO{
			NodeID:     s.NodeID,
			SlotID:     s.SlotID,
			OffsetMs:   s.OffsetMs,
			DurationMs: s.DurationMs,
		}
	}

	payload := ScheduleDownlinkPayload{
		SchemaVersion:          scheduler.DefaultSchemaVersion,
		RequestID:              sched.RequestID,
		GatewayID:              sched.GatewayID,
		ScheduleID:             sched.ScheduleID,
		ScheduleVersion:        sched.ScheduleVersion,
		CreatedAt:              sched.CreatedAt.UTC().Format(time.RFC3339),
		ExpiresAt:              sched.ExpiresAt.UTC().Format(time.RFC3339),
		ProfileID:              sched.ProfileID,
		SuperframeMs:           sched.SuperframeMs,
		MinAnnounceSuperframes: sched.MinAnnounceSuperframes,
		Slots:                  slotsDTO,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("failed to marshal schedule payload: %w", err)
	}

	topic := BuildScheduleDownlinkTopic(sched.GatewayID)

	// Publish QoS 1, Retain=false, Message Expiry Interval bounded by remaining lifetime
	err = d.publisher.Publish(ctx, topic, 1, false, expiryIntervalSeconds, body)
	if err != nil {
		return fmt.Errorf("failed to publish schedule to %s: %w", topic, err)
	}

	return nil
}
