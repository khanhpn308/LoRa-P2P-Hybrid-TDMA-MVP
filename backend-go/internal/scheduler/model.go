package scheduler

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"regexp"
	"time"
)

// Owner-approved V2 TDMA schedule profile constants (Issue #19, #125, #127, #206, #208).
const (
	// ProfileV2VN920Static15N is the Owner-approved MVP baseline profile:
	// Static DATA superframe with W_MS=500, G_MS=50, 15 reserved node positions (9000ms data region).
	ProfileV2VN920Static15N = "V2-VN920-STATIC-15N"

	// ProfileP10S15 is the historical candidate profile (marked OBSOLETE_HISTORICAL_BASELINE per PR #206).
	ProfileP10S15 = "P-10S-15"

	// WMsUsableDataSlot is the usable Event + ACK window duration in milliseconds.
	WMsUsableDataSlot = 500

	// GMsDataGuard is the leading and trailing guard time each side in milliseconds.
	GMsDataGuard = 50

	// FullDataSlotMs is the total reserved time per node slot in milliseconds (W_MS + 2*G_MS).
	FullDataSlotMs = WMsUsableDataSlot + 2*GMsDataGuard // 600 ms

	// MaxNodeCapacity is the maximum number of reserved node positions in MVP (1..15).
	MaxNodeCapacity = 15

	// TotalDataRegionMs is the total reserved duration of all 15 node positions in milliseconds.
	TotalDataRegionMs = MaxNodeCapacity * FullDataSlotMs // 9000 ms

	// RMsUsableReadySlot is the usable on-demand READY slot duration in milliseconds.
	RMsUsableReadySlot = 400

	// GRMsReadyGuard is the leading and trailing guard time for READY slots in milliseconds.
	GRMsReadyGuard = 50

	// FullReadySlotMs is the total reserved time per READY slot in milliseconds (R_MS + 2*G_R_MS).
	FullReadySlotMs = RMsUsableReadySlot + 2*GRMsReadyGuard // 500 ms

	// TotalReadyRegionMs is the total duration of 15 READY positions in milliseconds.
	TotalReadyRegionMs = MaxNodeCapacity * FullReadySlotMs // 7500 ms

	// NominalMaintenanceRecurrenceSeconds is the nominal interval between maintenance opportunities.
	NominalMaintenanceRecurrenceSeconds = 300

	// MinAnnounceSuperframesDefault is the default minimum number of complete beacon announcement superframes.
	MinAnnounceSuperframesDefault = 3

	// DefaultSchemaVersion matches the schedule contract schema version.
	DefaultSchemaVersion = "1.0-draft"
)

// Candidate RF wire message types (pending #127 canonical registration).
const (
	TypeDownSchedPrepare  uint8 = 0x4B // Candidate 80B broadcast
	TypeUpSchedReady      uint8 = 0x4C // Approved 41B unicast
	TypeDownSchedDecision uint8 = 0x4D // Candidate 80B broadcast (COMMIT/ABORT)
)

// Migration decision types.
const (
	DecisionAbort  uint8 = 0
	DecisionCommit uint8 = 1
)

// Node execution states after reboot or reconciliation.
const (
	NodeStateActive          = "ACTIVE"
	NodeStateRebootRxOnly    = "REBOOT_RX_ONLY"   // DATA_TX_DISABLED until authenticated reconciliation
	NodeStateBlockedContract = "BLOCKED_CONTRACT" // Resume message contract pending #127
	NodeStateSuspended       = "SUSPENDED"
)

