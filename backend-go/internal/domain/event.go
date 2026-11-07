package domain

import (
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"time"
)

// Standard Event Severities defined in alert.schema.json
type EventSeverity string

const (
	SeverityP0Emergency EventSeverity = "P0_EMERGENCY"
	SeverityP1High      EventSeverity = "P1_HIGH"
	SeverityP2Medium    EventSeverity = "P2_MEDIUM"
	SeverityP3Normal    EventSeverity = "P3_NORMAL"
)

// ObservedTimeSource options defined in alert.schema.json
type TimeSource string

const (
	TimeSourceGatewayUTC TimeSource = "gateway_utc"
	TimeSourceNodeUTC    TimeSource = "node_utc"
	TimeSourceEstimated  TimeSource = "estimated"
	TimeSourceUnknown    TimeSource = "unknown"
)

// AckStatus tracks manual operator workflow acknowledgment in backend/UI
type AckStatus string

const (
	AckStatusUnacknowledged AckStatus = "UNACKNOWLEDGED"
	AckStatusAcknowledged   AckStatus = "ACKNOWLEDGED"
)

var (
	uuidRegex    = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)
	seqRegex     = regexp.MustCompile(`^(0|[1-9][0-9]{0,19})$`)
	gatewayRegex = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)

	ErrInvalidEventID        = errors.New("event_id does not match canonical gateway_id:gateway_epoch:event_seq format")
	ErrInvalidGatewayEpoch   = errors.New("gateway_epoch must be a valid UUID")
	ErrInvalidEventSeq       = errors.New("event_seq must be a decimal uint64 string without leading zeros")
	ErrInvalidNodeID         = errors.New("node_id must be between 1 and 254")
	ErrInvalidSlotID         = errors.New("slot_id must be between 1 and 15")
	ErrInvalidSeverity       = errors.New("invalid event severity")
	ErrInvalidTimeSource     = errors.New("invalid observed_time_source")
	ErrInvalidObservedAt     = errors.New("observed_at must be null when observed_time_source is unknown and UTC otherwise")
	ErrInvalidDutyCycle      = errors.New("node_duty_permille must be between 0 and 1000")
	ErrInvalidTriggerChannel = errors.New("trigger channel must be between 1 and 3")
	ErrMissingRadioACK       = errors.New("radio_ack_sent must be true for verified UP_EVENT ingestion")
)

// EventData contains event fields mapped from UP_EVENT (0x41 26B).
type EventData struct {
	EventRef   uint32
	EventCode  uint8
	EventValue int16
}

// EventTrigger optionally describes the specific limit violation that generated the event.
type EventTrigger struct {
	Channel      uint8
	ObservedRaw  int32
	ThresholdRaw int32
}

// Event represents an active V2 discrete alarm/event record.
type Event struct {
	ID                 int64
	SchemaVersion      string
	EventID            string
	GatewayID          string
	GatewayEpoch       string
	EventSeq           string
	NodeID             uint8
	SuperframeSeq      uint32
	SeqNum             uint8
	ScheduleVersion    uint32
	Severity           EventSeverity
	ObservedAt         *time.Time
	ObservedTimeSource TimeSource
	RadioRxMonotonicUS string
	Buffered           bool
	RadioAckSent       bool
	Data               EventData
	Trigger            *EventTrigger
	RawPayloadSHA256   [32]byte
	IngestedAt         time.Time
	AckStatus          AckStatus
	AcknowledgedAt     *time.Time
	AcknowledgedBy     *string
}

