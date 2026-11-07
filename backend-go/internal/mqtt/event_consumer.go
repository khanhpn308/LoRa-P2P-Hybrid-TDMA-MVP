package mqtt

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"sync"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var (
	topicRegex = regexp.MustCompile(`^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/alert$`)

	ErrInvalidTopicNamespace    = errors.New("topic does not match canonical iot/v1/gw/{gateway_id}/uplink/alert format")
	ErrUnauthorizedPrincipal    = errors.New("authenticated principal does not match topic gateway_id or payload identity")
	ErrUnsupportedSchemaVersion = errors.New("unsupported schema_version; expected '1.0-draft'")
	ErrQueueFull                = errors.New("ingestion queue is full; backpressure applied")
	ErrConsumerClosed           = errors.New("event consumer is shut down")
)

// AlertEventPayload represents the wire JSON schema defined in alert.schema.json.
type AlertEventPayload struct {
	SchemaVersion      string               `json:"schema_version"`
	EventID            string               `json:"event_id"`
	GatewayID          string               `json:"gateway_id"`
	GatewayEpoch       string               `json:"gateway_epoch"`
	EventSeq           string               `json:"event_seq"`
	ObservedAt         *string              `json:"observed_at"`
	ObservedTimeSource string               `json:"observed_time_source"`
	RadioRxMonotonicUS string               `json:"radio_rx_monotonic_us"`
	Buffered           bool                 `json:"buffered"`
	NodeID             uint8                `json:"node_id"`
	SuperframeSeq      uint32               `json:"superframe_seq"`
	SeqNum             uint8                `json:"seq_num"`
	ScheduleVersion    uint32               `json:"schedule_version"`
	Severity           string               `json:"severity"`
	Data               AlertDataPayload     `json:"data"`
	Trigger            *AlertTriggerPayload `json:"trigger,omitempty"`
	RadioAckSent       bool                 `json:"radio_ack_sent"`
}

// AlertDataPayload represents sensor payload metrics mapped from UP_EVENT (0x41 26B).
type AlertDataPayload struct {
	EventRef   uint32 `json:"event_ref"`
	EventCode  uint8  `json:"event_code"`
	EventValue int16  `json:"event_value"`
}

// AlertTriggerPayload represents trigger threshold metrics.
type AlertTriggerPayload struct {
	Channel      uint8 `json:"channel"`
	ObservedRaw  int32 `json:"observed_raw"`
	ThresholdRaw int32 `json:"threshold_raw"`
}

// IngestMessage wraps an incoming MQTT packet along with transport credentials.
type IngestMessage struct {
	Topic         string
	AuthPrincipal string
	Payload       []byte
	ResultChan    chan error
}

// EventConsumerConfig configures queue bounds and worker pool size.
type EventConsumerConfig struct {
	WorkerCount int
	QueueDepth  int
}

// EventConsumer ingests MQTT discrete events with authenticated gateway binding,
// schema validation, poison-payload quarantine, and strict deduplication.
type EventConsumer struct {
	repo   storage.EventRepository
	cfg    EventConsumerConfig
	queue  chan IngestMessage
	wg     sync.WaitGroup
	ctx    context.Context
	cancel context.CancelFunc
	mu     sync.Mutex
	closed bool
}

// NewEventConsumer instantiates an EventConsumer with bounded concurrency.
func NewEventConsumer(repo storage.EventRepository, cfg EventConsumerConfig) *EventConsumer {
	if cfg.WorkerCount <= 0 {
		cfg.WorkerCount = 4
	}
	if cfg.QueueDepth <= 0 {
		cfg.QueueDepth = 128
	}

	ctx, cancel := context.WithCancel(context.Background())
	ec := &EventConsumer{
		repo:   repo,
		cfg:    cfg,
		queue:  make(chan IngestMessage, cfg.QueueDepth),
		ctx:    ctx,
		cancel: cancel,
	}

	ec.startWorkers()
	return ec
}

