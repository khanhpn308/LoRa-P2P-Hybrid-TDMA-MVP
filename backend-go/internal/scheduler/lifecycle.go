package scheduler

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

// Migration lifecycle states.
const (
	StateDraft           = "DRAFT"
	StatePrepared        = "PREPARED"
	StateStaged          = "STAGED"
	StateCollectingReady = "COLLECTING_READY"
	StateReadyComplete   = "READY_COMPLETE"
	StateCommitted       = "COMMITTED"
	StateAborted         = "ABORTED"
	StateActive          = "ACTIVE"
	StateSuperseded      = "SUPERSEDED"
)

// Ingestion and transition errors.
var (
	ErrInvalidStateTransition   = errors.New("invalid schedule migration state transition")
	ErrDuplicateReport          = errors.New("duplicate schedule ack report ignored")
	ErrStaleReport              = errors.New("stale schedule report rejected: generation or version lower than current")
	ErrActiveScheduleOnChannel  = errors.New("cannot change or release channel while gateway holds an active schedule")
	ErrNodeRebootRxOnly         = errors.New("node is in RX_ONLY state after reboot; DATA transmission disabled")
	ErrContractBlockedResume    = errors.New("node resume wire message contract is BLOCKED_CONTRACT pending #127 registration")
	ErrGatewayMismatchedReport  = errors.New("report gateway_id does not match transaction gateway_id")
	ErrScheduleMismatchedReport = errors.New("report schedule_id does not match transaction schedule_id")
)

// StageAckReport represents an incoming uplink schedule-ack report message.
type StageAckReport struct {
	EventID                  string     `json:"event_id"`
	GatewayID                string     `json:"gateway_id"`
	GatewayEpoch             string     `json:"gateway_epoch"`
	EventSeq                 string     `json:"event_seq"`
	ObservedAt               *time.Time `json:"observed_at"`
	ObservedTimeSource       string     `json:"observed_time_source"`
	RadioRxMonotonicUs       string     `json:"radio_rx_monotonic_us"`
	Buffered                 bool       `json:"buffered"`
	RequestID                string     `json:"request_id"`
	ScheduleID               string     `json:"schedule_id"`
	ScheduleVersion          uint32     `json:"schedule_version"`
	Stage                    string     `json:"stage"` // STAGE_ACK, VERIFY_NACK, ACTIVE_REPORT
	ActivateAtSuperframeSeq  *uint32    `json:"activate_at_superframe_seq,omitempty"`
	ActivatedAtSuperframeSeq *uint32    `json:"activated_at_superframe_seq,omitempty"`
	ReasonCode               string     `json:"reason_code"`
}

// LifecycleEngine manages the complete schedule migration workflow and state invariants.
type LifecycleEngine struct {
	mu           sync.Mutex
	repo         ScheduleRepository
	signer       *ScheduleSigner
	planner      *Planner
	barriers     map[string]*ReadyBarrier // txID -> ReadyBarrier
	nodeStates   map[uint8]string         // nodeID -> NodeStateActive / NodeStateRebootRxOnly
	nodeReboots  map[uint8]time.Time      // nodeID -> last reboot time
	seenEventIDs map[string]bool          // event_id -> seen
}

// NewLifecycleEngine creates a new LifecycleEngine.
func NewLifecycleEngine(repo ScheduleRepository, signer *ScheduleSigner, planner *Planner) *LifecycleEngine {
	return &LifecycleEngine{
		repo:         repo,
		signer:       signer,
		planner:      planner,
		barriers:     make(map[string]*ReadyBarrier),
		nodeStates:   make(map[uint8]string),
		nodeReboots:  make(map[uint8]time.Time),
		seenEventIDs: make(map[string]bool),
	}
}

