package mqtt

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"sync"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

var (
	statusTopicRegex   = regexp.MustCompile(`^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/status$`)
	statusEventIDRegex = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}:(0|[1-9][0-9]{0,19})$`)

	ErrInvalidStatusTopicNamespace = errors.New("topic does not match canonical iot/v1/gw/{gateway_id}/uplink/status format")
	ErrStatusConsumerClosed        = errors.New("status consumer is shut down")
	ErrInvalidStatusPayload        = errors.New("invalid status schema payload")
)

// StatusEventPayload represents the wire JSON schema defined in status.schema.json.
type StatusEventPayload struct {
	SchemaVersion           string  `json:"schema_version"`
	EventID                 string  `json:"event_id"`
	GatewayID               string  `json:"gateway_id"`
	GatewayEpoch            string  `json:"gateway_epoch"`
	EventSeq                string  `json:"event_seq"`
	ObservedAt              *string `json:"observed_at"`
	ObservedTimeSource      string  `json:"observed_time_source"`
	RadioRxMonotonicUS      string  `json:"radio_rx_monotonic_us"`
	Buffered                bool    `json:"buffered"`
	ActiveScheduleVersion   uint32  `json:"active_schedule_version"`
	Mode                    string  `json:"mode"`
	RFDutyPermille          int     `json:"rf_duty_permille"`
	FreeHeapBytes           uint32  `json:"free_heap_bytes"`
	OfflineQueueCount       uint32  `json:"offline_queue_count"`
	OfflineDroppedAlert     string  `json:"offline_dropped_alert"`
	OfflineDroppedTelemetry *string `json:"offline_dropped_telemetry,omitempty"`
	NodeCount               int     `json:"node_count"`
	ActiveRequestID         *string `json:"active_request_id,omitempty"`
	ActiveScheduleID        *string `json:"active_schedule_id,omitempty"`
	StagedScheduleVersion   *uint32 `json:"staged_schedule_version,omitempty"`
	PendingEventCount       *uint8  `json:"pending_event_count,omitempty"`
	DroppedEventCount       *string `json:"dropped_event_count,omitempty"`
	DiagSeq                 *string `json:"diag_seq,omitempty"`
	ChannelID               *string `json:"channel_id,omitempty"`
	MaintSeq                *uint32 `json:"maint_seq,omitempty"`
}

// StatusConsumerConfig configures worker pool size and ingestion queue depth.
type StatusConsumerConfig struct {
	WorkerCount int
	QueueDepth  int
}

// StatusConsumer ingests MQTT operational status snapshots with authenticated principal binding,
// schema validation against status.schema.json, and durable persistence into PostgreSQL.
// Authority: MQ-001, MQ-002, MQ-003, SE-002, SE-004.
type StatusConsumer struct {
	storage storage.StatusStorage
	cfg     StatusConsumerConfig
	queue   chan IngestMessage
	wg      sync.WaitGroup
	ctx     context.Context
	cancel  context.CancelFunc
	mu      sync.Mutex
	closed  bool
}

// NewStatusConsumer instantiates a new StatusConsumer.
func NewStatusConsumer(store storage.StatusStorage, cfg StatusConsumerConfig) *StatusConsumer {
	if cfg.WorkerCount <= 0 {
		cfg.WorkerCount = 4
	}
	if cfg.QueueDepth <= 0 {
		cfg.QueueDepth = 128
	}

	ctx, cancel := context.WithCancel(context.Background())
	sc := &StatusConsumer{
		storage: store,
		cfg:     cfg,
		queue:   make(chan IngestMessage, cfg.QueueDepth),
		ctx:     ctx,
		cancel:  cancel,
	}

	sc.startWorkers()
	return sc
}

func (sc *StatusConsumer) startWorkers() {
	for i := 0; i < sc.cfg.WorkerCount; i++ {
		sc.wg.Add(1)
		go func() {
			defer sc.wg.Done()
			for {
				select {
				case <-sc.ctx.Done():
					return
				case msg, ok := <-sc.queue:
					if !ok {
						return
					}
					err := sc.processMessage(sc.ctx, msg)
					if msg.ResultChan != nil {
						msg.ResultChan <- err
					}
				}
			}
		}()
	}
}

// Submit enqueues an incoming MQTT packet for async processing.
func (sc *StatusConsumer) Submit(ctx context.Context, msg IngestMessage) error {
	sc.mu.Lock()
	if sc.closed {
		sc.mu.Unlock()
		return ErrStatusConsumerClosed
	}
	sc.mu.Unlock()

	select {
	case sc.queue <- msg:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	default:
		return ErrQueueFull
	}
}

// ProcessSync processes an incoming status packet synchronously within caller context.
func (sc *StatusConsumer) ProcessSync(ctx context.Context, msg IngestMessage) error {
	return sc.processMessage(ctx, msg)
}

func (sc *StatusConsumer) processMessage(ctx context.Context, msg IngestMessage) (err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("panic recovered in status consumer: %v", r)
		}
	}()

	// 1. Validate topic namespace
	matches := statusTopicRegex.FindStringSubmatch(msg.Topic)
	if len(matches) < 2 {
		return fmt.Errorf("%w: '%s'", ErrInvalidStatusTopicNamespace, msg.Topic)
	}
	topicGW := matches[1]

	// 2. Enforce mTLS / broker principal identity binding (MQ-002, SE-002)
	if msg.AuthPrincipal != "" && msg.AuthPrincipal != topicGW {
		return fmt.Errorf("%w: principal '%s' tried publishing to topic for '%s'", ErrUnauthorizedPrincipal, msg.AuthPrincipal, topicGW)
	}

	// 3. Unmarshal wire payload
	var wire StatusEventPayload
	if unmarshalErr := json.Unmarshal(msg.Payload, &wire); unmarshalErr != nil {
		return fmt.Errorf("malformed JSON payload: %w", unmarshalErr)
	}

	// 4. Verify payload gateway_id matches authenticated principal and topic
	if wire.GatewayID != topicGW || (msg.AuthPrincipal != "" && wire.GatewayID != msg.AuthPrincipal) {
		return fmt.Errorf("%w: payload gateway_id '%s' differs from topic '%s'", ErrUnauthorizedPrincipal, wire.GatewayID, topicGW)
	}

	// 5. Check schema version
	if wire.SchemaVersion != "1.0-draft" {
		return fmt.Errorf("%w: got '%s'", ErrUnsupportedSchemaVersion, wire.SchemaVersion)
	}

	// 6. Validate event_id format and component equality
	if !statusEventIDRegex.MatchString(wire.EventID) {
		return fmt.Errorf("%w: invalid event_id pattern '%s'", ErrInvalidStatusPayload, wire.EventID)
	}
	expectedEventID := fmt.Sprintf("%s:%s:%s", wire.GatewayID, wire.GatewayEpoch, wire.EventSeq)
	if wire.EventID != expectedEventID {
		return fmt.Errorf("%w: event_id '%s' != expected '%s'", ErrInvalidStatusPayload, wire.EventID, expectedEventID)
	}

	// 7. Validate mode enum
	var gMode domain.GatewayMode
	switch wire.Mode {
	case "BOOTSTRAP":
		gMode = domain.GatewayModeBootstrap
	case "ACTIVE":
		gMode = domain.GatewayModeActive
	case "AUTONOMOUS":
		gMode = domain.GatewayModeAutonomous
	case "RECOVERY":
		gMode = domain.GatewayModeRecovery
	case "FAULT":
		gMode = domain.GatewayModeFault
	default:
		return fmt.Errorf("%w: invalid mode '%s'", domain.ErrInvalidGatewayMode, wire.Mode)
	}

	// 8. Validate observed_at and observed_time_source rules
	var lastSeen time.Time
	switch wire.ObservedTimeSource {
	case "gateway_utc", "node_utc", "estimated":
		if wire.ObservedAt == nil {
			return fmt.Errorf("%w: observed_at cannot be null when source is '%s'", ErrInvalidStatusPayload, wire.ObservedTimeSource)
		}
		t, parseErr := time.Parse(time.RFC3339Nano, *wire.ObservedAt)
		if parseErr != nil {
			return fmt.Errorf("%w: invalid observed_at format '%s': %w", ErrInvalidStatusPayload, *wire.ObservedAt, parseErr)
		}
		lastSeen = t.UTC()
	case "unknown":
		if wire.ObservedAt != nil {
			return fmt.Errorf("%w: observed_at must be null when source is 'unknown'", ErrInvalidStatusPayload)
		}
		lastSeen = time.Now().UTC()
	default:
		return fmt.Errorf("%w: invalid observed_time_source '%s'", ErrInvalidStatusPayload, wire.ObservedTimeSource)
	}

	// 9. Validate channel_id if present
	if wire.ChannelID != nil && *wire.ChannelID != "" {
		if !domain.ChannelIDPattern.MatchString(*wire.ChannelID) {
			return fmt.Errorf("%w: invalid channel_id '%s'", domain.ErrInvalidChannelID, *wire.ChannelID)
		}
	}

	// 10. Parse pending_event_count (DEC-MH-02: 0x44 UP_HEALTH_REPLY)
	var pendingCount uint8
	if wire.PendingEventCount != nil {
		pendingCount = *wire.PendingEventCount
	}

	// 11. Parse dropped_event_count (DEC-MH-08: 0x4A UP_DIAG_METRICS)
	var droppedCount uint64
	if wire.DroppedEventCount != nil && *wire.DroppedEventCount != "" {
		parsed, parseErr := strconv.ParseUint(*wire.DroppedEventCount, 10, 64)
		if parseErr != nil {
			return fmt.Errorf("%w: invalid dropped_event_count '%s': %w", ErrInvalidStatusPayload, *wire.DroppedEventCount, parseErr)
		}
		droppedCount = parsed
	}

	// 12. Construct domain record
	record := &domain.GatewayStatusRecord{
		GatewayID:             wire.GatewayID,
		GatewayEpoch:          wire.GatewayEpoch,
		Mode:                  gMode,
		ActiveScheduleVersion: wire.ActiveScheduleVersion,
		ChannelID:             wire.ChannelID,
		RFDutyPermille:        wire.RFDutyPermille,
		NodeCount:             wire.NodeCount,
		FreeHeapBytes:         uint64(wire.FreeHeapBytes),
		OfflineQueueCount:     wire.OfflineQueueCount,
		PendingEventCount:     pendingCount,
		DroppedEventCount:     droppedCount,
		LastSeenAt:            lastSeen,
		UpdatedAt:             time.Now().UTC(),
	}

	if valErr := record.Validate(); valErr != nil {
		return fmt.Errorf("domain status validation failed: %w", valErr)
	}

	// 13. Persist snapshot into PostgreSQL
	if upsertErr := sc.storage.UpsertGatewayStatus(ctx, record); upsertErr != nil {
		return fmt.Errorf("failed to persist gateway status: %w", upsertErr)
	}

	return nil
}

// Close gracefully terminates worker routines.
func (sc *StatusConsumer) Close() error {
	sc.mu.Lock()
	if sc.closed {
		sc.mu.Unlock()
		return nil
	}
	sc.closed = true
	close(sc.queue)
	sc.mu.Unlock()

	sc.cancel()
	sc.wg.Wait()
	return nil
}