// Domain validation errors.
var (
	ErrInvalidGatewayID      = errors.New("invalid gateway id: must match ^[A-Za-z0-9_-]{1,32}$")
	ErrInvalidChannelID      = errors.New("invalid channel id: must be approved VN920_V1 channel (CH00..CH10)")
	ErrInvalidProfileID      = errors.New("unsupported profile id: only V2-VN920-STATIC-15N is approved for MVP")
	ErrInvalidNodeID         = errors.New("invalid node id: must be between 1 and 15")
	ErrInvalidSlotID         = errors.New("invalid slot id: slot_id must equal node_id in MVP static schedule")
	ErrDuplicateNodeID       = errors.New("duplicate node id in schedule membership")
	ErrEmptyNodeMembership   = errors.New("schedule membership cannot be empty")
	ErrSlotCapacityExceeded  = errors.New("node capacity exceeded: maximum 15 nodes")
	ErrSlotOverlap           = errors.New("slot timing overlaps another reserved slot")
	ErrInvalidSlotDuration   = errors.New("invalid slot duration: usable duration must be 500 ms")
	ErrInvalidExpiryOrdering = errors.New("invalid expiry ordering: created_at must be before expires_at")
	ErrInvalidSuperframeMs   = errors.New("invalid superframe duration: must be 9000 ms for V2-VN920-STATIC-15N")
	ErrSlotOutOfBounds       = errors.New("slot offset exceeds total reserved data region boundary")
	ErrStaleScheduleVersion  = errors.New("schedule version must be strictly greater than current active version")
	ErrStaleGeneration       = errors.New("schedule generation must be strictly greater than current active generation")
)

var gatewayIDRegex = regexp.MustCompile(`^[A-Za-z0-9_-]{1,32}$`)
var scheduleIDRegex = regexp.MustCompile(`^(0|[1-9][0-9]{0,19})$`)

// SlotGeometry calculates the precise millisecond offsets for a static DATA slot (1..15).
// Invariant: NODE_ID == SLOT_INDEX (1..15).
// reserved_start(i) = DATA_ORIGIN + (i-1)*600ms
// usable_start(i)   = reserved_start(i) + 50ms
// usable_end(i)     = usable_start(i) + 500ms
// reserved_end(i)   = reserved_start(i) + 600ms
func SlotGeometry(slotIndex uint8, originOffsetMs int) (reservedStartMs, usableStartMs, usableEndMs, reservedEndMs int, err error) {
	if slotIndex < 1 || slotIndex > MaxNodeCapacity {
		return 0, 0, 0, 0, fmt.Errorf("%w: got %d", ErrInvalidNodeID, slotIndex)
	}
	base := originOffsetMs + int(slotIndex-1)*FullDataSlotMs
	reservedStartMs = base
	usableStartMs = base + GMsDataGuard
	usableEndMs = usableStartMs + WMsUsableDataSlot
	reservedEndMs = base + FullDataSlotMs
	return reservedStartMs, usableStartMs, usableEndMs, reservedEndMs, nil
}

// ReadyGeometry calculates the precise millisecond offsets for an on-demand READY slot (1..15).
// Invariant: R_MS = 400ms, G_R_MS = 50ms each side => 500ms full slot.
// ready_start(i)  = T_READY_BASE + (i-1)*500ms + 50ms
// ready_end(i)    = ready_start(i) + 400ms
func ReadyGeometry(slotIndex uint8, baseOffsetMs int) (reservedStartMs, usableStartMs, usableEndMs, reservedEndMs int, err error) {
	if slotIndex < 1 || slotIndex > MaxNodeCapacity {
		return 0, 0, 0, 0, fmt.Errorf("%w: got %d", ErrInvalidNodeID, slotIndex)
	}
	base := baseOffsetMs + int(slotIndex-1)*FullReadySlotMs
	reservedStartMs = base
	usableStartMs = base + GRMsReadyGuard
	usableEndMs = usableStartMs + RMsUsableReadySlot
	reservedEndMs = base + FullReadySlotMs
	return reservedStartMs, usableStartMs, usableEndMs, reservedEndMs, nil
}

// SlotConfig describes an individual reserved slot within the schedule contract.
type SlotConfig struct {
	NodeID     uint8 `json:"node_id"`
	SlotID     uint8 `json:"slot_id"`
	OffsetMs   int   `json:"offset_ms"`
	DurationMs int   `json:"duration_ms"`
}