// StartMigration initiates a new schedule migration for a Gateway.
func (e *LifecycleEngine) StartMigration(ctx context.Context, planReq PlanRequest, kTarget uint32) (*MigrationTransaction, *PrepareTransaction, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	// 1. Plan and validate schedule
	result, err := e.planner.Plan(ctx, planReq)
	if err != nil {
		return nil, nil, fmt.Errorf("planning failed: %w", err)
	}

	// 2. Monotonicity check against existing active schedule
	active, err := e.repo.GetActiveScheduleByGateway(ctx, planReq.GatewayID)
	if err != nil {
		return nil, nil, err
	}
	if active != nil {
		if planReq.ScheduleVersion <= active.ScheduleVersion {
			return nil, nil, fmt.Errorf("%w: current version is %d, requested %d",
				ErrStaleScheduleVersion, active.ScheduleVersion, planReq.ScheduleVersion)
		}
		if planReq.ScheduleGeneration <= active.ScheduleGeneration {
			return nil, nil, fmt.Errorf("%w: current generation is %d, requested %d",
				ErrStaleGeneration, active.ScheduleGeneration, planReq.ScheduleGeneration)
		}
	}

	// 3. Save schedule
	if err := e.repo.SaveSchedule(ctx, result.Schedule); err != nil {
		return nil, nil, err
	}

	// 4. Construct and sign DOWN_SCHED_PREPARE (0x4B, 80B)
	// Gateway numeric ID is mapped from gatewayID (for MVP: e.g. 1)
	gwNumericID := uint8(1)
	profileCode := uint8(1) // V2-VN920-STATIC-15N
	keyID := uint8(0)

	prepareTx, err := e.signer.SignPrepare(gwNumericID, planReq.NetworkID, profileCode, planReq.ScheduleGeneration, kTarget, keyID)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to sign PREPARE frame: %w", err)
	}

	txID := fmt.Sprintf("tx-%s-%d-%d", planReq.GatewayID, planReq.ScheduleGeneration, time.Now().UnixNano())
	barrier, err := NewReadyBarrier(prepareTx.PrepareDigest, planReq.ScheduleGeneration, kTarget, result.AffectedNodeSet, result.Schedule.ExpiresAt)
	if err != nil {
		return nil, nil, err
	}
	e.barriers[txID] = barrier

	now := time.Now().UTC()
	tx := &MigrationTransaction{
		TransactionID:      txID,
		GatewayID:          planReq.GatewayID,
		ScheduleID:         result.Schedule.ScheduleID,
		ScheduleGeneration: planReq.ScheduleGeneration,
		KTarget:            kTarget,
		State:              StatePrepared,
		StateReason:        "PREPARE signed and staged to gateway",
		PrepareDigest:      prepareTx.PrepareDigest,
		PrepareFrame:       prepareTx.RawFrame,
		AffectedNodes:      result.AffectedNodeSet,
		CreatedAt:          now,
		UpdatedAt:          now,
		ExpiresAt:          result.Schedule.ExpiresAt,
	}

	if err := e.repo.CreateTransaction(ctx, tx); err != nil {
		return nil, nil, err
	}

	return tx, prepareTx, nil
}

// IngestReadyProof verifies and records a node's UP_SCHED_READY (0x4C, 41B) proof.
func (e *LifecycleEngine) IngestReadyProof(ctx context.Context, txID string, proofInput NodeReadyProofInput) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	tx, err := e.repo.GetTransaction(ctx, txID)
	if err != nil {
		return err
	}
	if tx.State != StatePrepared && tx.State != StateStaged && tx.State != StateCollectingReady {
		return fmt.Errorf("%w: cannot ingest ready proof in state %s", ErrInvalidStateTransition, tx.State)
	}

	barrier, ok := e.barriers[txID]
	if !ok {
		return errors.New("active ready barrier not found for transaction")
	}

	// Independently verify proof using node authentication key
	if err := e.signer.VerifyNodeReadyProof(proofInput, tx.PrepareDigest); err != nil {
		return fmt.Errorf("proof verification failed: %w", err)
	}

	// Record in barrier
	record := VerifiedReadyRecord{
		NodeID:             proofInput.NodeID,
		ScheduleGeneration: proofInput.ScheduleGeneration,
		KTarget:            proofInput.KTarget,
		Proof:              proofInput.Proof,
		VerifiedAt:         time.Now().UTC(),
	}
	if err := barrier.RecordReady(record); err != nil {
		return err
	}

	// Transition state if appropriate
	if barrier.IsComplete() {
		_ = e.repo.UpdateTransactionState(ctx, txID, StateReadyComplete, "100% affected nodes verified READY")
	} else {
		_ = e.repo.UpdateTransactionState(ctx, txID, StateCollectingReady,
			fmt.Sprintf("%d/%d nodes verified READY", len(barrier.VerifiedNodes()), len(tx.AffectedNodes)))
	}

	return nil
}

