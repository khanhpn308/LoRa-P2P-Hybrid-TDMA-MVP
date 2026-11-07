package mqtt

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

const (
	// TopicSuffixScheduleAckUplink is the canonical MQTT 5.0 suffix for schedule ack uplink.
	TopicSuffixScheduleAckUplink = "/uplink/schedule-ack"
	// TopicFilterScheduleAckUplink is the wildcard subscription topic filter for schedule acknowledgments.
	TopicFilterScheduleAckUplink = "iot/v1/gw/+/uplink/schedule-ack"
)

var (
	// ErrNilLifecycleEngine indicates a nil LifecycleEngine was provided.
	ErrNilLifecycleEngine = errors.New("lifecycle engine cannot be nil")
	// ErrMalformedScheduleAckTopic indicates the topic does not match the canonical schedule-ack format.
	ErrMalformedScheduleAckTopic = errors.New("topic does not match canonical iot/v1/gw/{gateway_id}/uplink/schedule-ack format")
	// ErrInvalidAckPayload indicates payload JSON deserialization or schema validation failure.
	ErrInvalidAckPayload = errors.New("invalid schedule ack payload")
	// ErrEventIDSemanticMismatch indicates event_id != gateway_id + ':' + gateway_epoch + ':' + event_seq.
	ErrEventIDSemanticMismatch = errors.New("event_id does not match gateway_id:gateway_epoch:event_seq semantic requirement")
	// ErrStageReasonMismatch indicates inconsistent stage and reason_code combinations.
	ErrStageReasonMismatch = errors.New("inconsistent stage and reason_code according to contract schema")
	// ErrActivatedSeqMismatch indicates unexpected activated_at_superframe_seq presence or absence.
	ErrActivatedSeqMismatch = errors.New("invalid activated_at_superframe_seq for reported stage")
)

// ScheduleAckPayload describes the wire JSON schema of contracts/mqtt/schemas/schedule-ack.schema.json.
type ScheduleAckPayload struct {
	SchemaVersion            string  `json:"schema_version"`
	EventID                  string  `json:"event_id"`
	GatewayID                string  `json:"gateway_id"`
	GatewayEpoch             string  `json:"gateway_epoch"`
	EventSeq                 string  `json:"event_seq"`
	ObservedAt               *string `json:"observed_at"`
	ObservedTimeSource       string  `json:"observed_time_source"`
	RadioRxMonotonicUS       string  `json:"radio_rx_monotonic_us"`
	Buffered                 bool    `json:"buffered"`
	RequestID                string  `json:"request_id"`
	ScheduleID               string  `json:"schedule_id"`
	ScheduleVersion          uint32  `json:"schedule_version"`
	Stage                    string  `json:"stage"` // STAGE_ACK, VERIFY_NACK, ACTIVE_REPORT
	ActivateAtSuperframeSeq  *uint32 `json:"activate_at_superframe_seq"`
	ActivatedAtSuperframeSeq *uint32 `json:"activated_at_superframe_seq"`
	ReasonCode               string  `json:"reason_code"`
}

// BuildScheduleAckTopic formats the canonical schedule-ack topic for a gateway.
func BuildScheduleAckTopic(gatewayID string) string {
	return TopicPrefixGw + gatewayID + TopicSuffixScheduleAckUplink
}

// ParseScheduleAckTopic extracts and validates the gateway_id from a schedule-ack topic.
func ParseScheduleAckTopic(topic string) (string, error) {
	if !strings.HasPrefix(topic, TopicPrefixGw) || !strings.HasSuffix(topic, TopicSuffixScheduleAckUplink) {
		return "", fmt.Errorf("%w: %q", ErrMalformedScheduleAckTopic, topic)
	}

	gatewayID := topic[len(TopicPrefixGw) : len(topic)-len(TopicSuffixScheduleAckUplink)]
	if gatewayID == "" || strings.Contains(gatewayID, "/") {
		return "", fmt.Errorf("%w: invalid gateway_id segment %q", ErrMalformedScheduleAckTopic, gatewayID)
	}

	if err := domain.ValidateGatewayID(gatewayID); err != nil {
		return "", fmt.Errorf("%w: %w", ErrMalformedScheduleAckTopic, err)
	}

	return gatewayID, nil
}

// ScheduleAckConsumer ingests Gateway schedule acknowledgment messages from Mosquitto and forwards to LifecycleEngine.
type ScheduleAckConsumer struct {
	engine *scheduler.LifecycleEngine
}

// NewScheduleAckConsumer creates a new ScheduleAckConsumer instance.
func NewScheduleAckConsumer(engine *scheduler.LifecycleEngine) (*ScheduleAckConsumer, error) {
	if engine == nil {
		return nil, ErrNilLifecycleEngine
	}
	return &ScheduleAckConsumer{
		engine: engine,
	}, nil
}

