package scheduler_test

import (
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

func TestReadyBarrier100PercentRule(t *testing.T) {
	var digest [32]byte
	copy(digest[:], []byte("barrier-test-prepare-digest-1234"))

	schedGen := uint32(1)
	kTarget := uint32(100)
	affectedNodes := []uint8{1, 2, 3}
	deadline := time.Now().UTC().Add(1 * time.Minute)

	barrier, err := scheduler.NewReadyBarrier(digest, schedGen, kTarget, affectedNodes, deadline)
	if err != nil {
		t.Fatalf("failed to create barrier: %v", err)
	}

	if barrier.IsComplete() {
		t.Errorf("barrier should not be complete before proofs arrive")
	}

	// 1. Ingest proof for node 1
	var proof1 [16]byte
	copy(proof1[:], "proof-node-1")
	err = barrier.RecordReady(scheduler.VerifiedReadyRecord{
		NodeID:             1,
		ScheduleGeneration: schedGen,
		KTarget:            kTarget,
		Proof:              proof1,
		VerifiedAt:         time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if barrier.IsComplete() {
		t.Errorf("barrier must not be complete with 1/3 nodes verified")
	}
	if err := barrier.CanCommit(time.Now().UTC()); err == nil {
		t.Errorf("CanCommit must fail when barrier is incomplete (1/3)")
	}

	// 2. Ingest duplicate proof for node 1 (should fail)
	if err := barrier.RecordReady(scheduler.VerifiedReadyRecord{
		NodeID:             1,
		ScheduleGeneration: schedGen,
		KTarget:            kTarget,
		Proof:              proof1,
		VerifiedAt:         time.Now().UTC(),
	}); err == nil {
		t.Errorf("expected error for duplicate ready proof from node 1")
	}

	// 3. Ingest proof for unaffected node 4 (should fail)
	if err := barrier.RecordReady(scheduler.VerifiedReadyRecord{
		NodeID:             4,
		ScheduleGeneration: schedGen,
		KTarget:            kTarget,
		Proof:              proof1,
		VerifiedAt:         time.Now().UTC(),
	}); err == nil {
		t.Errorf("expected error for unaffected node 4")
	}

	// 4. Ingest proof for node 2
	var proof2 [16]byte
	copy(proof2[:], "proof-node-2")
	_ = barrier.RecordReady(scheduler.VerifiedReadyRecord{
		NodeID:             2,
		ScheduleGeneration: schedGen,
		KTarget:            kTarget,
		Proof:              proof2,
		VerifiedAt:         time.Now().UTC(),
	})

	if barrier.IsComplete() {
		t.Errorf("barrier must not be complete with 2/3 nodes verified")
	}
	if err := barrier.CanCommit(time.Now().UTC()); err == nil {
		t.Errorf("CanCommit must fail when barrier is incomplete (2/3)")
	}

	// 5. Ingest proof for node 3 (100% complete)
	var proof3 [16]byte
	copy(proof3[:], "proof-node-3")
	_ = barrier.RecordReady(scheduler.VerifiedReadyRecord{
		NodeID:             3,
		ScheduleGeneration: schedGen,
		KTarget:            kTarget,
		Proof:              proof3,
		VerifiedAt:         time.Now().UTC(),
	})

	if !barrier.IsComplete() {
		t.Errorf("barrier should be complete with 3/3 nodes verified")
	}
	if err := barrier.CanCommit(time.Now().UTC()); err != nil {
		t.Errorf("CanCommit should succeed with 100%% verified nodes, got: %v", err)
	}
}

func TestReadyBarrierRejectionAndTimeout(t *testing.T) {
	var digest [32]byte
	schedGen := uint32(1)
	kTarget := uint32(100)
	affectedNodes := []uint8{1, 2}
	deadline := time.Now().UTC().Add(100 * time.Millisecond)

	barrier, err := scheduler.NewReadyBarrier(digest, schedGen, kTarget, affectedNodes, deadline)
	if err != nil {
		t.Fatalf("failed to create barrier: %v", err)
	}

	// Node 1 rejects
	if err := barrier.RecordReject(1, 42); err != nil {
		t.Fatalf("unexpected error recording reject: %v", err)
	}

	if barrier.IsComplete() {
		t.Errorf("aborted barrier must not be complete")
	}
	if err := barrier.CanCommit(time.Now().UTC()); err == nil {
		t.Errorf("CanCommit must fail on aborted barrier")
	}

	// Timeout test
	barrier2, _ := scheduler.NewReadyBarrier(digest, schedGen, kTarget, affectedNodes, deadline)
	time.Sleep(120 * time.Millisecond)
	if err := barrier2.CanCommit(time.Now().UTC()); err == nil {
		t.Errorf("CanCommit must fail after deadline has expired")
	}
}