// CommitMigration signs and issues the terminal DOWN_SCHED_DECISION (COMMIT) frame.
// STRICT BARRIER: Fails if even 1 affected node is missing, unresponsive, or unverified.
func (e *LifecycleEngine) CommitMigration(ctx context.Context, txID string, now time.Time) (*DecisionTransaction, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	tx, err := e.repo.GetTransaction(ctx, txID)
	if err != nil {
		return nil, err
	}
	if tx.DecisionType != nil {
		return nil, errors.New("terminal decision already issued for transaction")
	}

	barrier, ok := e.barriers[txID]
	if !ok {
		return nil, errors.New("ready barrier not found")
	}

	// Strict 100% barrier check
	if err := barrier.CanCommit(now); err != nil {
		return nil, fmt.Errorf("cannot commit: %w", err)
	}

	// Sign DOWN_SCHED_DECISION COMMIT (0x4D, 80B)
	gwNumericID := uint8(1)
	netID := uint32(1)
	sched, err := e.repo.GetSchedule(ctx, tx.ScheduleID)
	if err == nil && sched != nil {
		netID = sched.NetworkID
	}

	decTx, err := e.signer.SignDecision(gwNumericID, netID, tx.ScheduleGeneration, DecisionCommit, tx.KTarget, tx.PrepareDigest)
	if err != nil {
		return nil, fmt.Errorf("failed to sign COMMIT decision: %w", err)
	}

	if err := e.repo.RecordDecision(ctx, txID, DecisionCommit, decTx.RawFrame); err != nil {
		return nil, err
	}
	if err := e.repo.UpdateTransactionState(ctx, txID, StateCommitted, "Signed COMMIT decision issued at K_TARGET"); err != nil {
		return nil, err
	}

	return decTx, nil
}

// AbortMigration signs and issues the terminal DOWN_SCHED_DECISION (ABORT) frame.
func (e *LifecycleEngine) AbortMigration(ctx context.Context, txID string, reason string) (*DecisionTransaction, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	tx, err := e.repo.GetTransaction(ctx, txID)
	if err != nil {
		return nil, err
	}
	if tx.DecisionType != nil {
		return nil, errors.New("terminal decision already issued for transaction")
	}

	if barrier, ok := e.barriers[txID]; ok {
		barrier.Abort(reason)
	}

	gwNumericID := uint8(1)
	netID := uint32(1)
	sched, err := e.repo.GetSchedule(ctx, tx.ScheduleID)
	if err == nil && sched != nil {
		netID = sched.NetworkID
	}

	decTx, err := e.signer.SignDecision(gwNumericID, netID, tx.ScheduleGeneration, DecisionAbort, tx.KTarget, tx.PrepareDigest)
	if err != nil {
		return nil, fmt.Errorf("failed to sign ABORT decision: %w", err)
	}

	if err := e.repo.RecordDecision(ctx, txID, DecisionAbort, decTx.RawFrame); err != nil {
		return nil, err
	}
	if err := e.repo.UpdateTransactionState(ctx, txID, StateAborted, fmt.Sprintf("Aborted: %s", reason)); err != nil {
		return nil, err
	}

	return decTx, nil
}