func (ec *EventConsumer) startWorkers() {
	for i := 0; i < ec.cfg.WorkerCount; i++ {
		ec.wg.Add(1)
		go func() {
			defer ec.wg.Done()
			for {
				select {
				case <-ec.ctx.Done():
					return
				case msg, ok := <-ec.queue:
					if !ok {
						return
					}
					err := ec.processMessage(ec.ctx, msg)
					if msg.ResultChan != nil {
						msg.ResultChan <- err
					}
				}
			}
		}()
	}
}

// Submit enqueues an incoming MQTT packet. Returns ErrQueueFull when backpressure limit is hit.
func (ec *EventConsumer) Submit(ctx context.Context, msg IngestMessage) error {
	ec.mu.Lock()
	if ec.closed {
		ec.mu.Unlock()
		return ErrConsumerClosed
	}
	ec.mu.Unlock()

	select {
	case ec.queue <- msg:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	default:
		return ErrQueueFull
	}
}

// ProcessSync processes an incoming MQTT message synchronously within caller context.
func (ec *EventConsumer) ProcessSync(ctx context.Context, msg IngestMessage) error {
	return ec.processMessage(ctx, msg)
}

func (ec *EventConsumer) processMessage(ctx context.Context, msg IngestMessage) (err error) {
	// Guard against panics
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("panic recovered in event consumer: %v", r)
		}
	}()

	// 1. Validate topic namespace
	matches := topicRegex.FindStringSubmatch(msg.Topic)
	if len(matches) < 2 {
		_ = ec.repo.QuarantineEvent(ctx, &storage.QuarantineRecord{
			GatewayID:      msg.AuthPrincipal,
			EventID:        "unknown",
			ConflictReason: "MALFORMED_PAYLOAD",
			RawPayload:     string(msg.Payload),
		})
		return fmt.Errorf("%w: '%s'", ErrInvalidTopicNamespace, msg.Topic)
	}
	topicGW := matches[1]

	// 2. Enforce mTLS / broker principal identity binding
	if msg.AuthPrincipal != "" && msg.AuthPrincipal != topicGW {
		_ = ec.repo.QuarantineEvent(ctx, &storage.QuarantineRecord{
			GatewayID:      msg.AuthPrincipal,
			EventID:        "unauthorized-topic",
			ConflictReason: "UNAUTHORIZED_GATEWAY_NODE",
			RawPayload:     fmt.Sprintf("auth_principal=%s, topic_gw=%s", msg.AuthPrincipal, topicGW),
		})
		return fmt.Errorf("%w: principal '%s' tried publishing to topic for '%s'", ErrUnauthorizedPrincipal, msg.AuthPrincipal, topicGW)
	}

	// 3. Unmarshal wire payload
	var wire AlertEventPayload
	if unmarshalErr := json.Unmarshal(msg.Payload, &wire); unmarshalErr != nil {
		_ = ec.repo.QuarantineEvent(ctx, &storage.QuarantineRecord{
			GatewayID:      topicGW,
			EventID:        "malformed-json",
			ConflictReason: "MALFORMED_PAYLOAD",
			RawPayload:     string(msg.Payload),
		})
		return fmt.Errorf("malformed JSON payload: %w", unmarshalErr)
	}

	// 4. Verify payload gateway_id matches authenticated principal and topic
	if wire.GatewayID != topicGW || (msg.AuthPrincipal != "" && wire.GatewayID != msg.AuthPrincipal) {
		_ = ec.repo.QuarantineEvent(ctx, &storage.QuarantineRecord{
			GatewayID:      topicGW,
			EventID:        wire.EventID,
			ConflictReason: "UNAUTHORIZED_GATEWAY_NODE",
			RawPayload:     fmt.Sprintf("payload_gw=%s, topic_gw=%s, auth=%s", wire.GatewayID, topicGW, msg.AuthPrincipal),
		})
		return fmt.Errorf("%w: payload gateway_id '%s' differs from topic '%s'", ErrUnauthorizedPrincipal, wire.GatewayID, topicGW)
	}

	// 5. Check schema version
	if wire.SchemaVersion != "1.0-draft" {
		_ = ec.repo.QuarantineEvent(ctx, &storage.QuarantineRecord{
			GatewayID:      topicGW,
			EventID:        wire.EventID,
			ConflictReason: "SCHEMA_VALIDATION_FAILED",
			RawPayload:     fmt.Sprintf("unsupported schema_version: %s", wire.SchemaVersion),
		})
		return fmt.Errorf("%w: got '%s'", ErrUnsupportedSchemaVersion, wire.SchemaVersion)
	}

	// 6. Map to domain Event
	evt := &domain.Event{
		SchemaVersion:      wire.SchemaVersion,
		EventID:            wire.EventID,
		GatewayID:          wire.GatewayID,
		GatewayEpoch:       wire.GatewayEpoch,
		EventSeq:           wire.EventSeq,
		NodeID:             wire.NodeID,
		SuperframeSeq:      wire.SuperframeSeq,
		SeqNum:             wire.SeqNum,
		ScheduleVersion:    wire.ScheduleVersion,
		Severity:           domain.EventSeverity(wire.Severity),
		ObservedTimeSource: domain.TimeSource(wire.ObservedTimeSource),
		RadioRxMonotonicUS: wire.RadioRxMonotonicUS,
		Buffered:           wire.Buffered,
		RadioAckSent:       wire.RadioAckSent,
		Data: domain.EventData{
			EventRef:   wire.Data.EventRef,
			EventCode:  wire.Data.EventCode,
			EventValue: wire.Data.EventValue,
		},
		AckStatus: domain.AckStatusUnacknowledged,
	}

	if wire.ObservedAt != nil {
		parsedTime, parseErr := time.Parse(time.RFC3339Nano, *wire.ObservedAt)
		if parseErr != nil {
			_ = ec.repo.QuarantineEvent(ctx, &storage.QuarantineRecord{
				GatewayID:      topicGW,
				EventID:        wire.EventID,
				ConflictReason: "SCHEMA_VALIDATION_FAILED",
				RawPayload:     fmt.Sprintf("invalid observed_at timestamp format: %s", *wire.ObservedAt),
			})
			return fmt.Errorf("invalid observed_at timestamp format: %w", parseErr)
		}
		utcTime := parsedTime.UTC()
		evt.ObservedAt = &utcTime
	}

	if wire.Trigger != nil {
		evt.Trigger = &domain.EventTrigger{
			Channel:      wire.Trigger.Channel,
			ObservedRaw:  wire.Trigger.ObservedRaw,
			ThresholdRaw: wire.Trigger.ThresholdRaw,
		}
	}

	// 7. Validate domain invariants
	if valErr := evt.Validate(); valErr != nil {
		_ = ec.repo.QuarantineEvent(ctx, &storage.QuarantineRecord{
			GatewayID:      topicGW,
			EventID:        wire.EventID,
			ConflictReason: "SCHEMA_VALIDATION_FAILED",
			RawPayload:     fmt.Sprintf("domain validation error: %v", valErr),
		})
		return fmt.Errorf("schema validation error: %w", valErr)
	}

	// 8. Idempotently record into PostgreSQL storage
	res, recErr := ec.repo.RecordEvent(ctx, evt)
	if recErr != nil {
		// Error logged by caller, conflict already quarantined
		return recErr
	}

	// Log idempotent processing metric
	_ = res
	return nil
}

// Close gracefully stops the consumer, draining any buffered work items.
func (ec *EventConsumer) Close() error {
	ec.mu.Lock()
	if ec.closed {
		ec.mu.Unlock()
		return nil
	}
	ec.closed = true
	close(ec.queue)
	ec.mu.Unlock()

	ec.cancel()
	ec.wg.Wait()
	return nil
}