// Schedule represents a versioned static TDMA schedule proposal.
type Schedule struct {
	SchemaVersion          string       `json:"schema_version"`
	RequestID              string       `json:"request_id"`
	GatewayID              string       `json:"gateway_id"`
	ScheduleID             string       `json:"schedule_id"`
	ScheduleVersion        uint32       `json:"schedule_version"`
	ScheduleGeneration     uint32       `json:"schedule_generation"`
	CreatedAt              time.Time    `json:"created_at"`
	ExpiresAt              time.Time    `json:"expires_at"`
	ProfileID              string       `json:"profile_id"`
	SuperframeMs           int          `json:"superframe_ms"`
	MinAnnounceSuperframes int          `json:"min_announce_superframes"`
	ChannelID              string       `json:"channel_id"`
	NetworkID              uint32       `json:"network_id"`
	Slots                  []SlotConfig `json:"slots"`
	AffectedNodeSet        []uint8      `json:"affected_node_set"`
}

// Validate performs strict validation of schedule invariants against contract schema and TDMA specifications.
func (s *Schedule) Validate() error {
	if !gatewayIDRegex.MatchString(s.GatewayID) {
		return fmt.Errorf("%w: %q", ErrInvalidGatewayID, s.GatewayID)
	}
	if !scheduleIDRegex.MatchString(s.ScheduleID) {
		return fmt.Errorf("invalid schedule_id format: %q", s.ScheduleID)
	}
	if s.ProfileID != ProfileV2VN920Static15N {
		return fmt.Errorf("%w: %q", ErrInvalidProfileID, s.ProfileID)
	}
	if s.SuperframeMs != TotalDataRegionMs {
		return fmt.Errorf("%w: expected %d, got %d", ErrInvalidSuperframeMs, TotalDataRegionMs, s.SuperframeMs)
	}
	if !s.CreatedAt.Before(s.ExpiresAt) {
		return ErrInvalidExpiryOrdering
	}
	if s.MinAnnounceSuperframes < MinAnnounceSuperframesDefault || s.MinAnnounceSuperframes > 30 {
		return fmt.Errorf("min_announce_superframes must be 3..30, got %d", s.MinAnnounceSuperframes)
	}
	if len(s.Slots) == 0 {
		return ErrEmptyNodeMembership
	}
	if len(s.Slots) > MaxNodeCapacity {
		return ErrSlotCapacityExceeded
	}

	seenNodes := make(map[uint8]bool, len(s.Slots))
	seenSlots := make(map[uint8]bool, len(s.Slots))

	for _, slot := range s.Slots {
		if slot.NodeID < 1 || slot.NodeID > MaxNodeCapacity {
			return fmt.Errorf("%w: got %d", ErrInvalidNodeID, slot.NodeID)
		}
		if slot.SlotID != slot.NodeID {
			return fmt.Errorf("%w: slot_id=%d != node_id=%d", ErrInvalidSlotID, slot.SlotID, slot.NodeID)
		}
		if seenNodes[slot.NodeID] {
			return fmt.Errorf("%w: node_id=%d", ErrDuplicateNodeID, slot.NodeID)
		}
		if seenSlots[slot.SlotID] {
			return fmt.Errorf("duplicate slot_id: %d", slot.SlotID)
		}
		seenNodes[slot.NodeID] = true
		seenSlots[slot.SlotID] = true

		if slot.DurationMs != WMsUsableDataSlot {
			return fmt.Errorf("%w: expected %d ms, got %d ms", ErrInvalidSlotDuration, WMsUsableDataSlot, slot.DurationMs)
		}

		// Verify geometric alignment: offset_ms must match usable_start
		_, expectedUsableStart, expectedUsableEnd, _, err := SlotGeometry(slot.NodeID, 0)
		if err != nil {
			return err
		}
		if slot.OffsetMs != expectedUsableStart {
			return fmt.Errorf("misaligned slot offset for node %d: expected %d ms, got %d ms",
				slot.NodeID, expectedUsableStart, slot.OffsetMs)
		}
		if expectedUsableEnd > TotalDataRegionMs {
			return ErrSlotOutOfBounds
		}
	}

	return nil
}

// GenerateRandomRequestID generates a standard UUID v4 string.
func GenerateRandomRequestID() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	b[6] = (b[6] & 0x0f) | 0x40 // Version 4
	b[8] = (b[8] & 0x3f) | 0x80 // RFC 4122 variant
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16]), nil
}

// GenerateRandomID generates a hex string of given length.
func GenerateRandomID(bytes int) string {
	b := make([]byte, bytes)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
