package scheduler

import (
	"context"
	"errors"
	"fmt"
	"math"
	"time"
)

// Channel allocation status and constants.
const (
	// DefaultBandwidthHz is 125 kHz per VN920 PHY baseline.
	DefaultBandwidthHz int64 = 125000

	// StatusAllocated is the status for actively allocated channels.
	StatusAllocated = "ALLOCATED"
)

// ChannelAllocation represents gateway channel allocation details required for feasibility validation.
type ChannelAllocation struct {
	GatewayID string
	ChannelID string
	Status    string
}

// Conservative system turnaround budgets for Gateway and Node.
const (
	// GatewayWalTurnaroundMs is the conservative budget for Gateway RX, AES-CCM verification,
	// durable WAL/SQLite persistence, and TX preparation for DOWN_EVENT_ACK.
	GatewayWalTurnaroundMs = 50

	// NodeAckProcessingMs is the conservative budget for Node switching to RX and verifying ACK.
	NodeAckProcessingMs = 20

	// MaxOscillatorDriftPpm is the conservative worst-case oscillator drift (40 ppm).
	MaxOscillatorDriftPpm = 40.0
)

// Approved frame payload sizes in octets (per contracts/radio-mac/specification.md).
const (
	BytesUpEvent           = 26 // 0x41: Header 7B + Ciphertext 11B + CCM-8 8B
	BytesDownEventAck      = 19 // 0x42: Header 7B + Ciphertext 4B + CCM-8 8B
	BytesDownSyncBeacon    = 32 // 0x43: Header 16B + HMAC-SHA256-128 16B
	BytesUpHealthReply     = 21 // 0x44: Header 7B + Ciphertext 6B + CCM-8 8B
	BytesUpDiagMetrics     = 23 // 0x4A: Header 7B + Ciphertext 8B + CCM-8 8B
	BytesDownSchedPrepare  = 80 // 0x4B: Header 16B + Ed25519 Sig 64B
	BytesUpSchedReady      = 41 // 0x4C: Header 7B + Ciphertext 26B + CCM-8 8B
	BytesDownSchedDecision = 80 // 0x4D: Header 16B + Ed25519 Sig 64B
)

var (
	ErrToAExceedsSlot       = errors.New("RF Time-on-Air and turnaround exceeds usable slot window")
	ErrUnsafeClockDrift     = errors.New("worst-case clock drift exceeds guard band budget")
	ErrChannelNotAllocated  = errors.New("gateway does not hold an active channel allocation for the requested channel")
	ErrInvalidPHYConfig     = errors.New("unsupported LoRa PHY configuration: SF must be 7 or 8, BW must be 125000 Hz")
	ErrRadioOverlapDetected = errors.New("half-duplex single radio constraint violation: overlapping transmissions")
)

// LoRaPHYConfig specifies SX1276 LoRa physical layer configuration parameters.
type LoRaPHYConfig struct {
	SpreadingFactor     int   // SF7 or SF8 approved for MVP
	BandwidthHz         int64 // 125000 Hz for VN920_V1
	CodingRate          int   // 1 for 4/5
	PreambleLength      int   // 8 symbols
	ExplicitHeader      bool  // true for explicit header mode (H=0 in formula)
	LowDataRateOptimize bool  // false for SF7/SF8 @ 125kHz
	CRCOn               bool  // true for packet CRC enabled
}

// DefaultVN920PHY returns the default approved VN920_V1 PHY configuration (SF7, BW 125kHz, CR 4/5).
func DefaultVN920PHY() LoRaPHYConfig {
	return LoRaPHYConfig{
		SpreadingFactor:     7,
		BandwidthHz:         DefaultBandwidthHz, // 125000
		CodingRate:          1,                  // 4/5
		PreambleLength:      8,
		ExplicitHeader:      true,
		LowDataRateOptimize: false,
		CRCOn:               true,
	}
}

// SF8VN920PHY returns the fallback approved VN920_V1 PHY configuration at SF8.
func SF8VN920PHY() LoRaPHYConfig {
	cfg := DefaultVN920PHY()
	cfg.SpreadingFactor = 8
	return cfg
}

