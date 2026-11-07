package mqtt

import (
	"encoding/hex"
	"errors"
	"fmt"
	"math"
	"regexp"
	"strconv"
	"time"
)

var (
	// ErrInvalidSchemaVersion indicates schema_version is not "1.0-draft".
	ErrInvalidSchemaVersion = errors.New("invalid schema_version: must be 1.0-draft")
	// ErrInvalidEventID indicates event_id is malformed or does not equal gateway_id:gateway_epoch:event_seq.
	ErrInvalidEventID = errors.New("invalid event_id: must match gateway_id:gateway_epoch:event_seq")
	// ErrInvalidGatewayID indicates gateway_id does not match the approved regex pattern.
	ErrInvalidGatewayID = errors.New("invalid gateway_id format")
	// ErrInvalidGatewayEpoch indicates gateway_epoch is not a valid UUID string.
	ErrInvalidGatewayEpoch = errors.New("invalid gateway_epoch format: must be valid UUID")
	// ErrInvalidEventSeq indicates event_seq is not a valid decimal uint64.
	ErrInvalidEventSeq = errors.New("invalid event_seq format: must be decimal uint64 <= MaxUint64")
	// ErrInvalidObservedAt indicates observed_at is malformed or does not comply with clock source rules.
	ErrInvalidObservedAt = errors.New("invalid observed_at timestamp")
	// ErrInvalidTimeSource indicates observed_time_source is not one of the approved enum values.
	ErrInvalidTimeSource = errors.New("invalid observed_time_source: must be gateway_utc, node_utc, estimated, or unknown")
	// ErrInvalidMonotonicUS indicates radio_rx_monotonic_us is not a valid decimal uint64.
	ErrInvalidMonotonicUS = errors.New("invalid radio_rx_monotonic_us format: must be decimal uint64")
	// ErrInvalidTargetGWID indicates target_gw_id is outside the unicast range 0x01..0xFE (1..254).
	ErrInvalidTargetGWID = errors.New("invalid target_gw_id: must be 1..254 (0x01..0xFE)")
	// ErrInvalidRawFrameHex indicates raw_frame_hex is not exactly 136 hex characters (68 bytes).
	ErrInvalidRawFrameHex = errors.New("invalid raw_frame_hex: must be exactly 136 hex characters (68 bytes)")
	// ErrInvalidRSSI indicates rssi is outside the range [-140, 0].
	ErrInvalidRSSI = errors.New("invalid rssi: must be in range -140..0 dBm")
	// ErrInvalidSNR indicates snr is outside the range [-30.0, 30.0].
	ErrInvalidSNR = errors.New("invalid snr: must be in range -30.0..30.0 dB")
)

var (
	regexGatewayID    = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)
	regexGatewayEpoch = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)
	regexEventSeq     = regexp.MustCompile(`^(0|[1-9][0-9]{0,19})$`)
	regexMonotonicUS  = regexp.MustCompile(`^(0|[1-9][0-9]{0,19})$`)
	regexRawFrameHex  = regexp.MustCompile(`^[0-9a-fA-F]{136}$`)
)

// Approved enum values for observed_time_source.
const (
	TimeSourceGatewayUTC = "gateway_utc"
	TimeSourceNodeUTC    = "node_utc"
	TimeSourceEstimated  = "estimated"
	TimeSourceUnknown    = "unknown"

	// SchemaVersionJoinHello is the exact contract schema version string.
	SchemaVersionJoinHello = "1.0-draft"
)

// JoinHelloEnvelope represents the exact versioned MQTT V2 Join Hello relay envelope
// defined in contracts/mqtt/schemas/join-hello.schema.json.
type JoinHelloEnvelope struct {
	SchemaVersion      string  `json:"schema_version"`
	EventID            string  `json:"event_id"`
	GatewayID          string  `json:"gateway_id"`
	GatewayEpoch       string  `json:"gateway_epoch"`
	EventSeq           string  `json:"event_seq"`
	ObservedAt         *string `json:"observed_at"`
	ObservedTimeSource string  `json:"observed_time_source"`
	RadioRxMonotonicUS string  `json:"radio_rx_monotonic_us"`
	Buffered           bool    `json:"buffered"`
	TargetGWID         int     `json:"target_gw_id"`
	RawFrameHex        string  `json:"raw_frame_hex"`
	RSSI               int     `json:"rssi"`
	SNR                float64 `json:"snr"`
}

