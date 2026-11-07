package scheduler

import (
	"errors"
	"fmt"
	"sort"
	"sync"
	"time"
)

var (
	ErrNodeNotAffected      = errors.New("node ID is not in the affected node set for this migration")
	ErrProofAlreadyReceived = errors.New("ready proof already received and verified for this node (duplicate/replayed)")
	ErrBarrierIncomplete    = errors.New("migration barrier incomplete: 100% affected node verification required for COMMIT")
	ErrBarrierAborted       = errors.New("migration barrier has been aborted due to timeout, collision or node rejection")
)

// VerifiedReadyRecord stores verified proof metadata for an affected node.
type VerifiedReadyRecord struct {
	NodeID             uint8     `json:"node_id"`
	ScheduleGeneration uint32    `json:"schedule_generation"`
	KTarget            uint32    `json:"k_target"`
	Proof              [16]byte  `json:"proof"`
	VerifiedAt         time.Time `json:"verified_at"`
}

// ReadyBarrier manages the 100% verified READY barrier for on-demand schedule migration.
type ReadyBarrier struct {
	mu            sync.RWMutex
	prepareDigest [32]byte
	schedGen      uint32
	kTarget       uint32
	affectedNodes map[uint8]bool
	verifiedNodes map[uint8]VerifiedReadyRecord
	rejectedNodes map[uint8]uint8 // node_id -> reason
	deadline      time.Time
	isAborted     bool
	abortReason   string
}

// NewReadyBarrier creates a new ReadyBarrier with an immutable set of affected nodes.
func NewReadyBarrier(prepareDigest [32]byte, schedGen uint32, kTarget uint32, affectedNodes []uint8, deadline time.Time) (*ReadyBarrier, error) {
	if len(affectedNodes) == 0 {
		return nil, ErrEmptyNodeMembership
	}
	affectedMap := make(map[uint8]bool, len(affectedNodes))
	for _, nid := range affectedNodes {
		if nid < 1 || nid > MaxNodeCapacity {
			return nil, fmt.Errorf("%w: got %d", ErrInvalidNodeID, nid)
		}
		if affectedMap[nid] {
			return nil, fmt.Errorf("%w: node_id=%d", ErrDuplicateNodeID, nid)
		}
		affectedMap[nid] = true
	}

	return &ReadyBarrier{
		prepareDigest: prepareDigest,
		schedGen:      schedGen,
		kTarget:       kTarget,
		affectedNodes: affectedMap,
		verifiedNodes: make(map[uint8]VerifiedReadyRecord, len(affectedNodes)),
		rejectedNodes: make(map[uint8]uint8),
		deadline:      deadline,
	}, nil
}

// RecordReady accepts and records a verified node proof. Fails if node is not affected or already verified.
func (b *ReadyBarrier) RecordReady(record VerifiedReadyRecord) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	if b.isAborted {
		return fmt.Errorf("%w: %s", ErrBarrierAborted, b.abortReason)
	}
	if !b.affectedNodes[record.NodeID] {
		return fmt.Errorf("%w: node_id=%d", ErrNodeNotAffected, record.NodeID)
	}
	if _, exists := b.verifiedNodes[record.NodeID]; exists {
		return fmt.Errorf("%w: node_id=%d", ErrProofAlreadyReceived, record.NodeID)
	}
	if record.ScheduleGeneration != b.schedGen || record.KTarget != b.kTarget {
		return fmt.Errorf("proof generation/target mismatch: expected gen=%d k_target=%d, got gen=%d k_target=%d",
			b.schedGen, b.kTarget, record.ScheduleGeneration, record.KTarget)
	}

	b.verifiedNodes[record.NodeID] = record
	return nil
}

// RecordReject marks an affected node as having rejected the schedule migration.
func (b *ReadyBarrier) RecordReject(nodeID uint8, reason uint8) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	if !b.affectedNodes[nodeID] {
		return fmt.Errorf("%w: node_id=%d", ErrNodeNotAffected, nodeID)
	}
	b.rejectedNodes[nodeID] = reason
	b.isAborted = true
	b.abortReason = fmt.Sprintf("node %d explicitly rejected with reason code %d", nodeID, reason)
	return nil
}

// Abort explicitly cancels the migration barrier (e.g. on timeout or CAD collision).
func (b *ReadyBarrier) Abort(reason string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.isAborted = true
	b.abortReason = reason
}

// IsComplete returns true ONLY when 100% of affected nodes are independently verified.
func (b *ReadyBarrier) IsComplete() bool {
	b.mu.RLock()
	defer b.mu.RUnlock()

	if b.isAborted {
		return false
	}
	if len(b.verifiedNodes) != len(b.affectedNodes) {
		return false
	}
	for nid := range b.affectedNodes {
		if _, ok := b.verifiedNodes[nid]; !ok {
			return false
		}
	}
	return true
}

// MissingNodes returns the list of affected nodes that have not yet provided a verified proof.
func (b *ReadyBarrier) MissingNodes() []uint8 {
	b.mu.RLock()
	defer b.mu.RUnlock()

	var missing []uint8
	for nid := range b.affectedNodes {
		if _, ok := b.verifiedNodes[nid]; !ok {
			missing = append(missing, nid)
		}
	}
	sort.Slice(missing, func(i, j int) bool { return missing[i] < missing[j] })
	return missing
}

// VerifiedNodes returns a sorted slice of node IDs that have verified READY.
func (b *ReadyBarrier) VerifiedNodes() []uint8 {
	b.mu.RLock()
	defer b.mu.RUnlock()

	verified := make([]uint8, 0, len(b.verifiedNodes))
	for nid := range b.verifiedNodes {
		verified = append(verified, nid)
	}
	sort.Slice(verified, func(i, j int) bool { return verified[i] < verified[j] })
	return verified
}

// CanCommit validates that the 100% barrier is strictly satisfied before a COMMIT decision can be signed.
func (b *ReadyBarrier) CanCommit(now time.Time) error {
	b.mu.RLock()
	defer b.mu.RUnlock()

	if b.isAborted {
		return fmt.Errorf("%w: %s", ErrBarrierAborted, b.abortReason)
	}
	if !b.deadline.IsZero() && now.After(b.deadline) {
		return fmt.Errorf("%w: deadline %v passed at %v", ErrBarrierAborted, b.deadline, now)
	}
	if len(b.verifiedNodes) != len(b.affectedNodes) {
		missing := b.missingNodesLocked()
		return fmt.Errorf("%w: missing nodes %v (%d/%d verified)",
			ErrBarrierIncomplete, missing, len(b.verifiedNodes), len(b.affectedNodes))
	}
	for nid := range b.affectedNodes {
		if _, ok := b.verifiedNodes[nid]; !ok {
			return fmt.Errorf("%w: node %d unverified", ErrBarrierIncomplete, nid)
		}
	}
	return nil
}

func (b *ReadyBarrier) missingNodesLocked() []uint8 {
	var missing []uint8
	for nid := range b.affectedNodes {
		if _, ok := b.verifiedNodes[nid]; !ok {
			missing = append(missing, nid)
		}
	}
	sort.Slice(missing, func(i, j int) bool { return missing[i] < missing[j] })
	return missing
}
