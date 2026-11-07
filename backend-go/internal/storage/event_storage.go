package storage

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

var (
	// ErrEventNotFound indicates no discrete event record matches the gateway and event ID.
	ErrEventNotFound = errors.New("event not found")
	// ErrAlertNotFound indicates no alert matches the specified ID.
	ErrAlertNotFound = errors.New("alert not found")
	// ErrConflictingPayload indicates that an event with the same ID was submitted with differing business data.
	ErrConflictingPayload = errors.New("conflicting payload detected for existing event_id")
	// ErrHealthNotFound indicates no health record exists for the given gateway and node ID.
	ErrHealthNotFound = errors.New("node health record not found")
	// ErrAlreadyAcknowledged indicates the event/alert has already been acknowledged.
	ErrAlreadyAcknowledged = errors.New("alert is already acknowledged")
	// ErrInvalidAlertFilter indicates one or more filter parameters violate validation constraints.
	ErrInvalidAlertFilter = domain.ErrInvalidAlertFilter
)

// EventRecordResult details the persistence outcome of an Event.
type EventRecordResult struct {
	EventID     int64
	IsDuplicate bool
	Status      string
}

// QuarantineRecord encapsulates an invalid, conflicting, or unauthorized payload for investigation.
type QuarantineRecord struct {
	GatewayID         string
	EventID           string
	ConflictReason    string
	ExpectedSHA256    []byte
	ConflictingSHA256 []byte
	RawPayload        string
}

// EventRepository defines the storage interface for discrete Event ingest, idempotency, quarantine, and health.
type EventRepository interface {
	RecordEvent(ctx context.Context, event *domain.Event) (*EventRecordResult, error)
	GetEvent(ctx context.Context, gatewayID, eventID string) (*domain.Event, error)
	QuarantineEvent(ctx context.Context, q *QuarantineRecord) error
	RecordHealthUpdate(ctx context.Context, h *domain.NodeHealth) error
	GetNodeHealth(ctx context.Context, gatewayID string, nodeID uint8) (*domain.NodeHealth, error)
}

// AlertRepository defines query and operator workflow acknowledgment operations for REST APIs.
type AlertRepository interface {
	ListAlerts(ctx context.Context, filter domain.AlertFilter) (*domain.AlertPage, error)
	AcknowledgeAlert(ctx context.Context, alertID int64, acknowledgedBy string) (*domain.AlertView, error)
}

// EventQueryRepository defines query and operator workflow acknowledgment operations for REST APIs.
type EventQueryRepository interface {
	EventRepository
	ListEvents(ctx context.Context, cursor int64, limit int) ([]*domain.Event, int64, error)
	AcknowledgeEvent(ctx context.Context, alertID int64, acknowledgedBy string) (*domain.Event, error)
	ListNodeHealth(ctx context.Context, gatewayID string, limit int) ([]*domain.NodeHealth, error)
}

// PostgresEventStorage implements EventRepository on PostgreSQL with strict row-level lock idempotency.
type PostgresEventStorage struct {
	db *sql.DB
}

// NewPostgresEventStorage creates a new PostgresEventStorage instance.
func NewPostgresEventStorage(db *sql.DB) *PostgresEventStorage {
	return &PostgresEventStorage{db: db}
}

