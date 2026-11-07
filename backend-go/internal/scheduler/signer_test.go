package scheduler_test

import (
	"crypto/ed25519"
	"crypto/rand"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

func TestSignerPrepareAndDecision(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate ed25519 key: %v", err)
	}

	nodeKeys := map[uint8][]byte{
		1: []byte("node1-secret-key-32-bytes-long!"),
		2: []byte("node2-secret-key-32-bytes-long!"),
	}
	keyDir := scheduler.NewMapNodeKeyDirectory(nodeKeys)

	signer, err := scheduler.NewScheduleSigner(priv, keyDir)
	if err != nil {
		t.Fatalf("failed to create signer: %v", err)
	}

	// 1. Sign DOWN_SCHED_PREPARE (0x4B, 80B)
	prepTx, err := signer.SignPrepare(1, 100, 1, 5, 1000, 0)
	if err != nil {
		t.Fatalf("failed to sign prepare: %v", err)
	}
	if len(prepTx.RawFrame) != scheduler.BytesDownSchedPrepare {
		t.Fatalf("expected 80 bytes prepare frame, got %d", len(prepTx.RawFrame))
	}

	// Verify PREPARE frame
	verifiedPrep, err := scheduler.VerifyPrepare(pub, prepTx.RawFrame[:])
	if err != nil {
		t.Fatalf("failed to verify prepare frame: %v", err)
	}
	if verifiedPrep.GatewayNumericID != 1 || verifiedPrep.NetworkID != 100 ||
		verifiedPrep.ScheduleGeneration != 5 || verifiedPrep.KTarget != 1000 {
		t.Errorf("verified prepare header mismatch: %+v", verifiedPrep)
	}
	if verifiedPrep.PrepareDigest != prepTx.PrepareDigest {
		t.Errorf("prepare digest mismatch")
	}

	// 2. Sign DOWN_SCHED_DECISION COMMIT (0x4D, 80B) bound to PREPARE
	decTx, err := signer.SignDecision(1, 100, 5, scheduler.DecisionCommit, 1000, prepTx.PrepareDigest)
	if err != nil {
		t.Fatalf("failed to sign decision: %v", err)
	}
	if len(decTx.RawFrame) != scheduler.BytesDownSchedDecision {
		t.Fatalf("expected 80 bytes decision frame, got %d", len(decTx.RawFrame))
	}

	// Verify DECISION frame with matching PREPARE digest
	verifiedDec, err := scheduler.VerifyDecision(pub, decTx.RawFrame[:], prepTx.PrepareDigest)
	if err != nil {
		t.Fatalf("failed to verify decision frame: %v", err)
	}
	if verifiedDec.DecisionType != scheduler.DecisionCommit {
		t.Errorf("expected decision commit (1), got %d", verifiedDec.DecisionType)
	}

	// 3. Verify DECISION frame with TAMPERED PREPARE digest fails!
	tamperedDigest := prepTx.PrepareDigest
	tamperedDigest[0] ^= 0xFF
	if _, err := scheduler.VerifyDecision(pub, decTx.RawFrame[:], tamperedDigest); err == nil {
		t.Errorf("expected failure when verifying decision with mismatched prepare digest")
	}
}

func TestSignerNodeReadyProof(t *testing.T) {
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("failed to generate ed25519 key: %v", err)
	}

	nodeKey1 := []byte("secret-key-node-1-thirtytwo-byte")
	keyDir := scheduler.NewMapNodeKeyDirectory(map[uint8][]byte{
		1: nodeKey1,
	})

	signer, err := scheduler.NewScheduleSigner(priv, keyDir)
	if err != nil {
		t.Fatalf("failed to create signer: %v", err)
	}

	var prepareDigest [32]byte
	copy(prepareDigest[:], []byte("mock-sha256-prepare-digest-12345"))

	schedGen := uint32(5)
	kTarget := uint32(200)
	nodeID := uint8(1)

	// Compute valid proof
	proof := scheduler.ComputeNodeReadyProof(nodeKey1, prepareDigest, schedGen, kTarget, nodeID)

	validInput := scheduler.NodeReadyProofInput{
		NodeID:             nodeID,
		SessionSel:         1,
		FrameCounter:       42,
		ScheduleGeneration: schedGen,
		KTarget:            kTarget,
		Status:             1, // READY
		Reason:             0, // NONE
		Proof:              proof,
	}

	if err := signer.VerifyNodeReadyProof(validInput, prepareDigest); err != nil {
		t.Fatalf("valid ready proof failed verification: %v", err)
	}

	// Non-ready status fails
	invalidStatusInput := validInput
	invalidStatusInput.Status = 0
	if err := signer.VerifyNodeReadyProof(invalidStatusInput, prepareDigest); err == nil {
		t.Errorf("expected failure when status != 1")
	}

	// Forged proof fails
	forgedInput := validInput
	forgedInput.Proof[0] ^= 0xFF
	if err := signer.VerifyNodeReadyProof(forgedInput, prepareDigest); err == nil {
		t.Errorf("expected failure for forged ready proof")
	}

	// Mismatched kTarget fails
	mismatchedTargetInput := validInput
	mismatchedTargetInput.KTarget = 201
	if err := signer.VerifyNodeReadyProof(mismatchedTargetInput, prepareDigest); err == nil {
		t.Errorf("expected failure for mismatched KTarget")
	}

	// Unregistered node fails
	unregisteredInput := validInput
	unregisteredInput.NodeID = 2
	if err := signer.VerifyNodeReadyProof(unregisteredInput, prepareDigest); err == nil {
		t.Errorf("expected failure for unregistered node")
	}
}
