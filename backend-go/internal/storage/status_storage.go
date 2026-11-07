package storage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

var (
	// ErrGatewayStatusNotFound indicates no operational status record was found for the gateway.
	ErrGatewayStatusNotFound = errors.New("gateway status record not found")
)

// StatusStorage defines the repository operations for Gateway status snapshots and Node monitoring.
type StatusStorage interface {
	UpsertGatewayStatus(ctx context.Context, status *domain.GatewayStatusRecord) error
	GetGatewayStatus(ctx context.Context, gatewayID string) (*domain.GatewayStatusRecord, error)
	ListNodes(ctx context.Context, filter domain.NodeFilter) (*domain.NodePage, error)
}

// PostgresStatusStorage implements StatusStorage using PostgreSQL with parameterized queries.
type PostgresStatusStorage struct {
	db *sql.DB
}

// NewPostgresStatusStorage creates a new PostgresStatusStorage instance.
func NewPostgresStatusStorage(db *sql.DB) *PostgresStatusStorage {
	return &PostgresStatusStorage{db: db}
}

// UpsertGatewayStatus idempotently stores or updates a Gateway status snapshot keyed by gateway_id.
// Authority: DB-001, DB-002, DB-003.
func (s *PostgresStatusStorage) UpsertGatewayStatus(ctx context.Context, status *domain.GatewayStatusRecord) error {
	if status == nil {
		return errors.New("gateway status record cannot be nil")
	}
	if err := status.Validate(); err != nil {
		return fmt.Errorf("gateway status validation failed: %w", err)
	}

	const query = `
		INSERT INTO gateway_status (
			gateway_id, gateway_epoch, mode, active_schedule_version,
			channel_id, rf_duty_permille, node_count, free_heap_bytes,
			offline_queue_count, pending_event_count, dropped_event_count,
			last_seen_at, updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, CURRENT_TIMESTAMP
		)
		ON CONFLICT (gateway_id) DO UPDATE SET
			gateway_epoch = EXCLUDED.gateway_epoch,
			mode = EXCLUDED.mode,
			active_schedule_version = EXCLUDED.active_schedule_version,
			channel_id = EXCLUDED.channel_id,
			rf_duty_permille = EXCLUDED.rf_duty_permille,
			node_count = EXCLUDED.node_count,
			free_heap_bytes = EXCLUDED.free_heap_bytes,
			offline_queue_count = EXCLUDED.offline_queue_count,
			pending_event_count = EXCLUDED.pending_event_count,
			dropped_event_count = EXCLUDED.dropped_event_count,
			last_seen_at = EXCLUDED.last_seen_at,
			updated_at = CURRENT_TIMESTAMP;
	`

	lastSeen := status.LastSeenAt
	if lastSeen.IsZero() {
		lastSeen = time.Now().UTC()
	}

	_, err := s.db.ExecContext(ctx, query,
		status.GatewayID,
		status.GatewayEpoch,
		string(status.Mode),
		int64(status.ActiveScheduleVersion),
		status.ChannelID,
		status.RFDutyPermille,
		status.NodeCount,
		int64(status.FreeHeapBytes),
		int64(status.OfflineQueueCount),
		int(status.PendingEventCount),
		status.DroppedEventCount,
		lastSeen,
	)
	if err != nil {
		return fmt.Errorf("failed to upsert gateway status: %w", err)
	}
	return nil
}

// GetGatewayStatus fetches the last-known operational status of a Gateway.
func (s *PostgresStatusStorage) GetGatewayStatus(ctx context.Context, gatewayID string) (*domain.GatewayStatusRecord, error) {
	if !domain.GatewayIDPattern.MatchString(gatewayID) {
		return nil, fmt.Errorf("%w: '%s'", domain.ErrInvalidGatewayID, gatewayID)
	}

	const query = `
		SELECT
			gateway_id, gateway_epoch, mode, active_schedule_version,
			channel_id, rf_duty_permille, node_count, free_heap_bytes,
			offline_queue_count, pending_event_count, dropped_event_count,
			last_seen_at, updated_at
		FROM gateway_status
		WHERE gateway_id = $1;
	`

	var rec domain.GatewayStatusRecord
	var modeStr string
	var schedVer, freeHeap, offQueue int64
	var pending int
	var droppedStr string

	err := s.db.QueryRowContext(ctx, query, gatewayID).Scan(
		&rec.GatewayID,
		&rec.GatewayEpoch,
		&modeStr,
		&schedVer,
		&rec.ChannelID,
		&rec.RFDutyPermille,
		&rec.NodeCount,
		&freeHeap,
		&offQueue,
		&pending,
		&droppedStr,
		&rec.LastSeenAt,
		&rec.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrGatewayStatusNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query gateway status: %w", err)
	}

	rec.Mode = domain.GatewayMode(modeStr)
	rec.ActiveScheduleVersion = uint32(schedVer)
	rec.FreeHeapBytes = uint64(freeHeap)
	rec.OfflineQueueCount = uint32(offQueue)
	rec.PendingEventCount = uint8(pending)

	dropped, _ := strconv.ParseUint(droppedStr, 10, 64)
	rec.DroppedEventCount = dropped

	return &rec, nil
}

// ListNodes queries confirmed node health records with cursor pagination and optional gateway and status filters.
func (s *PostgresStatusStorage) ListNodes(ctx context.Context, filter domain.NodeFilter) (*domain.NodePage, error) {
	if err := filter.Validate(); err != nil {
		return nil, err
	}

	limit := filter.Limit
	if limit <= 0 {
		limit = 50
	}
	if limit > 100 {
		limit = 100
	}

	cursorNodeID := 0
	if filter.Cursor != "" {
		c, err := strconv.Atoi(filter.Cursor)
		if err != nil || c < 0 {
			return nil, fmt.Errorf("%w: '%s'", domain.ErrInvalidCursor, filter.Cursor)
		}
		cursorNodeID = c
	}

	const query = `
		SELECT
			nh.node_id,
			nh.gateway_id,
			nh.health_status,
			nh.last_seen_at
		FROM node_health nh
		WHERE ($1 = '' OR nh.gateway_id = $1)
		  AND ($2 = '' OR nh.health_status = $2)
		  AND nh.node_id > $3
		ORDER BY nh.node_id ASC
		LIMIT $4;
	`

	rows, err := s.db.QueryContext(ctx, query, filter.GatewayID, filter.Status, cursorNodeID, limit+1)
	if err != nil {
		return nil, fmt.Errorf("failed to query nodes list: %w", err)
	}
	defer rows.Close()

	var items []domain.NodeSummary
	for rows.Next() {
		var nID int
		var gwID, status string
		var lastSeen time.Time

		if err := rows.Scan(&nID, &gwID, &status, &lastSeen); err != nil {
			return nil, fmt.Errorf("failed to scan node row: %w", err)
		}

		slotID := nID
		lastSeenStr := lastSeen.UTC().Format(time.RFC3339)
		items = append(items, domain.NodeSummary{
			NodeID:         nID,
			GatewayID:      gwID,
			AssignedSlotID: &slotID,
			LastSeenAt:     &lastSeenStr,
			Status:         status,
		})
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error reading node rows: %w", err)
	}

	var nextCursor *string
	if len(items) > limit {
		cursorStr := strconv.Itoa(items[limit-1].NodeID)
		nextCursor = &cursorStr
		items = items[:limit]
	}

	return &domain.NodePage{
		Items:      items,
		NextCursor: nextCursor,
	}, nil
}
