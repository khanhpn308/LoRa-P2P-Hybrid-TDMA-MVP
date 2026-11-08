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
	ListGateways(ctx context.Context) ([]*domain.GatewayItem, error)
	CreateGateway(ctx context.Context, gatewayID, name, location, ipAddress string) error
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

// ListGateways retrieves all gateways known from the registry and/or live reporting.
func (s *PostgresStatusStorage) ListGateways(ctx context.Context) ([]*domain.GatewayItem, error) {
	const query = `
		WITH all_gw_ids AS (
			SELECT gateway_id FROM gateways
			UNION
			SELECT gateway_id FROM gateway_status
			UNION
			SELECT gateway_id FROM gateway_channel_allocations WHERE status = 'ALLOCATED'
		)
		SELECT
			id.gateway_id AS gw_id,
			COALESCE(g.name, CONCAT('Trạm điều hành ', id.gateway_id)) AS gw_name,
			COALESCE(g.location, 'Khu vực chung') AS gw_loc,
			COALESCE(g.ip_address, '') AS gw_ip,
			COALESCE(s.mode, 'OFFLINE') AS gw_mode,
			COALESCE(s.active_schedule_version, 0) AS sched_ver,
			COALESCE(s.channel_id, a.channel_id, 'CH00') AS ch_id,
			COALESCE(c.center_frequency_hz, 920250000) AS freq_hz,
			COALESCE(s.rf_duty_permille, 0) AS duty,
			COALESCE(s.node_count, 0) AS nodes,
			s.last_seen_at
		FROM all_gw_ids id
		LEFT JOIN gateways g ON g.gateway_id = id.gateway_id
		LEFT JOIN gateway_status s ON s.gateway_id = id.gateway_id
		LEFT JOIN gateway_channel_allocations a ON a.gateway_id = id.gateway_id AND a.status = 'ALLOCATED'
		LEFT JOIN rf_channels c ON c.channel_id = COALESCE(s.channel_id, a.channel_id, 'CH00')
		ORDER BY gw_id ASC;
	`

	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to query gateways: %w", err)
	}
	defer rows.Close()

	var items []*domain.GatewayItem
	for rows.Next() {
		var item domain.GatewayItem
		var lastSeen sql.NullTime
		var schedVer int64
		var freqHz int64

		if err := rows.Scan(
			&item.GatewayID,
			&item.Name,
			&item.Location,
			&item.IPAddress,
			&item.Mode,
			&schedVer,
			&item.ChannelID,
			&freqHz,
			&item.RFDutyPermille,
			&item.NodeCount,
			&lastSeen,
		); err != nil {
			return nil, fmt.Errorf("failed to scan gateway item: %w", err)
		}

		item.ActiveScheduleVersion = uint32(schedVer)
		item.FrequencyHz = uint64(freqHz)
		if lastSeen.Valid {
			formatted := lastSeen.Time.UTC().Format(time.RFC3339)
			item.LastSeenAt = &formatted
		}

		items = append(items, &item)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating gateways: %w", err)
	}

	return items, nil
}

// CreateGateway registers or updates a gateway in the metadata registry.
func (s *PostgresStatusStorage) CreateGateway(ctx context.Context, gatewayID, name, location, ipAddress string) error {
	if !domain.GatewayIDPattern.MatchString(gatewayID) {
		return fmt.Errorf("%w: '%s'", domain.ErrInvalidGatewayID, gatewayID)
	}
	if name == "" {
		name = fmt.Sprintf("Trạm điều hành %s", gatewayID)
	}
	if location == "" {
		location = "Khu vực chung"
	}

	const query = `
		INSERT INTO gateways (gateway_id, name, location, ip_address, updated_at)
		VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
		ON CONFLICT (gateway_id) DO UPDATE SET
			name = EXCLUDED.name,
			location = EXCLUDED.location,
			ip_address = EXCLUDED.ip_address,
			updated_at = CURRENT_TIMESTAMP;
	`

	_, err := s.db.ExecContext(ctx, query, gatewayID, name, location, ipAddress)
	if err != nil {
		return fmt.Errorf("failed to upsert gateway registry: %w", err)
	}
	return nil
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
