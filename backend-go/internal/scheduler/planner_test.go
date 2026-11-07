package scheduler_test

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

func TestPlannerFull15Nodes(t *testing.T) {
	checker := &mockChannelChecker{
		allocations: map[string]*scheduler.ChannelAllocation{
			"gw01": {
				GatewayID: "gw01",
				ChannelID: "CH00",
				Status:    scheduler.StatusAllocated,
			},
		},
	}
	planner := scheduler.NewPlanner(scheduler.NewFeasibilityValidator(checker))

	all15Nodes := []uint8{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}
	req := scheduler.PlanRequest{
		GatewayID:              "gw01",
		NetworkID:              1,
		ChannelID:              "CH00",
		ScheduleVersion:        1,
		ScheduleGeneration:     1,
		ActiveNodeIDs:          all15Nodes,
		BaseTime:               time.Now().UTC(),
		ValidityTTL:            10 * time.Minute,
		MinAnnounceSuperframes: 3,
		PHY:                    scheduler.DefaultVN920PHY(),
	}

	res, err := planner.Plan(context.Background(), req)
	if err != nil {
		t.Fatalf("failed to plan 15-node schedule: %v", err)
	}

	if len(res.Schedule.Slots) != 15 {
		t.Fatalf("expected 15 slots, got %d", len(res.Schedule.Slots))
	}
	if res.Schedule.SuperframeMs != 9000 {
		t.Errorf("expected 9000ms superframe, got %d", res.Schedule.SuperframeMs)
	}

	for i, slot := range res.Schedule.Slots {
		expectedNodeID := uint8(i + 1)
		if slot.NodeID != expectedNodeID {
			t.Errorf("slot %d: expected node_id=%d, got %d", i, expectedNodeID, slot.NodeID)
		}
		if slot.SlotID != expectedNodeID {
			t.Errorf("slot %d: expected slot_id=%d, got %d", i, expectedNodeID, slot.SlotID)
		}
		if slot.DurationMs != 500 {
			t.Errorf("slot %d: expected duration 500ms, got %d", i, slot.DurationMs)
		}
		expectedOffset := (int(expectedNodeID)-1)*600 + 50
		if slot.OffsetMs != expectedOffset {
			t.Errorf("slot %d: expected offset %d, got %d", i, expectedOffset, slot.OffsetMs)
		}
	}
}

func TestPlannerSparseMembershipNonCompacting(t *testing.T) {
	checker := &mockChannelChecker{
		allocations: map[string]*scheduler.ChannelAllocation{
			"gw01": {
				GatewayID: "gw01",
				ChannelID: "CH00",
				Status:    scheduler.StatusAllocated,
			},
		},
	}
	planner := scheduler.NewPlanner(scheduler.NewFeasibilityValidator(checker))

	// Sparse membership: only nodes 1, 5, 12
	sparseNodes := []uint8{12, 1, 5} // Unordered to test deterministic sorting
	req := scheduler.PlanRequest{
		GatewayID:              "gw01",
		NetworkID:              1,
		ChannelID:              "CH00",
		ScheduleVersion:        2,
		ScheduleGeneration:     2,
		ActiveNodeIDs:          sparseNodes,
		BaseTime:               time.Now().UTC(),
		ValidityTTL:            10 * time.Minute,
		MinAnnounceSuperframes: 3,
		PHY:                    scheduler.DefaultVN920PHY(),
	}

	res, err := planner.Plan(context.Background(), req)
	if err != nil {
		t.Fatalf("failed to plan sparse schedule: %v", err)
	}

	if len(res.Schedule.Slots) != 3 {
		t.Fatalf("expected 3 active slots, got %d", len(res.Schedule.Slots))
	}

	// Verify that slots are NOT compacted:
	// Node 1 offset = 50ms
	// Node 5 offset = (5-1)*600 + 50 = 2450ms (not compacted to 650ms!)
	// Node 12 offset = (12-1)*600 + 50 = 6650ms (not compacted to 1250ms!)
	expectedOffsets := map[uint8]int{
		1:  50,
		5:  2450,
		12: 6650,
	}

	for _, slot := range res.Schedule.Slots {
		expectedOffset, ok := expectedOffsets[slot.NodeID]
		if !ok {
			t.Errorf("unexpected node %d in slots", slot.NodeID)
		}
		if slot.OffsetMs != expectedOffset {
			t.Errorf("node %d slot offset was compacted or miscalculated: expected %d, got %d",
				slot.NodeID, expectedOffset, slot.OffsetMs)
		}
		if slot.SlotID != slot.NodeID {
			t.Errorf("node %d has mismatching slot_id %d", slot.NodeID, slot.SlotID)
		}
	}
}