// Validate checks all schema constraints, regex formats, and semantic equality invariants
// specified in contracts/mqtt/schemas/join-hello.schema.json and semantic-rules.md (JH-01..JH-07).
func (e *JoinHelloEnvelope) Validate() error {
	if e.SchemaVersion != SchemaVersionJoinHello {
		return fmt.Errorf("%w: got %q", ErrInvalidSchemaVersion, e.SchemaVersion)
	}

	if !regexGatewayID.MatchString(e.GatewayID) {
		return fmt.Errorf("%w: got %q", ErrInvalidGatewayID, e.GatewayID)
	}

	if !regexGatewayEpoch.MatchString(e.GatewayEpoch) {
		return fmt.Errorf("%w: got %q", ErrInvalidGatewayEpoch, e.GatewayEpoch)
	}

	if !regexEventSeq.MatchString(e.EventSeq) {
		return fmt.Errorf("%w: got %q", ErrInvalidEventSeq, e.EventSeq)
	}
	seqVal, err := strconv.ParseUint(e.EventSeq, 10, 64)
	if err != nil || seqVal > math.MaxUint64 {
		return fmt.Errorf("%w: uint64 overflow %q", ErrInvalidEventSeq, e.EventSeq)
	}

	// Semantic equality: event_id MUST equal gateway_id + ":" + gateway_epoch + ":" + event_seq
	expectedEventID := fmt.Sprintf("%s:%s:%s", e.GatewayID, e.GatewayEpoch, e.EventSeq)
	if e.EventID != expectedEventID {
		return fmt.Errorf("%w: got %q, expected %q", ErrInvalidEventID, e.EventID, expectedEventID)
	}

	// Validate observed_time_source enum
	switch e.ObservedTimeSource {
	case TimeSourceGatewayUTC, TimeSourceNodeUTC, TimeSourceEstimated:
		if e.ObservedAt == nil {
			return fmt.Errorf("%w: observed_at must not be null when source is %q", ErrInvalidObservedAt, e.ObservedTimeSource)
		}
		// Validate RFC3339 ending in 'Z'
		t, err := time.Parse(time.RFC3339Nano, *e.ObservedAt)
		if err != nil || (*e.ObservedAt)[len(*e.ObservedAt)-1] != 'Z' {
			return fmt.Errorf("%w: must be valid RFC3339 ending with 'Z', got %q", ErrInvalidObservedAt, *e.ObservedAt)
		}
		_ = t
	case TimeSourceUnknown:
		// Schema allOf requirement: if observed_time_source == "unknown", observed_at MUST be null
		if e.ObservedAt != nil {
			return fmt.Errorf("%w: observed_at must be null when source is unknown, got %q", ErrInvalidObservedAt, *e.ObservedAt)
		}
	default:
		return fmt.Errorf("%w: got %q", ErrInvalidTimeSource, e.ObservedTimeSource)
	}

	if !regexMonotonicUS.MatchString(e.RadioRxMonotonicUS) {
		return fmt.Errorf("%w: got %q", ErrInvalidMonotonicUS, e.RadioRxMonotonicUS)
	}
	if _, err := strconv.ParseUint(e.RadioRxMonotonicUS, 10, 64); err != nil {
		return fmt.Errorf("%w: uint64 overflow %q", ErrInvalidMonotonicUS, e.RadioRxMonotonicUS)
	}

	// Target Gateway ID: 0x01..0xFE (1..254)
	if e.TargetGWID < 1 || e.TargetGWID > 254 {
		return fmt.Errorf("%w: got %d", ErrInvalidTargetGWID, e.TargetGWID)
	}

	// Raw frame hex: exactly 136 characters = 68 bytes
	if !regexRawFrameHex.MatchString(e.RawFrameHex) {
		return fmt.Errorf("%w: length=%d", ErrInvalidRawFrameHex, len(e.RawFrameHex))
	}

	// RSSI: -140..0
	if e.RSSI < -140 || e.RSSI > 0 {
		return fmt.Errorf("%w: got %d", ErrInvalidRSSI, e.RSSI)
	}

	// SNR: -30.0..30.0
	if e.SNR < -30.0 || e.SNR > 30.0 {
		return fmt.Errorf("%w: got %f", ErrInvalidSNR, e.SNR)
	}

	return nil
}

// DecodeRawFrameHex decodes the 136 hex characters of RawFrameHex into a 68-byte slice.
func (e *JoinHelloEnvelope) DecodeRawFrameHex() ([]byte, error) {
	if len(e.RawFrameHex) != 136 {
		return nil, ErrInvalidRawFrameHex
	}
	raw, err := hex.DecodeString(e.RawFrameHex)
	if err != nil {
		return nil, fmt.Errorf("hex decode raw frame: %w", err)
	}
	if len(raw) != 68 {
		return nil, fmt.Errorf("%w: decoded bytes=%d", ErrInvalidRawFrameHex, len(raw))
	}
	return raw, nil
}