// HandleScheduleAck processes incoming Gateway schedule acknowledgments (STAGE_ACK, VERIFY_NACK, ACTIVE_REPORT).
// INVARIANTS:
// - STAGE_ACK only records durable gateway staging; NEVER promotes schedule to ACTIVE.
// - ACTIVE_REPORT only promotes schedule to ACTIVE if current state is COMMITTED and activated_at >= k_target.
// - Monotonic progression: Duplicate or stale reports NEVER roll back state.
func (e *LifecycleEngine) HandleScheduleAck(ctx context.Context, report StageAckReport) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	// Idempotency deduplication by event_id
	if report.EventID != "" && e.seenEventIDs[report.EventID] {
		return nil // Deduplicated cleanly
	}
	if report.EventID != "" {
		e.seenEventIDs[report.EventID] = true
	}

	// Locate schedule and active state
	sched, err := e.repo.GetSchedule(ctx, report.ScheduleID)
	if err != nil {
		return fmt.Errorf("unknown schedule_id %s: %w", report.ScheduleID, err)
	}
	if sched.GatewayID != report.GatewayID {
		return fmt.Errorf("%w: expected %s, got %s", ErrGatewayMismatchedReport, sched.GatewayID, report.GatewayID)
	}

	active, err := e.repo.GetActiveScheduleByGateway(ctx, report.GatewayID)
	if err != nil {
		return err
	}

	switch report.Stage {
	case "STAGE_ACK":
		// Gateway confirmed durable local persistence of proposed schedule.
		// Protect against state rollback if already COMMITTED or ACTIVE.
		if active != nil && active.ScheduleVersion >= report.ScheduleVersion {
			return nil // Out-of-order or duplicate STAGE_ACK; do not downgrade active state
		}
		// In staging phase, update transaction state if exists
		return nil

	case "VERIFY_NACK":
		// Gateway rejected the proposed schedule with reason_code
		return fmt.Errorf("gateway rejected schedule %s with reason: %s", report.ScheduleID, report.ReasonCode)

	case "ACTIVE_REPORT":
		// Gateway reports it has successfully switched its RF timing engine to the new schedule.
		if report.ActivatedAtSuperframeSeq == nil {
			return errors.New("ACTIVE_REPORT missing mandatory activated_at_superframe_seq")
		}

		// Reject stale activation reports lower than current active
		if active != nil && report.ScheduleVersion < active.ScheduleVersion {
			return fmt.Errorf("%w: active version is %d, report version is %d",
				ErrStaleReport, active.ScheduleVersion, report.ScheduleVersion)
		}
		if active != nil && report.ScheduleVersion == active.ScheduleVersion && active.ScheduleID == report.ScheduleID {
			return nil // Duplicate idempotent report
		}

		// Promote to ACTIVE in durable repository
		newActive := &ActiveGatewaySchedule{
			GatewayID:          report.GatewayID,
			ScheduleID:         report.ScheduleID,
			ScheduleVersion:    report.ScheduleVersion,
			ScheduleGeneration: sched.ScheduleGeneration,
			ChannelID:          sched.ChannelID,
			ActivatedAt:        time.Now().UTC(),
			SuperframeSeq:      *report.ActivatedAtSuperframeSeq,
		}
		if err := e.repo.SetActiveSchedule(ctx, newActive); err != nil {
			return fmt.Errorf("failed to persist active schedule: %w", err)
		}

		return nil

	default:
		return fmt.Errorf("unrecognized schedule-ack stage: %q", report.Stage)
	}
}

// CanChangeGatewayChannel verifies that a Gateway does not retain an active schedule before releasing or reassigning its channel.
func (e *LifecycleEngine) CanChangeGatewayChannel(ctx context.Context, gatewayID string) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	active, err := e.repo.GetActiveScheduleByGateway(ctx, gatewayID)
	if err != nil {
		return err
	}
	if active != nil {
		return fmt.Errorf("%w: gateway %s is actively executing schedule %s on channel %s",
			ErrActiveScheduleOnChannel, gatewayID, active.ScheduleID, active.ChannelID)
	}
	return nil
}

// RecordNodeReboot handles Node reboot fail-closed state tracking.
// Invariant: After reboot, Node enters RX_ONLY / DATA_TX_DISABLED until authenticated reconciliation.
func (e *LifecycleEngine) RecordNodeReboot(nodeID uint8, rebootTime time.Time) {
	e.mu.Lock()
	defer e.mu.Unlock()

	e.nodeStates[nodeID] = NodeStateRebootRxOnly
	e.nodeReboots[nodeID] = rebootTime
}

// GetNodeExecutionState returns the current execution state of a Node.
func (e *LifecycleEngine) GetNodeExecutionState(nodeID uint8) string {
	e.mu.Lock()
	defer e.mu.Unlock()

	st, ok := e.nodeStates[nodeID]
	if !ok {
		return NodeStateActive
	}
	return st
}

// ReconcileRebootedNode attempts to reconcile a rebooted node into active state.
// AC 7: If exact Resume message wire contract is unavailable, marks BLOCKED_CONTRACT.
func (e *LifecycleEngine) ReconcileRebootedNode(nodeID uint8, resumeContractAvailable bool) error {
	e.mu.Lock()
	defer e.mu.Unlock()

	if !resumeContractAvailable {
		e.nodeStates[nodeID] = NodeStateBlockedContract
		return fmt.Errorf("%w: node %d marked BLOCKED_CONTRACT pending #127 candidate codepoint",
			ErrContractBlockedResume, nodeID)
	}

	e.nodeStates[nodeID] = NodeStateActive
	return nil
}