func TestPlannerInvalidMemberships(t *testing.T) {
	checker := &mockChannelChecker{
		allocations: map[string]*scheduler.ChannelAllocation{
			"gw01": {
				GatewayID: "gw01",
				ChannelID: "CH00",
				Status:    scheduler.StatusAllocated,
			},
		},
	}
	planner := scheduler.NewPlanner(scheduler.NewFeasibilityValidator(checker))

	baseReq := scheduler.PlanRequest{
		GatewayID:              "gw01",
		NetworkID:              1,
		ChannelID:              "CH00",
		ScheduleVersion:        1,
		ScheduleGeneration:     1,
		BaseTime:               time.Now().UTC(),
		ValidityTTL:            10 * time.Minute,
		MinAnnounceSuperframes: 3,
		PHY:                    scheduler.DefaultVN920PHY(),
	}

	// Empty membership
	reqEmpty := baseReq
	reqEmpty.ActiveNodeIDs = []uint8{}
	if _, err := planner.Plan(context.Background(), reqEmpty); err == nil {
		t.Errorf("expected error for empty active nodes")
	}

	// Node ID 0 out of bounds
	reqZero := baseReq
	reqZero.ActiveNodeIDs = []uint8{0, 1}
	if _, err := planner.Plan(context.Background(), reqZero); err == nil {
		t.Errorf("expected error for node_id 0")
	}

	// Node ID 16 out of bounds
	reqSixteen := baseReq
	reqSixteen.ActiveNodeIDs = []uint8{1, 16}
	if _, err := planner.Plan(context.Background(), reqSixteen); err == nil {
		t.Errorf("expected error for node_id 16")
	}

	// Duplicate node ID
	reqDup := baseReq
	reqDup.ActiveNodeIDs = []uint8{1, 2, 1}
	if _, err := planner.Plan(context.Background(), reqDup); err == nil {
		t.Errorf("expected error for duplicate node ID")
	}
}

func TestPlannerConcurrency(t *testing.T) {
	checker := &mockChannelChecker{
		allocations: map[string]*scheduler.ChannelAllocation{
			"gw01": {
				GatewayID: "gw01",
				ChannelID: "CH00",
				Status:    scheduler.StatusAllocated,
			},
		},
	}
	planner := scheduler.NewPlanner(scheduler.NewFeasibilityValidator(checker))

	var wg sync.WaitGroup
	errCh := make(chan error, 20)

	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func(version int) {
			defer wg.Done()
			req := scheduler.PlanRequest{
				GatewayID:              "gw01",
				NetworkID:              1,
				ChannelID:              "CH00",
				ScheduleVersion:        uint32(version + 1),
				ScheduleGeneration:     uint32(version + 1),
				ActiveNodeIDs:          []uint8{1, 2, 3, 4},
				BaseTime:               time.Now().UTC(),
				ValidityTTL:            10 * time.Minute,
				MinAnnounceSuperframes: 3,
				PHY:                    scheduler.DefaultVN920PHY(),
			}
			_, err := planner.Plan(context.Background(), req)
			if err != nil {
				errCh <- err
			}
		}(i)
	}

	wg.Wait()
	close(errCh)

	for err := range errCh {
		t.Fatalf("concurrent planning failed: %v", err)
	}
}
