package scheduler

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

var (
	ErrScheduleNotFound    = errors.New("schedule not found")
	ErrTransactionNotFound = errors.New("schedule migration transaction not found")
	ErrActiveScheduleFound = errors.New("gateway already has an active schedule running on an allocated channel")
)

// ActiveGatewaySchedule records the currently active, verified schedule for a Gateway.
type ActiveGatewaySchedule struct {
	GatewayID          string    `json:"gateway_id"`
	ScheduleID         string    `json:"schedule_id"`
	ScheduleVersion    uint32    `json:"schedule_version"`
	ScheduleGeneration uint32    `json:"schedule_generation"`
	ChannelID          string    `json:"channel_id"`
	ActivatedAt        time.Time `json:"activated_at"`
	SuperframeSeq      uint32    `json:"superframe_seq"`
}

// MigrationTransaction persists the complete state of a schedule migration workflow.
type MigrationTransaction struct {
	TransactionID      string                        `json:"transaction_id"`
	GatewayID          string                        `json:"gateway_id"`
	ScheduleID         string                        `json:"schedule_id"`
	ScheduleGeneration uint32                        `json:"schedule_generation"`
	KTarget            uint32                        `json:"k_target"`
	State              string                        `json:"state"`
	StateReason        string                        `json:"state_reason"`
	PrepareDigest      [32]byte                      `json:"prepare_digest"`
	PrepareFrame       [BytesDownSchedPrepare]byte   `json:"prepare_frame"`
	DecisionType       *uint8                        `json:"decision_type,omitempty"`
	DecisionFrame      *[BytesDownSchedDecision]byte `json:"decision_frame,omitempty"`
	AffectedNodes      []uint8                       `json:"affected_nodes"`
	CreatedAt          time.Time                     `json:"created_at"`
	UpdatedAt          time.Time                     `json:"updated_at"`
	ExpiresAt          time.Time                     `json:"expires_at"`
}

// ScheduleRepository defines storage operations for TDMA schedules and migration transactions.
type ScheduleRepository interface {
	SaveSchedule(ctx context.Context, sched *Schedule) error
	GetSchedule(ctx context.Context, scheduleID string) (*Schedule, error)
	GetActiveScheduleByGateway(ctx context.Context, gatewayID string) (*ActiveGatewaySchedule, error)
	SetActiveSchedule(ctx context.Context, active *ActiveGatewaySchedule) error

	CreateTransaction(ctx context.Context, tx *MigrationTransaction) error
	GetTransaction(ctx context.Context, txID string) (*MigrationTransaction, error)
	UpdateTransactionState(ctx context.Context, txID string, state string, reason string) error
	RecordDecision(ctx context.Context, txID string, decType uint8, decFrame [BytesDownSchedDecision]byte) error

	UpdateReviewState(ctx context.Context, scheduleID string, reviewState string, rejectReason *string) error
	GetReviewState(ctx context.Context, scheduleID string) (reviewState string, rejectReason *string, err error)
	UpdateScheduleState(ctx context.Context, scheduleID string, state string) error
	GetScheduleState(ctx context.Context, scheduleID string) (string, error)
}

type memoryReviewRecord struct {
	ReviewState  string
	RejectReason *string
}

// MemoryScheduleRepository provides a thread-safe in-memory implementation of ScheduleRepository.
type MemoryScheduleRepository struct {
	mu           sync.RWMutex
	schedules    map[string]*Schedule
	active       map[string]*ActiveGatewaySchedule // gatewayID -> active
	transactions map[string]*MigrationTransaction
	reviews      map[string]*memoryReviewRecord
	states       map[string]string
}

// NewMemoryScheduleRepository creates a new MemoryScheduleRepository.
func NewMemoryScheduleRepository() *MemoryScheduleRepository {
	return &MemoryScheduleRepository{
		schedules:    make(map[string]*Schedule),
		active:       make(map[string]*ActiveGatewaySchedule),
		transactions: make(map[string]*MigrationTransaction),
		reviews:      make(map[string]*memoryReviewRecord),
		states:       make(map[string]string),
	}
}

// SaveSchedule saves a schedule proposal.
func (r *MemoryScheduleRepository) SaveSchedule(ctx context.Context, sched *Schedule) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	cp := *sched
	r.schedules[sched.ScheduleID] = &cp
	return nil
}