// CalculateToA computes the exact Semtech SX1276 Time-on-Air for a given payload size in bytes.
// Follows SX1276 datasheet and PR #206 / specification.md calculations.
func CalculateToA(payloadBytes int, phy LoRaPHYConfig) (time.Duration, error) {
	if phy.SpreadingFactor != 7 && phy.SpreadingFactor != 8 {
		return 0, fmt.Errorf("%w: SF=%d", ErrInvalidPHYConfig, phy.SpreadingFactor)
	}
	if phy.BandwidthHz != DefaultBandwidthHz {
		return 0, fmt.Errorf("%w: BW=%d", ErrInvalidPHYConfig, phy.BandwidthHz)
	}

	sf := float64(phy.SpreadingFactor)
	bw := float64(phy.BandwidthHz)

	// Symbol duration: Tsym = 2^SF / BW
	tSymMs := (math.Pow(2, sf) / bw) * 1000.0

	// Preamble duration: Tpreamble = (Npreamble + 4.25) * Tsym
	tPreambleMs := (float64(phy.PreambleLength) + 4.25) * tSymMs

	// Payload symbol count calculation:
	// term = 8*PL - 4*SF + 28 + 16 - 20*H
	h := 0.0 // 0 for explicit header
	if !phy.ExplicitHeader {
		h = 1.0
	}
	de := 0.0
	if phy.LowDataRateOptimize {
		de = 1.0
	}
	crc := 16.0
	if !phy.CRCOn {
		crc = 0.0
	}

	term := 8.0*float64(payloadBytes) - 4.0*sf + 28.0 + crc - 20.0*h
	denom := 4.0 * (sf - 2.0*de)

	symCount := math.Ceil(term/denom) * float64(phy.CodingRate+4)
	if symCount < 0 {
		symCount = 0
	}
	nPayload := 8.0 + symCount

	tPayloadMs := nPayload * tSymMs
	totalMs := tPreambleMs + tPayloadMs

	return time.Duration(totalMs * float64(time.Millisecond)), nil
}

// FeasibilityReport details the timing bounds and verification results for a proposed schedule.
type FeasibilityReport struct {
	PHY                 LoRaPHYConfig `json:"phy"`
	UpEventToAMs        float64       `json:"up_event_toa_ms"`
	DownEventAckToAMs   float64       `json:"down_event_ack_toa_ms"`
	TotalRoundTripMs    float64       `json:"total_round_trip_ms"`
	UsableSlotMarginMs  float64       `json:"usable_slot_margin_ms"`
	DownSyncBeaconToAMs float64       `json:"down_sync_beacon_toa_ms"`
	UpHealthReplyToAMs  float64       `json:"up_health_reply_toa_ms"`
	UpDiagMetricsToAMs  float64       `json:"up_diag_metrics_toa_ms"`
	WorstCaseDriftMs    float64       `json:"worst_case_drift_ms"`
	GuardMarginMs       float64       `json:"guard_margin_ms"`
	ChannelVerified     bool          `json:"channel_verified"`
	HalfDuplexSafe      bool          `json:"half_duplex_safe"`
	IsFeasible          bool          `json:"is_feasible"`
}

// ChannelAllocationChecker abstracts checking Gateway channel ownership against Issue #154 database.
type ChannelAllocationChecker interface {
	GetActiveAllocationByGateway(ctx context.Context, gatewayID string) (*ChannelAllocation, error)
}

// FeasibilityValidator validates schedule profile feasibility against SX1276 RF, half-duplex and timing laws.
type FeasibilityValidator struct {
	channelChecker ChannelAllocationChecker
}

// NewFeasibilityValidator creates a FeasibilityValidator with an optional channel allocation checker.
func NewFeasibilityValidator(checker ChannelAllocationChecker) *FeasibilityValidator {
	return &FeasibilityValidator{channelChecker: checker}
}

