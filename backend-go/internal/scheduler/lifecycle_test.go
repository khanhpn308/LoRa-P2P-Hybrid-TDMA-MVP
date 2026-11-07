package scheduler_test

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

func setupLifecycleEngine(t *testing.T) (*scheduler.LifecycleEngine, *scheduler.MemoryScheduleRepository, map[uint8][]byte) {
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	nodeKeys := map[uint8][]byte{
		1: []byte("node-1-key-thirty-two-bytes-1234"),
		2: []byte("node-2-key-thirty-two-bytes-1234"),
	}
	keyDir := scheduler.NewMapNodeKeyDirectory(nodeKeys)
	signer, err := scheduler.NewScheduleSigner(priv, keyDir)
	if err != nil {
		t.Fatalf("failed to create signer: %v", err)
	}

	checker := &mockChannelChecker{
		allocations: map[string]*scheduler.ChannelAllocation{
			"gw01": {
				GatewayID: "gw01",
				ChannelID: "CH00",
				Status:    scheduler.StatusAllocated,
			},
		},
	}
	validator := scheduler.NewFeasibilityValidator(checker)
	planner := scheduler.NewPlanner(validator)
	repo := scheduler.NewMemoryScheduleRepository()

	engine := scheduler.NewLifecycleEngine(repo, signer, planner)
	return engine, repo, nodeKeys
}

func TestLifecycleHappyPath(t *testing.T) {
	engine, repo, nodeKeys := setupLifecycleEngine(t)
	ctx := context.Background()

	// 1. Start Migration
	planReq := scheduler.PlanRequest{
		GatewayID:              "gw01",
		NetworkID:              1,
		ChannelID:              "CH00",
		ScheduleVersion:        1,
		ScheduleGeneration:     1,
		ActiveNodeIDs:          []uint8{1, 2},
		BaseTime:               time.Now().UTC(),
		ValidityTTL:            10 * time.Minute,
		MinAnnounceSuperframes: 3,
		PHY:                    scheduler.DefaultVN920PHY(),
	}

	kTarget := uint32(500)
	tx, prepTx, err := engine.StartMigration(ctx, planReq, kTarget)
	if err != nil {
		t.Fatalf("failed to start migration: %v", err)
	}
	if tx.State != scheduler.StatePrepared {
		t.Errorf("expected state PREPARED, got %s", tx.State)
	}

	// 2. Gateway STAGE_ACK
	err = engine.HandleScheduleAck(ctx, scheduler.StageAckReport{
		EventID:         "gw01:epoch-1:1",
		GatewayID:       "gw01",
		ScheduleID:      tx.ScheduleID,
		ScheduleVersion: 1,
		Stage:           "STAGE_ACK",
	})
	if err != nil {
		t.Fatalf("STAGE_ACK failed: %v", err)
	}

	// Invariant: STAGE_ACK must NOT promote schedule to ACTIVE!
	active, err := repo.GetActiveScheduleByGateway(ctx, "gw01")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if active != nil {
		t.Fatalf("schedule must NOT become active on STAGE_ACK")
	}

	// 3. Ingest UP_SCHED_READY proof for Node 1
	proof1 := scheduler.ComputeNodeReadyProof(nodeKeys[1], prepTx.PrepareDigest, 1, kTarget, 1)
	err = engine.IngestReadyProof(ctx, tx.TransactionID, scheduler.NodeReadyProofInput{
		NodeID:             1,
		SessionSel:         1,
		FrameCounter:       10,
		ScheduleGeneration: 1,
		KTarget:            kTarget,
		Status:             1,
		Reason:             0,
		Proof:              proof1,
	})
	if err != nil {
		t.Fatalf("failed to ingest node 1 proof: %v", err)
	}

	// Barrier is 1/2 complete; COMMIT must fail
	if _, err := engine.CommitMigration(ctx, tx.TransactionID, time.Now().UTC()); err == nil {
		t.Errorf("expected error committing with only 1/2 nodes verified")
	}

	// 4. Ingest UP_SCHED_READY proof for Node 2 (100% barrier complete)
	proof2 := scheduler.ComputeNodeReadyProof(nodeKeys[2], prepTx.PrepareDigest, 1, kTarget, 2)
	err = engine.IngestReadyProof(ctx, tx.TransactionID, scheduler.NodeReadyProofInput{
		NodeID:             2,
		SessionSel:         1,
		FrameCounter:       11,
		ScheduleGeneration: 1,
		KTarget:            kTarget,
		Status:             1,
		Reason:             0,
		Proof:              proof2,
	})
	if err != nil {
		t.Fatalf("failed to ingest node 2 proof: %v", err)
	}

	// 5. Commit Migration (signs DOWN_SCHED_DECISION COMMIT 0x4D, 80B)
	decTx, err := engine.CommitMigration(ctx, tx.TransactionID, time.Now().UTC())
	if err != nil {
		t.Fatalf("failed to commit migration: %v", err)
	}
	if decTx.DecisionType != scheduler.DecisionCommit {
		t.Errorf("expected COMMIT decision")
	}

	// Invariant: Cannot issue second decision for same transaction
	if _, err := engine.CommitMigration(ctx, tx.TransactionID, time.Now().UTC()); err == nil {
		t.Errorf("expected error on duplicate commit")
	}

	// 6. Gateway ACTIVE_REPORT at superframe 500
	superframeSeq := uint32(500)
	err = engine.HandleScheduleAck(ctx, scheduler.StageAckReport{
		EventID:                  "gw01:epoch-1:2",
		GatewayID:                "gw01",
		ScheduleID:               tx.ScheduleID,
		ScheduleVersion:          1,
		Stage:                    "ACTIVE_REPORT",
		ActivatedAtSuperframeSeq: &superframeSeq,
	})
	if err != nil {
		t.Fatalf("ACTIVE_REPORT failed: %v", err)
	}

	// Verify schedule is now ACTIVE in repository
	active, err = repo.GetActiveScheduleByGateway(ctx, "gw01")
	if err != nil || active == nil {
		t.Fatalf("expected active schedule in repository: %v", err)
	}
	if active.ScheduleID != tx.ScheduleID || active.SuperframeSeq != 500 {
		t.Errorf("active schedule state mismatch: %+v", active)
	}

	// 7. Test anti-rollback: An out-of-order STAGE_ACK does NOT downgrade ACTIVE state!
	err = engine.HandleScheduleAck(ctx, scheduler.StageAckReport{
		EventID:         "gw01:epoch-1:3",
		GatewayID:       "gw01",
		ScheduleID:      tx.ScheduleID,
		ScheduleVersion: 1,
		Stage:           "STAGE_ACK",
	})
	if err != nil {
		t.Fatalf("out-of-order STAGE_ACK should be handled cleanly: %v", err)
	}
	activeAfter, _ := repo.GetActiveScheduleByGateway(ctx, "gw01")
	if activeAfter == nil || activeAfter.ScheduleID != tx.ScheduleID {
		t.Errorf("out-of-order STAGE_ACK rolled back or destroyed active state!")
	}

	// 8. Test channel change guard: Gateway cannot change or release channel while schedule is active
	if err := engine.CanChangeGatewayChannel(ctx, "gw01"); err == nil {
		t.Errorf("expected error changing channel when gateway holds active schedule")
	}
}