// GetSchedule retrieves a schedule by scheduleID.
func (r *MemoryScheduleRepository) GetSchedule(ctx context.Context, scheduleID string) (*Schedule, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	s, ok := r.schedules[scheduleID]
	if !ok {
		return nil, fmt.Errorf("%w: %s", ErrScheduleNotFound, scheduleID)
	}
	cp := *s
	return &cp, nil
}

// GetActiveScheduleByGateway returns the currently active schedule for a Gateway, if any.
func (r *MemoryScheduleRepository) GetActiveScheduleByGateway(ctx context.Context, gatewayID string) (*ActiveGatewaySchedule, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	act, ok := r.active[gatewayID]
	if !ok {
		return nil, nil // No active schedule is a normal starting state
	}
	cp := *act
	return &cp, nil
}

// SetActiveSchedule records the new active schedule for a Gateway.
func (r *MemoryScheduleRepository) SetActiveSchedule(ctx context.Context, active *ActiveGatewaySchedule) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	cp := *active
	r.active[active.GatewayID] = &cp
	return nil
}

// CreateTransaction initializes a new migration transaction.
func (r *MemoryScheduleRepository) CreateTransaction(ctx context.Context, tx *MigrationTransaction) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, exists := r.transactions[tx.TransactionID]; exists {
		return fmt.Errorf("duplicate transaction id: %s", tx.TransactionID)
	}
	cp := *tx
	r.transactions[tx.TransactionID] = &cp
	return nil
}

// GetTransaction retrieves a migration transaction.
func (r *MemoryScheduleRepository) GetTransaction(ctx context.Context, txID string) (*MigrationTransaction, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	tx, ok := r.transactions[txID]
	if !ok {
		return nil, fmt.Errorf("%w: %s", ErrTransactionNotFound, txID)
	}
	cp := *tx
	return &cp, nil
}

// UpdateTransactionState updates the state and reason of an existing transaction.
func (r *MemoryScheduleRepository) UpdateTransactionState(ctx context.Context, txID string, state string, reason string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	tx, ok := r.transactions[txID]
	if !ok {
		return fmt.Errorf("%w: %s", ErrTransactionNotFound, txID)
	}
	tx.State = state
	tx.StateReason = reason
	tx.UpdatedAt = time.Now().UTC()
	return nil
}

// RecordDecision stores the signed terminal decision (COMMIT/ABORT).
func (r *MemoryScheduleRepository) RecordDecision(ctx context.Context, txID string, decType uint8, decFrame [BytesDownSchedDecision]byte) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	tx, ok := r.transactions[txID]
	if !ok {
		return fmt.Errorf("%w: %s", ErrTransactionNotFound, txID)
	}
	if tx.DecisionType != nil {
		return errors.New("terminal decision already recorded for this transaction")
	}
	tx.DecisionType = &decType
	frameCopy := decFrame
	tx.DecisionFrame = &frameCopy
	tx.UpdatedAt = time.Now().UTC()
	return nil
}

// UpdateReviewState updates the review state and optional reject reason for a schedule.
func (r *MemoryScheduleRepository) UpdateReviewState(ctx context.Context, scheduleID string, reviewState string, rejectReason *string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	r.reviews[scheduleID] = &memoryReviewRecord{
		ReviewState:  reviewState,
		RejectReason: rejectReason,
	}
	return nil
}

// GetReviewState retrieves the review state and optional reject reason for a schedule.
func (r *MemoryScheduleRepository) GetReviewState(ctx context.Context, scheduleID string) (string, *string, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	rec, ok := r.reviews[scheduleID]
	if !ok {
		return "PENDING", nil, nil
	}
	return rec.ReviewState, rec.RejectReason, nil
}

// UpdateScheduleState updates the lifecycle state of a schedule.
func (r *MemoryScheduleRepository) UpdateScheduleState(ctx context.Context, scheduleID string, state string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	r.states[scheduleID] = state
	return nil
}

// GetScheduleState retrieves the lifecycle state of a schedule.
func (r *MemoryScheduleRepository) GetScheduleState(ctx context.Context, scheduleID string) (string, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	state, ok := r.states[scheduleID]
	if !ok {
		return "PROPOSED", nil
	}
	return state, nil
}