// HandleMessage parses and verifies an incoming schedule-ack MQTT message and routes it to LifecycleEngine.
// Invariants enforced (contracts/mqtt/semantic-rules.md §4, MQ-009):
// - STAGE_ACK: confirms staging; NEVER promotes schedule to ACTIVE.
// - ACTIVE_REPORT: confirms radio switch; promotes schedule to ACTIVE only upon verified boundary.
// - VERIFY_NACK: reports gateway rejection.
func (c *ScheduleAckConsumer) HandleMessage(ctx context.Context, topic string, payloadBytes []byte) error {
	topicGwID, err := ParseScheduleAckTopic(topic)
	if err != nil {
		return err
	}

	var payload ScheduleAckPayload
	if err := json.Unmarshal(payloadBytes, &payload); err != nil {
		return fmt.Errorf("%w: json decode failed: %v", ErrInvalidAckPayload, err)
	}

	// 1. Validate schema version
	if payload.SchemaVersion != scheduler.DefaultSchemaVersion {
		return fmt.Errorf("%w: expected schema_version %s, got %s",
			ErrUnsupportedSchemaVersion, scheduler.DefaultSchemaVersion, payload.SchemaVersion)
	}

	// 2. Validate gateway_id matches topic principal
	if payload.GatewayID != topicGwID {
		return fmt.Errorf("%w: payload gateway_id %q != topic gateway_id %q",
			ErrIdentityMismatch, payload.GatewayID, topicGwID)
	}

	// 3. Validate semantic event_id equality: event_id == gateway_id + ':' + gateway_epoch + ':' + event_seq
	expectedEventID := fmt.Sprintf("%s:%s:%s", payload.GatewayID, payload.GatewayEpoch, payload.EventSeq)
	if payload.EventID != expectedEventID {
		return fmt.Errorf("%w: expected %q, got %q", ErrEventIDSemanticMismatch, expectedEventID, payload.EventID)
	}

	// 4. Validate stage and reason_code invariants
	switch payload.Stage {
	case "STAGE_ACK":
		if payload.ReasonCode != "NONE" {
			return fmt.Errorf("%w: STAGE_ACK reason_code must be NONE, got %s", ErrStageReasonMismatch, payload.ReasonCode)
		}
		if payload.ActivatedAtSuperframeSeq != nil {
			return fmt.Errorf("%w: STAGE_ACK must have activated_at_superframe_seq = null", ErrActivatedSeqMismatch)
		}
		if payload.ActivateAtSuperframeSeq == nil {
			return fmt.Errorf("%w: STAGE_ACK requires activate_at_superframe_seq", ErrInvalidAckPayload)
		}

	case "VERIFY_NACK":
		if payload.ReasonCode == "NONE" {
			return fmt.Errorf("%w: VERIFY_NACK reason_code cannot be NONE", ErrStageReasonMismatch)
		}
		if payload.ActivatedAtSuperframeSeq != nil {
			return fmt.Errorf("%w: VERIFY_NACK must have activated_at_superframe_seq = null", ErrActivatedSeqMismatch)
		}

	case "ACTIVE_REPORT":
		if payload.ReasonCode != "NONE" {
			return fmt.Errorf("%w: ACTIVE_REPORT reason_code must be NONE, got %s", ErrStageReasonMismatch, payload.ReasonCode)
		}
		if payload.ActivatedAtSuperframeSeq == nil {
			return fmt.Errorf("%w: ACTIVE_REPORT requires activated_at_superframe_seq non-null", ErrActivatedSeqMismatch)
		}
		if payload.ActivateAtSuperframeSeq == nil {
			return fmt.Errorf("%w: ACTIVE_REPORT requires activate_at_superframe_seq non-null", ErrInvalidAckPayload)
		}

	default:
		return fmt.Errorf("%w: unsupported stage %q", ErrInvalidAckPayload, payload.Stage)
	}

	// 5. Parse observed_at timestamp if present
	var observedAt *time.Time
	if payload.ObservedAt != nil && *payload.ObservedAt != "" {
		t, err := time.Parse(time.RFC3339, *payload.ObservedAt)
		if err != nil {
			return fmt.Errorf("%w: invalid observed_at timestamp %q: %v", ErrInvalidAckPayload, *payload.ObservedAt, err)
		}
		utc := t.UTC()
		observedAt = &utc
	}

	// 6. Map to domain StageAckReport and forward to LifecycleEngine
	report := scheduler.StageAckReport{
		EventID:                  payload.EventID,
		GatewayID:                payload.GatewayID,
		GatewayEpoch:             payload.GatewayEpoch,
		EventSeq:                 payload.EventSeq,
		ObservedAt:               observedAt,
		ObservedTimeSource:       payload.ObservedTimeSource,
		RadioRxMonotonicUs:       payload.RadioRxMonotonicUS,
		Buffered:                 payload.Buffered,
		RequestID:                payload.RequestID,
		ScheduleID:               payload.ScheduleID,
		ScheduleVersion:          payload.ScheduleVersion,
		Stage:                    payload.Stage,
		ActivateAtSuperframeSeq:  payload.ActivateAtSuperframeSeq,
		ActivatedAtSuperframeSeq: payload.ActivatedAtSuperframeSeq,
		ReasonCode:               payload.ReasonCode,
	}

	if err := c.engine.HandleScheduleAck(ctx, report); err != nil {
		return fmt.Errorf("lifecycle engine failed to process schedule ack: %w", err)
	}

	return nil
}
