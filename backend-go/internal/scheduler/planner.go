package scheduler

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"sort"
	"time"
)

var (
	ErrNodeIDOutOfRange = errors.New("node ID out of range: must be 1..15")
	ErrNoChannelPlan    = errors.New("channel must be specified and part of approved VN920_V1 catalogue")
)

var channelIDRegex = regexp.MustCompile(`^CH(?:0[0-9]|10)$`)

func validateGatewayID(id string) error {
	if !gatewayIDRegex.MatchString(id) {
		return errors.New("invalid gateway id")
	}
	return nil
}

func validateChannelID(id string) error {
	if !channelIDRegex.MatchString(id) {
		return errors.New("invalid channel id")
	}
	return nil
}

// PlanRequest encapsulates deterministic input parameters for TDMA schedule planning.
type PlanRequest struct {
	GatewayID              string
	NetworkID              uint32
	ChannelID              string
	ScheduleVersion        uint32
	ScheduleGeneration     uint32
	ActiveNodeIDs          []uint8
	BaseTime               time.Time
	ValidityTTL            time.Duration
	MinAnnounceSuperframes int
	PHY                    LoRaPHYConfig
}

// PlanResult encapsulates the planned schedule and feasibility analysis report.
type PlanResult struct {
	Schedule          *Schedule          `json:"schedule"`
	FeasibilityReport *FeasibilityReport `json:"feasibility_report"`
	AffectedNodeSet   []uint8            `json:"affected_node_set"`
}

// Planner constructs deterministic, collision-free V2 static TDMA schedules.
type Planner struct {
	validator *FeasibilityValidator
}

// NewPlanner creates a new Planner with the given feasibility validator.
func NewPlanner(validator *FeasibilityValidator) *Planner {
	if validator == nil {
		validator = NewFeasibilityValidator(nil)
	}
	return &Planner{validator: validator}
}

// Plan computes a deterministic TDMA schedule strictly preserving fixed slot positions.
// Empty/offline slots are never compacted (NODE_ID == SLOT_INDEX invariant).
func (p *Planner) Plan(ctx context.Context, req PlanRequest) (*PlanResult, error) {
	if err := validateGatewayID(req.GatewayID); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidGatewayID, err)
	}
	if err := validateChannelID(req.ChannelID); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidChannelID, err)
	}
	if len(req.ActiveNodeIDs) == 0 {
		return nil, ErrEmptyNodeMembership
	}
	if len(req.ActiveNodeIDs) > MaxNodeCapacity {
		return nil, ErrSlotCapacityExceeded
	}

	// Validate and sort active node set (deduplicate and verify 1..15)
	seen := make(map[uint8]bool, len(req.ActiveNodeIDs))
	affectedNodes := make([]uint8, 0, len(req.ActiveNodeIDs))
	for _, nid := range req.ActiveNodeIDs {
		if nid < 1 || nid > MaxNodeCapacity {
			return nil, fmt.Errorf("%w: got %d", ErrNodeIDOutOfRange, nid)
		}
		if seen[nid] {
			return nil, fmt.Errorf("%w: node_id=%d", ErrDuplicateNodeID, nid)
		}
		seen[nid] = true
		affectedNodes = append(affectedNodes, nid)
	}
	sort.Slice(affectedNodes, func(i, j int) bool { return affectedNodes[i] < affectedNodes[j] })

	// Calculate deterministic slots with fixed positions
	slots := make([]SlotConfig, 0, len(affectedNodes))
	for _, nid := range affectedNodes {
		_, usableStart, _, _, err := SlotGeometry(nid, 0)
		if err != nil {
			return nil, err
		}
		slots = append(slots, SlotConfig{
			NodeID:     nid,
			SlotID:     nid, // Invariant: slot_id == node_id
			OffsetMs:   usableStart,
			DurationMs: WMsUsableDataSlot,
		})
	}

	createdAt := req.BaseTime
	if createdAt.IsZero() {
		createdAt = time.Now().UTC()
	}
	ttl := req.ValidityTTL
	if ttl <= 0 {
		ttl = 10 * time.Minute
	}
	expiresAt := createdAt.Add(ttl)

	minAnnounce := req.MinAnnounceSuperframes
	if minAnnounce < MinAnnounceSuperframesDefault {
		minAnnounce = MinAnnounceSuperframesDefault
	}

	schedID := fmt.Sprintf("%d", req.ScheduleVersion)
	reqID, err := GenerateRandomRequestID()
	if err != nil {
		return nil, err
	}

	sched := &Schedule{
		SchemaVersion:          DefaultSchemaVersion,
		RequestID:              reqID,
		GatewayID:              req.GatewayID,
		ScheduleID:             schedID,
		ScheduleVersion:        req.ScheduleVersion,
		ScheduleGeneration:     req.ScheduleGeneration,
		CreatedAt:              createdAt,
		ExpiresAt:              expiresAt,
		ProfileID:              ProfileV2VN920Static15N,
		SuperframeMs:           TotalDataRegionMs, // 9000 ms
		MinAnnounceSuperframes: minAnnounce,
		ChannelID:              req.ChannelID,
		NetworkID:              req.NetworkID,
		Slots:                  slots,
		AffectedNodeSet:        affectedNodes,
	}

	// Validate structural invariants
	if err := sched.Validate(); err != nil {
		return nil, err
	}

	// Validate RF & channel feasibility
	phy := req.PHY
	if phy.SpreadingFactor == 0 {
		phy = DefaultVN920PHY()
	}
	report, err := p.validator.ValidateScheduleFeasibility(ctx, sched, phy)
	if err != nil {
		return nil, fmt.Errorf("schedule feasibility check failed: %w", err)
	}

	return &PlanResult{
		Schedule:          sched,
		FeasibilityReport: report,
		AffectedNodeSet:   affectedNodes,
	}, nil
}