// RecordEvent idempotently records an active V2 event or deduplicates identical replays.
// If a conflicting payload is presented with an existing event_id, it quarantines the payload and fails closed.
func (s *PostgresEventStorage) RecordEvent(ctx context.Context, event *domain.Event) (*EventRecordResult, error) {
	if event == nil {
		return nil, errors.New("event cannot be nil")
	}
	if err := event.Validate(); err != nil {
		return nil, fmt.Errorf("event validation failed: %w", err)
	}

	payloadHash := event.ComputePayloadSHA256()
	event.RawPayloadSHA256 = payloadHash

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return nil, fmt.Errorf("failed to begin event transaction: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	const checkQuery = `
		SELECT id, raw_payload_sha256
		FROM events
		WHERE gateway_id = $1 AND event_id = $2
		FOR UPDATE;
	`

	var existingID int64
	var existingHash []byte

	err = tx.QueryRowContext(ctx, checkQuery, event.GatewayID, event.EventID).Scan(&existingID, &existingHash)
	if err == nil {
		// Existing event found: verify payload identity
		if bytes.Equal(existingHash, payloadHash[:]) {
			// Exact duplicate: commit transaction and return deduplicated result
			if commitErr := tx.Commit(); commitErr != nil {
				return nil, fmt.Errorf("failed to commit duplicate event transaction: %w", commitErr)
			}
			return &EventRecordResult{
				EventID:     existingID,
				IsDuplicate: true,
				Status:      "DEDUPLICATED",
			}, nil
		}

		// Conflict: same identity, different business payload! Fail closed and quarantine.
		_ = tx.Rollback()
		qErr := s.QuarantineEvent(ctx, &QuarantineRecord{
			GatewayID:         event.GatewayID,
			EventID:           event.EventID,
			ConflictReason:    "CONFLICTING_PAYLOAD_HASH",
			ExpectedSHA256:    existingHash,
			ConflictingSHA256: payloadHash[:],
			RawPayload:        fmt.Sprintf("node_id=%d, event_ref=%d, event_code=%d, event_value=%d", event.NodeID, event.Data.EventRef, event.Data.EventCode, event.Data.EventValue),
		})
		if qErr != nil {
			return nil, fmt.Errorf("%w: failed to record quarantine: %v", ErrConflictingPayload, qErr)
		}
		return nil, ErrConflictingPayload
	}

	if !errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("failed to query existing event: %w", err)
	}

	// Insert new event
	const insertQuery = `
		INSERT INTO events (
			event_id, gateway_id, gateway_epoch, event_seq, node_id, superframe_seq,
			seq_num, schedule_version, severity, observed_at, observed_time_source,
			radio_rx_monotonic_us, buffered, radio_ack_sent, event_ref, event_code, event_value,
			slot_id, ch1_raw,
			trigger_channel, trigger_observed_raw, trigger_threshold_raw,
			raw_payload_sha256, ack_status
		) VALUES (
			$1, $2, $3, $4, $5, $6,
			$7, $8, $9, $10, $11,
			$12, $13, $14, $15, $16, $17,
			$18, $19,
			$20, $21, $22,
			$23, $24
		) RETURNING id;
	`

	var triggerChan sql.NullInt32
	var triggerObs sql.NullInt32
	var triggerThresh sql.NullInt32
	if event.Trigger != nil {
		triggerChan = sql.NullInt32{Int32: int32(event.Trigger.Channel), Valid: true}
		triggerObs = sql.NullInt32{Int32: event.Trigger.ObservedRaw, Valid: true}
		triggerThresh = sql.NullInt32{Int32: event.Trigger.ThresholdRaw, Valid: true}
	}

	var insertedID int64
	err = tx.QueryRowContext(
		ctx,
		insertQuery,
		event.EventID,
		event.GatewayID,
		event.GatewayEpoch,
		event.EventSeq,
		int(event.NodeID),
		int64(event.SuperframeSeq),
		int(event.SeqNum),
		int64(event.ScheduleVersion),
		string(event.Severity),
		event.ObservedAt,
		string(event.ObservedTimeSource),
		event.RadioRxMonotonicUS,
		event.Buffered,
		event.RadioAckSent,
		int64(event.Data.EventRef),
		int(event.Data.EventCode),
		int(event.Data.EventValue),
		int(event.Data.EventRef),
		int(event.Data.EventValue),
		triggerChan,
		triggerObs,
		triggerThresh,
		payloadHash[:],
		string(domain.AckStatusUnacknowledged),
	).Scan(&insertedID)

	if err != nil {
		return nil, fmt.Errorf("failed to insert discrete event: %w", err)
	}

	if commitErr := tx.Commit(); commitErr != nil {
		return nil, fmt.Errorf("failed to commit new event: %w", commitErr)
	}

	return &EventRecordResult{
		EventID:     insertedID,
		IsDuplicate: false,
		Status:      "INSERTED",
	}, nil
}

// GetEvent retrieves a discrete event by its gateway ID and event ID.
func (s *PostgresEventStorage) GetEvent(ctx context.Context, gatewayID, eventID string) (*domain.Event, error) {
	const query = `
		SELECT
			id, event_id, gateway_id, gateway_epoch, event_seq, node_id,
			superframe_seq, seq_num, schedule_version, severity, observed_at, observed_time_source,
			radio_rx_monotonic_us, buffered, radio_ack_sent, event_ref, event_code, event_value,
			trigger_channel, trigger_observed_raw, trigger_threshold_raw,
			raw_payload_sha256, ingested_at, ack_status, acknowledged_at, acknowledged_by
		FROM events
		WHERE gateway_id = $1 AND event_id = $2;
	`

	var e domain.Event
	var obsAt sql.NullTime
	var ackAt sql.NullTime
	var ackBy sql.NullString
	var trigChan sql.NullInt32
	var trigObs sql.NullInt32
	var trigThresh sql.NullInt32
	var nodeID, seqNum, eventCode, eventValue int
	var eventRef int64
	var rawHash []byte
	var sev, timeSrc, ackStat string

	err := s.db.QueryRowContext(ctx, query, gatewayID, eventID).Scan(
		&e.ID,
		&e.EventID,
		&e.GatewayID,
		&e.GatewayEpoch,
		&e.EventSeq,
		&nodeID,
		&e.SuperframeSeq,
		&seqNum,
		&e.ScheduleVersion,
		&sev,
		&obsAt,
		&timeSrc,
		&e.RadioRxMonotonicUS,
		&e.Buffered,
		&e.RadioAckSent,
		&eventRef,
		&eventCode,
		&eventValue,
		&trigChan,
		&trigObs,
		&trigThresh,
		&rawHash,
		&e.IngestedAt,
		&ackStat,
		&ackAt,
		&ackBy,
	)

	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrEventNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query event: %w", err)
	}

	e.NodeID = uint8(nodeID)
	e.SeqNum = uint8(seqNum)
	e.Data.EventRef = uint32(eventRef)
	e.Data.EventCode = uint8(eventCode)
	e.Data.EventValue = int16(eventValue)
	e.Severity = domain.EventSeverity(sev)
	e.ObservedTimeSource = domain.TimeSource(timeSrc)
	e.AckStatus = domain.AckStatus(ackStat)

	if obsAt.Valid {
		t := obsAt.Time.UTC()
		e.ObservedAt = &t
	}
	if ackAt.Valid {
		t := ackAt.Time.UTC()
		e.AcknowledgedAt = &t
	}
	if ackBy.Valid {
		e.AcknowledgedBy = &ackBy.String
	}
	if trigChan.Valid {
		e.Trigger = &domain.EventTrigger{
			Channel:      uint8(trigChan.Int32),
			ObservedRaw:  trigObs.Int32,
			ThresholdRaw: trigThresh.Int32,
		}
	}
	copy(e.RawPayloadSHA256[:], rawHash)

	return &e, nil
}

// QuarantineEvent records a suspicious or conflicting payload into event_quarantine.
func (s *PostgresEventStorage) QuarantineEvent(ctx context.Context, q *QuarantineRecord) error {
	if q == nil {
		return errors.New("quarantine record cannot be nil")
	}

	const query = `
		INSERT INTO event_quarantine (
			gateway_id, event_id, conflict_reason, expected_sha256, conflicting_sha256, raw_payload
		) VALUES ($1, $2, $3, $4, $5, $6);
	`

	_, err := s.db.ExecContext(
		ctx,
		query,
		q.GatewayID,
		q.EventID,
		q.ConflictReason,
		q.ExpectedSHA256,
		q.ConflictingSHA256,
		q.RawPayload,
	)
	if err != nil {
		return fmt.Errorf("failed to insert quarantine record: %w", err)
	}
	return nil
}

// RecordHealthUpdate updates or inserts per-node health from authenticated UP_HEALTH_REPLY (0x44 21B).
func (s *PostgresEventStorage) RecordHealthUpdate(ctx context.Context, h *domain.NodeHealth) error {
	if h == nil {
		return errors.New("health record cannot be nil")
	}
	if err := h.Validate(); err != nil {
		return fmt.Errorf("invalid health update: %w", err)
	}

	const query = `
		INSERT INTO node_health (
			gateway_id, node_id, session_sel, frame_counter, maint_seq, status_flags,
			pending_event_count, health_status, last_seen_at, updated_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
		ON CONFLICT (gateway_id, node_id) DO UPDATE SET
			session_sel = EXCLUDED.session_sel,
			frame_counter = EXCLUDED.frame_counter,
			maint_seq = EXCLUDED.maint_seq,
			status_flags = EXCLUDED.status_flags,
			pending_event_count = EXCLUDED.pending_event_count,
			health_status = EXCLUDED.health_status,
			last_seen_at = CURRENT_TIMESTAMP,
			updated_at = CURRENT_TIMESTAMP;
	`

	_, err := s.db.ExecContext(
		ctx,
		query,
		h.GatewayID,
		int(h.NodeID),
		int(h.SessionSel),
		int64(h.FrameCounter),
		int64(h.MaintSeq),
		int(h.StatusFlags),
		int(h.PendingEventCount),
		string(h.HealthStatus),
	)
	if err != nil {
		return fmt.Errorf("failed to record node health: %w", err)
	}
	return nil
}

// GetNodeHealth queries the latest reported health status of a Node.
func (s *PostgresEventStorage) GetNodeHealth(ctx context.Context, gatewayID string, nodeID uint8) (*domain.NodeHealth, error) {
	const query = `
		SELECT
			gateway_id, node_id, session_sel, frame_counter, maint_seq, status_flags,
			pending_event_count, health_status, last_seen_at, updated_at
		FROM node_health
		WHERE gateway_id = $1 AND node_id = $2;
	`

	var h domain.NodeHealth
	var nID, sessionSel, flags, pending int
	var frameCounter, maintSeq int64
	var status string

	err := s.db.QueryRowContext(ctx, query, gatewayID, int(nodeID)).Scan(
		&h.GatewayID,
		&nID,
		&sessionSel,
		&frameCounter,
		&maintSeq,
		&flags,
		&pending,
		&status,
		&h.LastSeenAt,
		&h.UpdatedAt,
	)

	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrHealthNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query node health: %w", err)
	}

	h.NodeID = uint8(nID)
	h.SessionSel = uint8(sessionSel)
	h.FrameCounter = uint32(frameCounter)
	h.MaintSeq = uint32(maintSeq)
	h.StatusFlags = uint8(flags)
	h.PendingEventCount = uint8(pending)
	h.HealthStatus = domain.HealthStatus(status)

	return &h, nil
}

// ListEvents retrieves cursor-paginated events ordered by ID descending.
// cursor == 0 indicates the first page.
// Returns items and nextCursor (0 if no further items).
func (s *PostgresEventStorage) ListEvents(ctx context.Context, cursor int64, limit int) ([]*domain.Event, int64, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 100 {
		limit = 100
	}

	var query string
	var args []any
	if cursor > 0 {
		query = `
			SELECT
				id, event_id, gateway_id, gateway_epoch, event_seq, node_id,
				superframe_seq, seq_num, schedule_version, severity, observed_at, observed_time_source,
				radio_rx_monotonic_us, buffered, radio_ack_sent, event_ref, event_code, event_value,
				raw_payload_sha256, ingested_at, ack_status, acknowledged_at, acknowledged_by
			FROM events
			WHERE id < $1
			ORDER BY id DESC
			LIMIT $2;
		`
		args = []any{cursor, limit}
	} else {
		query = `
			SELECT
				id, event_id, gateway_id, gateway_epoch, event_seq, node_id,
				superframe_seq, seq_num, schedule_version, severity, observed_at, observed_time_source,
				radio_rx_monotonic_us, buffered, radio_ack_sent, event_ref, event_code, event_value,
				raw_payload_sha256, ingested_at, ack_status, acknowledged_at, acknowledged_by
			FROM events
			ORDER BY id DESC
			LIMIT $1;
		`
		args = []any{limit}
	}

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, 0, fmt.Errorf("failed to query events: %w", err)
	}
	defer rows.Close()

	var events []*domain.Event
	for rows.Next() {
		var e domain.Event
		var obsAt sql.NullTime
		var ackAt sql.NullTime
		var ackBy sql.NullString
		var nodeID, seqNum, eventCode, eventValue int
		var eventRef int64
		var rawHash []byte
		var sev, timeSrc, ackStat string

		if err := rows.Scan(
			&e.ID,
			&e.EventID,
			&e.GatewayID,
			&e.GatewayEpoch,
			&e.EventSeq,
			&nodeID,
			&e.SuperframeSeq,
			&seqNum,
			&e.ScheduleVersion,
			&sev,
			&obsAt,
			&timeSrc,
			&e.RadioRxMonotonicUS,
			&e.Buffered,
			&e.RadioAckSent,
			&eventRef,
			&eventCode,
			&eventValue,
			&rawHash,
			&e.IngestedAt,
			&ackStat,
			&ackAt,
			&ackBy,
		); err != nil {
			return nil, 0, fmt.Errorf("failed to scan event row: %w", err)
		}

		e.NodeID = uint8(nodeID)
		e.SeqNum = uint8(seqNum)
		e.Data.EventRef = uint32(eventRef)
		e.Data.EventCode = uint8(eventCode)
		e.Data.EventValue = int16(eventValue)
		e.Severity = domain.EventSeverity(sev)
		e.ObservedTimeSource = domain.TimeSource(timeSrc)
		e.AckStatus = domain.AckStatus(ackStat)

		if obsAt.Valid {
			t := obsAt.Time.UTC()
			e.ObservedAt = &t
		}
		if ackAt.Valid {
			t := ackAt.Time.UTC()
			e.AcknowledgedAt = &t
		}
		if ackBy.Valid {
			e.AcknowledgedBy = &ackBy.String
		}
		copy(e.RawPayloadSHA256[:], rawHash)
		events = append(events, &e)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("error reading event rows: %w", err)
	}

	var nextCursor int64
	if len(events) == limit {
		nextCursor = events[len(events)-1].ID
	}
	return events, nextCursor, nil
}

// AcknowledgeEvent updates the acknowledgment status of an event by its database ID.
// Returns ErrAlreadyAcknowledged if already acknowledged, and ErrEventNotFound if not found.
func (s *PostgresEventStorage) AcknowledgeEvent(ctx context.Context, alertID int64, acknowledgedBy string) (*domain.Event, error) {
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return nil, fmt.Errorf("failed to begin acknowledge transaction: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	const checkQuery = `
		SELECT ack_status
		FROM events
		WHERE id = $1
		FOR UPDATE;
	`
	var currentStatus string
	err = tx.QueryRowContext(ctx, checkQuery, alertID).Scan(&currentStatus)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrEventNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to check event status: %w", err)
	}
	if domain.AckStatus(currentStatus) == domain.AckStatusAcknowledged {
		return nil, ErrAlreadyAcknowledged
	}

	const updateQuery = `
		UPDATE events
		SET ack_status = 'ACKNOWLEDGED',
		    acknowledged_at = CURRENT_TIMESTAMP,
		    acknowledged_by = $1
		WHERE id = $2;
	`
	if _, err := tx.ExecContext(ctx, updateQuery, acknowledgedBy, alertID); err != nil {
		return nil, fmt.Errorf("failed to update event ack status: %w", err)
	}

	const selectQuery = `
		SELECT
			id, event_id, gateway_id, gateway_epoch, event_seq, node_id,
			superframe_seq, seq_num, schedule_version, severity, observed_at, observed_time_source,
			radio_rx_monotonic_us, buffered, radio_ack_sent, event_ref, event_code, event_value,
			raw_payload_sha256, ingested_at, ack_status, acknowledged_at, acknowledged_by
		FROM events
		WHERE id = $1;
	`
	var e domain.Event
	var obsAt sql.NullTime
	var ackAt sql.NullTime
	var ackBy sql.NullString
	var nodeID, seqNum, eventCode, eventValue int
	var eventRef int64
	var rawHash []byte
	var sev, timeSrc, ackStat string

	err = tx.QueryRowContext(ctx, selectQuery, alertID).Scan(
		&e.ID,
		&e.EventID,
		&e.GatewayID,
		&e.GatewayEpoch,
		&e.EventSeq,
		&nodeID,
		&e.SuperframeSeq,
		&seqNum,
		&e.ScheduleVersion,
		&sev,
		&obsAt,
		&timeSrc,
		&e.RadioRxMonotonicUS,
		&e.Buffered,
		&e.RadioAckSent,
		&eventRef,
		&eventCode,
		&eventValue,
		&rawHash,
		&e.IngestedAt,
		&ackStat,
		&ackAt,
		&ackBy,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to load updated event: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("failed to commit acknowledge transaction: %w", err)
	}

	e.NodeID = uint8(nodeID)
	e.SeqNum = uint8(seqNum)
	e.Data.EventRef = uint32(eventRef)
	e.Data.EventCode = uint8(eventCode)
	e.Data.EventValue = int16(eventValue)
	e.Severity = domain.EventSeverity(sev)
	e.ObservedTimeSource = domain.TimeSource(timeSrc)
	e.AckStatus = domain.AckStatus(ackStat)

	if obsAt.Valid {
		t := obsAt.Time.UTC()
		e.ObservedAt = &t
	}
	if ackAt.Valid {
		t := ackAt.Time.UTC()
		e.AcknowledgedAt = &t
	}
	if ackBy.Valid {
		e.AcknowledgedBy = &ackBy.String
	}
	copy(e.RawPayloadSHA256[:], rawHash)

	return &e, nil
}

// ListAlerts retrieves cursor-paginated alerts ordered by ID descending with optional filtering.
func (s *PostgresEventStorage) ListAlerts(ctx context.Context, filter domain.AlertFilter) (*domain.AlertPage, error) {
	if err := filter.Validate(); err != nil {
		return nil, fmt.Errorf("%w: %w", ErrInvalidAlertFilter, err)
	}

	limit := filter.Limit
	if limit <= 0 {
		limit = 50
	}
	if limit > 100 {
		limit = 100
	}

	var cursorID int64
	if filter.Cursor != "" {
		parsed, err := strconv.ParseInt(filter.Cursor, 10, 64)
		if err != nil || parsed < 0 {
			return nil, fmt.Errorf("%w: cursor must be a non-negative decimal string", ErrInvalidAlertFilter)
		}
		cursorID = parsed
	}

	var conditions []string
	var args []any
	argIdx := 1

	if cursorID > 0 {
		conditions = append(conditions, fmt.Sprintf("id < $%d", argIdx))
		args = append(args, cursorID)
		argIdx++
	}
	if filter.Severity != "" {
		conditions = append(conditions, fmt.Sprintf("severity = $%d", argIdx))
		args = append(args, filter.Severity)
		argIdx++
	}
	if filter.NodeID != nil {
		conditions = append(conditions, fmt.Sprintf("node_id = $%d", argIdx))
		args = append(args, *filter.NodeID)
		argIdx++
	}
	if filter.GatewayID != "" {
		conditions = append(conditions, fmt.Sprintf("gateway_id = $%d", argIdx))
		args = append(args, filter.GatewayID)
		argIdx++
	}
	if filter.AckStatus != "" {
		conditions = append(conditions, fmt.Sprintf("ack_status = $%d", argIdx))
		args = append(args, filter.AckStatus)
		argIdx++
	}

	query := `
		SELECT
			id, event_id, gateway_id, gateway_epoch, event_seq, node_id,
			superframe_seq, seq_num, schedule_version, severity, observed_at, observed_time_source,
			radio_rx_monotonic_us, buffered, radio_ack_sent, event_ref, event_code, event_value,
			raw_payload_sha256, ingested_at, ack_status, acknowledged_at, acknowledged_by
		FROM events
	`
	if len(conditions) > 0 {
		query += " WHERE " + strings.Join(conditions, " AND ")
	}
	query += fmt.Sprintf(" ORDER BY id DESC LIMIT $%d;", argIdx)
	args = append(args, limit+1)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query alerts: %w", err)
	}
	defer rows.Close()

	var items []domain.AlertView
	for rows.Next() {
		var e domain.Event
		var obsAt sql.NullTime
		var ackAt sql.NullTime
		var ackBy sql.NullString
		var nodeID, seqNum, eventCode, eventValue int
		var eventRef int64
		var rawHash []byte
		var sev, timeSrc, ackStat string

		if err := rows.Scan(
			&e.ID,
			&e.EventID,
			&e.GatewayID,
			&e.GatewayEpoch,
			&e.EventSeq,
			&nodeID,
			&e.SuperframeSeq,
			&seqNum,
			&e.ScheduleVersion,
			&sev,
			&obsAt,
			&timeSrc,
			&e.RadioRxMonotonicUS,
			&e.Buffered,
			&e.RadioAckSent,
			&eventRef,
			&eventCode,
			&eventValue,
			&rawHash,
			&e.IngestedAt,
			&ackStat,
			&ackAt,
			&ackBy,
		); err != nil {
			return nil, fmt.Errorf("failed to scan alert row: %w", err)
		}

		e.NodeID = uint8(nodeID)
		e.SeqNum = uint8(seqNum)
		e.Data.EventRef = uint32(eventRef)
		e.Data.EventCode = uint8(eventCode)
		e.Data.EventValue = int16(eventValue)
		e.Severity = domain.EventSeverity(sev)
		e.ObservedTimeSource = domain.TimeSource(timeSrc)
		e.AckStatus = domain.AckStatus(ackStat)

		if obsAt.Valid {
			t := obsAt.Time.UTC()
			e.ObservedAt = &t
		}
		if ackAt.Valid {
			t := ackAt.Time.UTC()
			e.AcknowledgedAt = &t
		}
		if ackBy.Valid {
			e.AcknowledgedBy = &ackBy.String
		}
		copy(e.RawPayloadSHA256[:], rawHash)

		items = append(items, domain.EventToAlertView(&e))
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error reading alert rows: %w", err)
	}

	var nextCursor *string
	if len(items) > limit {
		items = items[:limit]
		cursorStr := items[len(items)-1].AlertID
		nextCursor = &cursorStr
	}

	if items == nil {
		items = []domain.AlertView{}
	}

	return &domain.AlertPage{
		Items:      items,
		NextCursor: nextCursor,
	}, nil
}

// AcknowledgeAlert updates the acknowledgment status of an alert by its record ID.
// Idempotent: If already acknowledged, it returns the current record without error.
// If the alert ID does not exist, it returns ErrAlertNotFound.
func (s *PostgresEventStorage) AcknowledgeAlert(ctx context.Context, alertID int64, acknowledgedBy string) (*domain.AlertView, error) {
	if acknowledgedBy == "" {
		acknowledgedBy = "operator"
	}

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return nil, fmt.Errorf("failed to begin acknowledge transaction: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	const checkQuery = `
		SELECT ack_status
		FROM events
		WHERE id = $1
		FOR UPDATE;
	`
	var currentStatus string
	err = tx.QueryRowContext(ctx, checkQuery, alertID).Scan(&currentStatus)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrAlertNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to check alert status: %w", err)
	}

	// Idempotent: if already acknowledged, do not re-update, just query and return
	if domain.AckStatus(currentStatus) != domain.AckStatusAcknowledged {
		const updateQuery = `
			UPDATE events
			SET ack_status = 'ACKNOWLEDGED',
			    acknowledged_at = CURRENT_TIMESTAMP,
			    acknowledged_by = $1
			WHERE id = $2;
		`
		if _, err := tx.ExecContext(ctx, updateQuery, acknowledgedBy, alertID); err != nil {
			return nil, fmt.Errorf("failed to update alert ack status: %w", err)
		}
	}

	const selectQuery = `
		SELECT
			id, event_id, gateway_id, gateway_epoch, event_seq, node_id,
			superframe_seq, seq_num, schedule_version, severity, observed_at, observed_time_source,
			radio_rx_monotonic_us, buffered, radio_ack_sent, event_ref, event_code, event_value,
			raw_payload_sha256, ingested_at, ack_status, acknowledged_at, acknowledged_by
		FROM events
		WHERE id = $1;
	`
	var e domain.Event
	var obsAt sql.NullTime
	var ackAt sql.NullTime
	var ackBy sql.NullString
	var nodeID, seqNum, eventCode, eventValue int
	var eventRef int64
	var rawHash []byte
	var sev, timeSrc, ackStat string

	err = tx.QueryRowContext(ctx, selectQuery, alertID).Scan(
		&e.ID,
		&e.EventID,
		&e.GatewayID,
		&e.GatewayEpoch,
		&e.EventSeq,
		&nodeID,
		&e.SuperframeSeq,
		&seqNum,
		&e.ScheduleVersion,
		&sev,
		&obsAt,
		&timeSrc,
		&e.RadioRxMonotonicUS,
		&e.Buffered,
		&e.RadioAckSent,
		&eventRef,
		&eventCode,
		&eventValue,
		&rawHash,
		&e.IngestedAt,
		&ackStat,
		&ackAt,
		&ackBy,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to load acknowledged alert: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("failed to commit acknowledge transaction: %w", err)
	}

	e.NodeID = uint8(nodeID)
	e.SeqNum = uint8(seqNum)
	e.Data.EventRef = uint32(eventRef)
	e.Data.EventCode = uint8(eventCode)
	e.Data.EventValue = int16(eventValue)
	e.Severity = domain.EventSeverity(sev)
	e.ObservedTimeSource = domain.TimeSource(timeSrc)
	e.AckStatus = domain.AckStatus(ackStat)

	if obsAt.Valid {
		t := obsAt.Time.UTC()
		e.ObservedAt = &t
	}
	if ackAt.Valid {
		t := ackAt.Time.UTC()
		e.AcknowledgedAt = &t
	}
	if ackBy.Valid {
		e.AcknowledgedBy = &ackBy.String
	}
	copy(e.RawPayloadSHA256[:], rawHash)

	view := domain.EventToAlertView(&e)
	return &view, nil
}

// ListNodeHealth queries all confirmed node health records.
func (s *PostgresEventStorage) ListNodeHealth(ctx context.Context, gatewayID string, limit int) ([]*domain.NodeHealth, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 100 {
		limit = 100
	}

	var query string
	var args []any
	if gatewayID != "" {
		query = `
			SELECT
				gateway_id, node_id, session_sel, frame_counter, maint_seq, status_flags,
				pending_event_count, health_status, last_seen_at, updated_at
			FROM node_health
			WHERE gateway_id = $1
			ORDER BY node_id ASC
			LIMIT $2;
		`
		args = []any{gatewayID, limit}
	} else {
		query = `
			SELECT
				gateway_id, node_id, session_sel, frame_counter, maint_seq, status_flags,
				pending_event_count, health_status, last_seen_at, updated_at
			FROM node_health
			ORDER BY node_id ASC
			LIMIT $1;
		`
		args = []any{limit}
	}

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query node health list: %w", err)
	}
	defer rows.Close()

	var list []*domain.NodeHealth
	for rows.Next() {
		var h domain.NodeHealth
		var nID, sessionSel, flags, pending int
		var frameCounter, maintSeq int64
		var status string

		if err := rows.Scan(
			&h.GatewayID,
			&nID,
			&sessionSel,
			&frameCounter,
			&maintSeq,
			&flags,
			&pending,
			&status,
			&h.LastSeenAt,
			&h.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan node health row: %w", err)
		}

		h.NodeID = uint8(nID)
		h.SessionSel = uint8(sessionSel)
		h.FrameCounter = uint32(frameCounter)
		h.MaintSeq = uint32(maintSeq)
		h.StatusFlags = uint8(flags)
		h.PendingEventCount = uint8(pending)
		h.HealthStatus = domain.HealthStatus(status)
		list = append(list, &h)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error reading node health rows: %w", err)
	}
	return list, nil
}