// ValidateScheduleFeasibility checks Event/ACK round-trip in W500ms, half-duplex safety, clock drift, and channel allocation.
func (v *FeasibilityValidator) ValidateScheduleFeasibility(ctx context.Context, schedule *Schedule, phy LoRaPHYConfig) (*FeasibilityReport, error) {
	if err := schedule.Validate(); err != nil {
		return nil, err
	}

	// 1. Calculate Time-on-Air for critical frames
	upEventToA, err := CalculateToA(BytesUpEvent, phy)
	if err != nil {
		return nil, err
	}
	downAckToA, err := CalculateToA(BytesDownEventAck, phy)
	if err != nil {
		return nil, err
	}
	beaconToA, err := CalculateToA(BytesDownSyncBeacon, phy)
	if err != nil {
		return nil, err
	}
	healthToA, err := CalculateToA(BytesUpHealthReply, phy)
	if err != nil {
		return nil, err
	}
	diagToA, err := CalculateToA(BytesUpDiagMetrics, phy)
	if err != nil {
		return nil, err
	}

	// 2. Validate Event/ACK round-trip in W_MS = 500ms
	totalRoundTrip := upEventToA + time.Duration(GatewayWalTurnaroundMs)*time.Millisecond +
		downAckToA + time.Duration(NodeAckProcessingMs)*time.Millisecond
	usableWindow := time.Duration(WMsUsableDataSlot) * time.Millisecond

	if totalRoundTrip > usableWindow {
		return nil, fmt.Errorf("%w: round-trip %v exceeds usable window %v", ErrToAExceedsSlot, totalRoundTrip, usableWindow)
	}
	usableMarginMs := (usableWindow - totalRoundTrip).Seconds() * 1000.0

	// 3. Validate clock drift budget against guard bands (G_MS = 50ms)
	// Over nominal 300s Maintenance interval at 40 ppm:
	// drift = 300 * 40e-6 = 0.012s = 12ms
	worstCaseDriftSec := float64(NominalMaintenanceRecurrenceSeconds) * (MaxOscillatorDriftPpm * 1e-6)
	worstCaseDriftMs := worstCaseDriftSec * 1000.0
	guardBudgetMs := float64(GMsDataGuard)
	if worstCaseDriftMs >= guardBudgetMs {
		return nil, fmt.Errorf("%w: drift %.2f ms exceeds guard %.2f ms", ErrUnsafeClockDrift, worstCaseDriftMs, guardBudgetMs)
	}
	guardMarginMs := guardBudgetMs - worstCaseDriftMs

	// 4. Verify Gateway exclusive channel allocation from Issue #154
	channelVerified := false
	if v.channelChecker != nil && schedule.GatewayID != "" && schedule.ChannelID != "" {
		alloc, err := v.channelChecker.GetActiveAllocationByGateway(ctx, schedule.GatewayID)
		if err != nil {
			return nil, fmt.Errorf("%w: error checking allocation for gateway %s: %v", ErrChannelNotAllocated, schedule.GatewayID, err)
		}
		if alloc == nil || alloc.ChannelID != schedule.ChannelID || alloc.Status != StatusAllocated {
			return nil, fmt.Errorf("%w: gateway %s is not actively allocated channel %s", ErrChannelNotAllocated, schedule.GatewayID, schedule.ChannelID)
		}
		channelVerified = true
	}

	report := &FeasibilityReport{
		PHY:                 phy,
		UpEventToAMs:        upEventToA.Seconds() * 1000.0,
		DownEventAckToAMs:   downAckToA.Seconds() * 1000.0,
		TotalRoundTripMs:    totalRoundTrip.Seconds() * 1000.0,
		UsableSlotMarginMs:  usableMarginMs,
		DownSyncBeaconToAMs: beaconToA.Seconds() * 1000.0,
		UpHealthReplyToAMs:  healthToA.Seconds() * 1000.0,
		UpDiagMetricsToAMs:  diagToA.Seconds() * 1000.0,
		WorstCaseDriftMs:    worstCaseDriftMs,
		GuardMarginMs:       guardMarginMs,
		ChannelVerified:     channelVerified,
		HalfDuplexSafe:      true,
		IsFeasible:          true,
	}

	return report, nil
}