func TestLifecycleAbortFlow(t *testing.T) {
	engine, _, _ := setupLifecycleEngine(t)
	ctx := context.Background()

	planReq := scheduler.PlanRequest{
		GatewayID:              "gw01",
		NetworkID:              1,
		ChannelID:              "CH00",
		ScheduleVersion:        1,
		ScheduleGeneration:     1,
		ActiveNodeIDs:          []uint8{1, 2},
		BaseTime:               time.Now().UTC(),
		ValidityTTL:            10 * time.Minute,
		MinAnnounceSuperframes: 3,
		PHY:                    scheduler.DefaultVN920PHY(),
	}

	tx, _, err := engine.StartMigration(ctx, planReq, 100)
	if err != nil {
		t.Fatalf("failed to start migration: %v", err)
	}

	// Abort due to node timeout or CAD collision
	decTx, err := engine.AbortMigration(ctx, tx.TransactionID, "CAD collision during READY window")
	if err != nil {
		t.Fatalf("failed to abort migration: %v", err)
	}
	if decTx.DecisionType != scheduler.DecisionAbort {
		t.Errorf("expected ABORT decision")
	}

	// Attempting to commit an aborted transaction fails
	if _, err := engine.CommitMigration(ctx, tx.TransactionID, time.Now().UTC()); err == nil {
		t.Errorf("expected error committing aborted transaction")
	}
}

func TestLifecycleNodeRebootFailClosed(t *testing.T) {
	engine, _, _ := setupLifecycleEngine(t)

	// Node 1 reboots
	engine.RecordNodeReboot(1, time.Now().UTC())

	// Invariant: Node must be in RX_ONLY state
	state := engine.GetNodeExecutionState(1)
	if state != scheduler.NodeStateRebootRxOnly {
		t.Errorf("expected node to be in REBOOT_RX_ONLY, got %s", state)
	}

	// Reconcile without resume contract marks BLOCKED_CONTRACT
	err := engine.ReconcileRebootedNode(1, false)
	if err == nil {
		t.Errorf("expected error when resume wire contract is unavailable")
	}
	state = engine.GetNodeExecutionState(1)
	if state != scheduler.NodeStateBlockedContract {
		t.Errorf("expected BLOCKED_CONTRACT, got %s", state)
	}

	// Reconcile when contract is available restores ACTIVE
	err = engine.ReconcileRebootedNode(1, true)
	if err != nil {
		t.Fatalf("unexpected error reconciling with available contract: %v", err)
	}
	state = engine.GetNodeExecutionState(1)
	if state != scheduler.NodeStateActive {
		t.Errorf("expected ACTIVE after reconciliation, got %s", state)
	}
}
