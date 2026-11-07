package storage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler"
)

var (
	// ErrNilSchedule indicates a nil schedule was passed to SaveSchedule.
	ErrNilSchedule = errors.New("schedule cannot be nil")
	// ErrNilActiveSchedule indicates a nil active schedule was passed to SetActiveSchedule.
	ErrNilActiveSchedule = errors.New("active schedule cannot be nil")
	// ErrNilTransaction indicates a nil migration transaction was passed to CreateTransaction.
	ErrNilTransaction = errors.New("migration transaction cannot be nil")
)

// PostgresScheduleStorage implements scheduler.ScheduleRepository against PostgreSQL.
type PostgresScheduleStorage struct {
	db *sql.DB
}

// NewPostgresScheduleStorage creates a new PostgresScheduleStorage instance.
func NewPostgresScheduleStorage(db *sql.DB) *PostgresScheduleStorage {
	return &PostgresScheduleStorage{db: db}
}

// SaveSchedule atomically persists a schedule proposal and its constituent slots.
func (s *PostgresScheduleStorage) SaveSchedule(ctx context.Context, sched *scheduler.Schedule) error {
	if sched == nil {
		return ErrNilSchedule
	}
	if err := sched.Validate(); err != nil {
		return fmt.Errorf("cannot save invalid schedule: %w", err)
	}

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return fmt.Errorf("failed to begin schedule transaction: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	const insertScheduleQuery = `
		INSERT INTO schedules (
			schedule_id, gateway_id, network_id, schedule_version, schedule_generation,
			channel_id, profile_id, superframe_ms, state, review_state, reject_reason,
			created_at, expires_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'PROPOSED', 'PENDING', NULL, $9, $10)
		ON CONFLICT (schedule_id) DO UPDATE SET
			gateway_id = EXCLUDED.gateway_id,
			network_id = EXCLUDED.network_id,
			schedule_version = EXCLUDED.schedule_version,
			schedule_generation = EXCLUDED.schedule_generation,
			channel_id = EXCLUDED.channel_id,
			profile_id = EXCLUDED.profile_id,
			superframe_ms = EXCLUDED.superframe_ms,
			created_at = EXCLUDED.created_at,
			expires_at = EXCLUDED.expires_at;
	`

	_, err = tx.ExecContext(ctx, insertScheduleQuery,
		sched.ScheduleID,
		sched.GatewayID,
		sched.NetworkID,
		sched.ScheduleVersion,
		sched.ScheduleGeneration,
		sched.ChannelID,
		sched.ProfileID,
		sched.SuperframeMs,
		sched.CreatedAt.UTC(),
		sched.ExpiresAt.UTC(),
	)
	if err != nil {
		return fmt.Errorf("failed to insert schedule %s: %w", sched.ScheduleID, err)
	}

	// Clean up existing slots if overwriting
	const deleteSlotsQuery = `DELETE FROM schedule_slots WHERE schedule_id = $1;`
	if _, err := tx.ExecContext(ctx, deleteSlotsQuery, sched.ScheduleID); err != nil {
		return fmt.Errorf("failed to clear previous slots for schedule %s: %w", sched.ScheduleID, err)
	}

	const insertSlotQuery = `
		INSERT INTO schedule_slots (schedule_id, slot_id, node_id, offset_ms, duration_ms)
		VALUES ($1, $2, $3, $4, $5);
	`
	for _, slot := range sched.Slots {
		_, err := tx.ExecContext(ctx, insertSlotQuery,
			sched.ScheduleID,
			slot.SlotID,
			slot.NodeID,
			slot.OffsetMs,
			slot.DurationMs,
		)
		if err != nil {
			return fmt.Errorf("failed to insert slot %d for schedule %s: %w", slot.SlotID, sched.ScheduleID, err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit schedule transaction: %w", err)
	}

	return nil
}

// GetSchedule retrieves a schedule by scheduleID along with its constituent slots.
func (s *PostgresScheduleStorage) GetSchedule(ctx context.Context, scheduleID string) (*scheduler.Schedule, error) {
	const selectScheduleQuery = `
		SELECT schedule_id, gateway_id, network_id, schedule_version, schedule_generation,
		       channel_id, profile_id, superframe_ms, created_at, expires_at
		FROM schedules
		WHERE schedule_id = $1;
	`

	var sched scheduler.Schedule
	var createdAt, expiresAt time.Time
	err := s.db.QueryRowContext(ctx, selectScheduleQuery, scheduleID).Scan(
		&sched.ScheduleID,
		&sched.GatewayID,
		&sched.NetworkID,
		&sched.ScheduleVersion,
		&sched.ScheduleGeneration,
		&sched.ChannelID,
		&sched.ProfileID,
		&sched.SuperframeMs,
		&createdAt,
		&expiresAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("%w: %s", scheduler.ErrScheduleNotFound, scheduleID)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query schedule %s: %w", scheduleID, err)
	}

	sched.CreatedAt = createdAt.UTC()
	sched.ExpiresAt = expiresAt.UTC()
	sched.SchemaVersion = scheduler.DefaultSchemaVersion
	sched.MinAnnounceSuperframes = scheduler.MinAnnounceSuperframesDefault

	const selectSlotsQuery = `
		SELECT slot_id, node_id, offset_ms, duration_ms
		FROM schedule_slots
		WHERE schedule_id = $1
		ORDER BY slot_id ASC;
	`

	rows, err := s.db.QueryContext(ctx, selectSlotsQuery, scheduleID)
	if err != nil {
		return nil, fmt.Errorf("failed to query slots for schedule %s: %w", scheduleID, err)
	}
	defer rows.Close()

	var slots []scheduler.SlotConfig
	var affectedNodes []uint8
	seenNodes := make(map[uint8]bool)

	for rows.Next() {
		var slot scheduler.SlotConfig
		if err := rows.Scan(&slot.SlotID, &slot.NodeID, &slot.OffsetMs, &slot.DurationMs); err != nil {
			return nil, fmt.Errorf("failed to scan slot row for schedule %s: %w", scheduleID, err)
		}
		slots = append(slots, slot)
		if !seenNodes[slot.NodeID] {
			seenNodes[slot.NodeID] = true
			affectedNodes = append(affectedNodes, slot.NodeID)
		}
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error reading slot rows: %w", err)
	}

	sched.Slots = slots
	sched.AffectedNodeSet = affectedNodes

	return &sched, nil
}

// GetActiveScheduleByGateway returns the currently active, verified schedule for a Gateway.
func (s *PostgresScheduleStorage) GetActiveScheduleByGateway(ctx context.Context, gatewayID string) (*scheduler.ActiveGatewaySchedule, error) {
	const selectActiveQuery = `
		SELECT gateway_id, schedule_id, schedule_version, schedule_generation,
		       channel_id, activated_at, superframe_seq
		FROM active_gateway_schedules
		WHERE gateway_id = $1;
	`

	var act scheduler.ActiveGatewaySchedule
	var activatedAt time.Time
	err := s.db.QueryRowContext(ctx, selectActiveQuery, gatewayID).Scan(
		&act.GatewayID,
		&act.ScheduleID,
		&act.ScheduleVersion,
		&act.ScheduleGeneration,
		&act.ChannelID,
		&activatedAt,
		&act.SuperframeSeq,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil // Normal initial condition: no active schedule yet
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query active schedule for gateway %s: %w", gatewayID, err)
	}

	act.ActivatedAt = activatedAt.UTC()
	return &act, nil
}

// SetActiveSchedule records the newly activated schedule for a Gateway atomically.
func (s *PostgresScheduleStorage) SetActiveSchedule(ctx context.Context, active *scheduler.ActiveGatewaySchedule) error {
	if active == nil {
		return ErrNilActiveSchedule
	}

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return fmt.Errorf("failed to begin set active schedule transaction: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	const upsertActiveQuery = `
		INSERT INTO active_gateway_schedules (
			gateway_id, schedule_id, schedule_version, schedule_generation,
			channel_id, activated_at, superframe_seq
		) VALUES ($1, $2, $3, $4, $5, $6, $7)
		ON CONFLICT (gateway_id) DO UPDATE SET
			schedule_id = EXCLUDED.schedule_id,
			schedule_version = EXCLUDED.schedule_version,
			schedule_generation = EXCLUDED.schedule_generation,
			channel_id = EXCLUDED.channel_id,
			activated_at = EXCLUDED.activated_at,
			superframe_seq = EXCLUDED.superframe_seq;
	`

	_, err = tx.ExecContext(ctx, upsertActiveQuery,
		active.GatewayID,
		active.ScheduleID,
		active.ScheduleVersion,
		active.ScheduleGeneration,
		active.ChannelID,
		active.ActivatedAt.UTC(),
		active.SuperframeSeq,
	)
	if err != nil {
		return fmt.Errorf("failed to upsert active schedule for gateway %s: %w", active.GatewayID, err)
	}

	const updateScheduleStateQuery = `
		UPDATE schedules
		SET state = 'ACTIVE'
		WHERE schedule_id = $1;
	`
	if _, err := tx.ExecContext(ctx, updateScheduleStateQuery, active.ScheduleID); err != nil {
		return fmt.Errorf("failed to update state to ACTIVE for schedule %s: %w", active.ScheduleID, err)
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit active schedule transaction: %w", err)
	}

	return nil
}

// CreateTransaction initializes a new migration transaction in PostgreSQL.
func (s *PostgresScheduleStorage) CreateTransaction(ctx context.Context, tx *scheduler.MigrationTransaction) error {
	if tx == nil {
		return ErrNilTransaction
	}

	const insertTxQuery = `
		INSERT INTO schedule_migration_transactions (
			transaction_id, gateway_id, schedule_id, schedule_generation,
			k_target, state, state_reason, prepare_digest, prepare_frame,
			decision_type, decision_frame, affected_nodes, created_at,
			updated_at, expires_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15);
	`

	var decType *int16
	if tx.DecisionType != nil {
		val := int16(*tx.DecisionType)
		decType = &val
	}

	var decFrame []byte
	if tx.DecisionFrame != nil {
		decFrame = tx.DecisionFrame[:]
	}

	affectedNodesStr := formatIntArray(tx.AffectedNodes)

	_, err := s.db.ExecContext(ctx, insertTxQuery,
		tx.TransactionID,
		tx.GatewayID,
		tx.ScheduleID,
		tx.ScheduleGeneration,
		tx.KTarget,
		tx.State,
		tx.StateReason,
		tx.PrepareDigest[:],
		tx.PrepareFrame[:],
		decType,
		decFrame,
		affectedNodesStr,
		tx.CreatedAt.UTC(),
		tx.UpdatedAt.UTC(),
		tx.ExpiresAt.UTC(),
	)
	if err != nil {
		return fmt.Errorf("failed to create migration transaction %s: %w", tx.TransactionID, err)
	}

	return nil
}

// GetTransaction retrieves a migration transaction by transaction_id.
func (s *PostgresScheduleStorage) GetTransaction(ctx context.Context, txID string) (*scheduler.MigrationTransaction, error) {
	const selectTxQuery = `
		SELECT transaction_id, gateway_id, schedule_id, schedule_generation,
		       k_target, state, state_reason, prepare_digest, prepare_frame,
		       decision_type, decision_frame, affected_nodes, created_at,
		       updated_at, expires_at
		FROM schedule_migration_transactions
		WHERE transaction_id = $1;
	`

	var tx scheduler.MigrationTransaction
	var prepDigest, prepFrame []byte
	var decTypeVal sql.NullInt16
	var decFrameVal []byte
	var affectedStr string
	var createdAt, updatedAt, expiresAt time.Time

	err := s.db.QueryRowContext(ctx, selectTxQuery, txID).Scan(
		&tx.TransactionID,
		&tx.GatewayID,
		&tx.ScheduleID,
		&tx.ScheduleGeneration,
		&tx.KTarget,
		&tx.State,
		&tx.StateReason,
		&prepDigest,
		&prepFrame,
		&decTypeVal,
		&decFrameVal,
		&affectedStr,
		&createdAt,
		&updatedAt,
		&expiresAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("%w: %s", scheduler.ErrTransactionNotFound, txID)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query migration transaction %s: %w", txID, err)
	}

	if len(prepDigest) == 32 {
		copy(tx.PrepareDigest[:], prepDigest)
	}
	if len(prepFrame) == scheduler.BytesDownSchedPrepare {
		copy(tx.PrepareFrame[:], prepFrame)
	}

	if decTypeVal.Valid {
		dt := uint8(decTypeVal.Int16)
		tx.DecisionType = &dt
	}
	if len(decFrameVal) == scheduler.BytesDownSchedDecision {
		var df [scheduler.BytesDownSchedDecision]byte
		copy(df[:], decFrameVal)
		tx.DecisionFrame = &df
	}

	affectedNodes, err := parseIntArray(affectedStr)
	if err != nil {
		return nil, fmt.Errorf("failed to parse affected nodes for transaction %s: %w", txID, err)
	}
	tx.AffectedNodes = affectedNodes
	tx.CreatedAt = createdAt.UTC()
	tx.UpdatedAt = updatedAt.UTC()
	tx.ExpiresAt = expiresAt.UTC()

	return &tx, nil
}

// UpdateTransactionState updates the state and reason of an existing transaction.
func (s *PostgresScheduleStorage) UpdateTransactionState(ctx context.Context, txID string, state string, reason string) error {
	const updateTxQuery = `
		UPDATE schedule_migration_transactions
		SET state = $1, state_reason = $2, updated_at = CURRENT_TIMESTAMP
		WHERE transaction_id = $3;
	`

	res, err := s.db.ExecContext(ctx, updateTxQuery, state, reason, txID)
	if err != nil {
		return fmt.Errorf("failed to update state for transaction %s: %w", txID, err)
	}
	rows, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to check rows affected: %w", err)
	}
	if rows == 0 {
		return fmt.Errorf("%w: %s", scheduler.ErrTransactionNotFound, txID)
	}

	return nil
}

// RecordDecision stores the signed terminal decision (COMMIT/ABORT) using a row lock.
func (s *PostgresScheduleStorage) RecordDecision(ctx context.Context, txID string, decType uint8, decFrame [scheduler.BytesDownSchedDecision]byte) error {
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return fmt.Errorf("failed to begin decision transaction: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	const lockTxQuery = `
		SELECT decision_type
		FROM schedule_migration_transactions
		WHERE transaction_id = $1
		FOR UPDATE;
	`

	var existingDecType sql.NullInt16
	err = tx.QueryRowContext(ctx, lockTxQuery, txID).Scan(&existingDecType)
	if errors.Is(err, sql.ErrNoRows) {
		return fmt.Errorf("%w: %s", scheduler.ErrTransactionNotFound, txID)
	}
	if err != nil {
		return fmt.Errorf("failed to lock transaction %s: %w", txID, err)
	}
	if existingDecType.Valid {
		return errors.New("terminal decision already recorded for this transaction")
	}

	const updateDecisionQuery = `
		UPDATE schedule_migration_transactions
		SET decision_type = $1, decision_frame = $2, updated_at = CURRENT_TIMESTAMP
		WHERE transaction_id = $3;
	`

	_, err = tx.ExecContext(ctx, updateDecisionQuery, int16(decType), decFrame[:], txID)
	if err != nil {
		return fmt.Errorf("failed to record decision for transaction %s: %w", txID, err)
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit decision transaction: %w", err)
	}

	return nil
}

// UpdateReviewState updates the review state and optional reject reason for a schedule.
func (s *PostgresScheduleStorage) UpdateReviewState(ctx context.Context, scheduleID string, reviewState string, rejectReason *string) error {
	const updateReviewQuery = `
		UPDATE schedules
		SET review_state = $1, reject_reason = $2
		WHERE schedule_id = $3;
	`

	res, err := s.db.ExecContext(ctx, updateReviewQuery, reviewState, rejectReason, scheduleID)
	if err != nil {
		return fmt.Errorf("failed to update review state for schedule %s: %w", scheduleID, err)
	}
	rows, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to inspect rows affected: %w", err)
	}
	if rows == 0 {
		return fmt.Errorf("%w: %s", scheduler.ErrScheduleNotFound, scheduleID)
	}

	return nil
}

// GetReviewState retrieves the review state and optional reject reason for a schedule.
func (s *PostgresScheduleStorage) GetReviewState(ctx context.Context, scheduleID string) (string, *string, error) {
	const selectReviewQuery = `
		SELECT review_state, reject_reason
		FROM schedules
		WHERE schedule_id = $1;
	`

	var revState string
	var rejReason *string
	err := s.db.QueryRowContext(ctx, selectReviewQuery, scheduleID).Scan(&revState, &rejReason)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nil, fmt.Errorf("%w: %s", scheduler.ErrScheduleNotFound, scheduleID)
	}
	if err != nil {
		return "", nil, fmt.Errorf("failed to get review state for schedule %s: %w", scheduleID, err)
	}

	return revState, rejReason, nil
}

// UpdateScheduleState updates the lifecycle state of a schedule.
func (s *PostgresScheduleStorage) UpdateScheduleState(ctx context.Context, scheduleID string, state string) error {
	const updateStateQuery = `
		UPDATE schedules
		SET state = $1
		WHERE schedule_id = $2;
	`

	res, err := s.db.ExecContext(ctx, updateStateQuery, state, scheduleID)
	if err != nil {
		return fmt.Errorf("failed to update state for schedule %s: %w", scheduleID, err)
	}
	rows, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to inspect rows affected: %w", err)
	}
	if rows == 0 {
		return fmt.Errorf("%w: %s", scheduler.ErrScheduleNotFound, scheduleID)
	}

	return nil
}

// GetScheduleState retrieves the lifecycle state of a schedule.
func (s *PostgresScheduleStorage) GetScheduleState(ctx context.Context, scheduleID string) (string, error) {
	const selectStateQuery = `
		SELECT state
		FROM schedules
		WHERE schedule_id = $1;
	`

	var state string
	err := s.db.QueryRowContext(ctx, selectStateQuery, scheduleID).Scan(&state)
	if errors.Is(err, sql.ErrNoRows) {
		return "", fmt.Errorf("%w: %s", scheduler.ErrScheduleNotFound, scheduleID)
	}
	if err != nil {
		return "", fmt.Errorf("failed to get state for schedule %s: %w", scheduleID, err)
	}

	return state, nil
}

func formatIntArray(nodes []uint8) string {
	if len(nodes) == 0 {
		return "{}"
	}
	var sb strings.Builder
	sb.WriteString("{")
	for i, n := range nodes {
		if i > 0 {
			sb.WriteString(",")
		}
		sb.WriteString(strconv.Itoa(int(n)))
	}
	sb.WriteString("}")
	return sb.String()
}

func parseIntArray(s string) ([]uint8, error) {
	s = strings.TrimSpace(s)
	if s == "" || s == "{}" {
		return []uint8{}, nil
	}
	s = strings.TrimPrefix(s, "{")
	s = strings.TrimSuffix(s, "}")
	parts := strings.Split(s, ",")
	res := make([]uint8, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		val, err := strconv.ParseUint(p, 10, 8)
		if err != nil {
			return nil, fmt.Errorf("invalid int in array %q: %w", p, err)
		}
		res = append(res, uint8(val))
	}
	return res, nil
}