// Validate validates all field constraints according to alert.schema.json and semantic rules.
func (e *Event) Validate() error {
	if e == nil {
		return errors.New("event cannot be nil")
	}

	if !gatewayRegex.MatchString(e.GatewayID) {
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayID, e.GatewayID)
	}

	if !uuidRegex.MatchString(e.GatewayEpoch) {
		return fmt.Errorf("%w: '%s'", ErrInvalidGatewayEpoch, e.GatewayEpoch)
	}

	if !seqRegex.MatchString(e.EventSeq) {
		return fmt.Errorf("%w: '%s'", ErrInvalidEventSeq, e.EventSeq)
	}
	if _, err := strconv.ParseUint(e.EventSeq, 10, 64); err != nil {
		return fmt.Errorf("%w: %w", ErrInvalidEventSeq, err)
	}

	expectedEventID := fmt.Sprintf("%s:%s:%s", e.GatewayID, e.GatewayEpoch, e.EventSeq)
	if e.EventID != expectedEventID {
		return fmt.Errorf("%w: expected '%s', got '%s'", ErrInvalidEventID, expectedEventID, e.EventID)
	}

	if e.NodeID < 1 || e.NodeID > 254 {
		return fmt.Errorf("%w: %d", ErrInvalidNodeID, e.NodeID)
	}

	switch e.Severity {
	case SeverityP0Emergency, SeverityP1High, SeverityP2Medium, SeverityP3Normal:
	default:
		return fmt.Errorf("%w: '%s'", ErrInvalidSeverity, e.Severity)
	}

	switch e.ObservedTimeSource {
	case TimeSourceGatewayUTC, TimeSourceNodeUTC, TimeSourceEstimated:
		if e.ObservedAt == nil {
			return fmt.Errorf("%w: observed_at cannot be null when source is %s", ErrInvalidObservedAt, e.ObservedTimeSource)
		}
	case TimeSourceUnknown:
		if e.ObservedAt != nil {
			return fmt.Errorf("%w: observed_at must be null when source is unknown", ErrInvalidObservedAt)
		}
	default:
		return fmt.Errorf("%w: '%s'", ErrInvalidTimeSource, e.ObservedTimeSource)
	}

	if !seqRegex.MatchString(e.RadioRxMonotonicUS) {
		return errors.New("radio_rx_monotonic_us must be a valid unsigned decimal string")
	}

	if !e.RadioAckSent {
		return ErrMissingRadioACK
	}

	if e.Trigger != nil {
		if e.Trigger.Channel < 1 || e.Trigger.Channel > 3 {
			return fmt.Errorf("%w: %d", ErrInvalidTriggerChannel, e.Trigger.Channel)
		}
	}

	return nil
}

// ComputePayloadSHA256 returns a deterministic 32-byte SHA-256 digest of the business payload.
// If two events have the same gateway_id and event_id but differing business payloads,
// their payload digests will differ, triggering quarantine conflict detection.
func (e *Event) ComputePayloadSHA256() [32]byte {
	h := sha256.New()

	// Identity and sequence
	h.Write([]byte(e.EventID))
	h.Write([]byte{e.NodeID})

	var b4 [4]byte
	binary.BigEndian.PutUint32(b4[:], e.SuperframeSeq)
	h.Write(b4[:])
	h.Write([]byte{e.SeqNum})
	binary.BigEndian.PutUint32(b4[:], e.ScheduleVersion)
	h.Write(b4[:])

	// Severity and time
	h.Write([]byte(e.Severity))
	h.Write([]byte(e.ObservedTimeSource))
	if e.ObservedAt != nil {
		h.Write([]byte(e.ObservedAt.UTC().Format(time.RFC3339Nano)))
	}

	// Data metrics (UP_EVENT 0x41 26B)
	binary.BigEndian.PutUint32(b4[:], e.Data.EventRef)
	h.Write(b4[:])
	h.Write([]byte{e.Data.EventCode})
	var b2 [2]byte
	binary.BigEndian.PutUint16(b2[:], uint16(e.Data.EventValue))
	h.Write(b2[:])

	// Trigger
	if e.Trigger != nil {
		h.Write([]byte{e.Trigger.Channel})
		var tb [4]byte
		binary.BigEndian.PutUint32(tb[:], uint32(e.Trigger.ObservedRaw))
		h.Write(tb[:])
		binary.BigEndian.PutUint32(tb[:], uint32(e.Trigger.ThresholdRaw))
		h.Write(tb[:])
	} else {
		h.Write([]byte{0xFF})
	}

	var sum [32]byte
	copy(sum[:], h.Sum(nil))
	return sum
}
