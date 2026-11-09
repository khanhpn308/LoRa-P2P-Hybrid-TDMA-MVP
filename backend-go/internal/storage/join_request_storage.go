package storage

import (
	"context"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

var (
	ErrRequestNotFound   = errors.New("join request not found")
	ErrNoAvailableNodeID = errors.New("no available node ID in range 1-254")
)

// JoinRequestStorage manages device join requests and approval state.
type JoinRequestStorage interface {
	CreateOrUpdatePendingRequest(ctx context.Context, req *domain.DeviceJoinRequest) (*domain.DeviceJoinRequest, error)
	ListPendingRequests(ctx context.Context) ([]*domain.DeviceJoinRequest, error)
	ApproveRequest(ctx context.Context, id int64, requestedNodeID *int) (*domain.DeviceJoinRequest, error)
	RejectRequest(ctx context.Context, id int64) error
}

// PostgresJoinRequestStorage implements JoinRequestStorage with PostgreSQL.
type PostgresJoinRequestStorage struct {
	db *sql.DB
}

// NewPostgresJoinRequestStorage constructs a new PostgresJoinRequestStorage.
func NewPostgresJoinRequestStorage(db *sql.DB) *PostgresJoinRequestStorage {
	return &PostgresJoinRequestStorage{db: db}
}

// CreateOrUpdatePendingRequest inserts a new request or updates an existing pending request for the MAC.
func (s *PostgresJoinRequestStorage) CreateOrUpdatePendingRequest(ctx context.Context, req *domain.DeviceJoinRequest) (*domain.DeviceJoinRequest, error) {
	if req == nil {
		return nil, errors.New("request cannot be nil")
	}
	cleanMAC := strings.ToLower(strings.TrimSpace(req.DeviceMAC))

	const checkQuery = `
		SELECT id, created_at FROM device_join_requests
		WHERE device_mac = $1 AND status = 'PENDING'
		LIMIT 1;
	`
	var existingID int64
	var createdAt time.Time
	err := s.db.QueryRowContext(ctx, checkQuery, cleanMAC).Scan(&existingID, &createdAt)
	if err == nil {
		const updateQuery = `
			UPDATE device_join_requests
			SET gateway_id = $1, rssi = $2, snr = $3, raw_frame_hex = $4, updated_at = CURRENT_TIMESTAMP
			WHERE id = $5
			RETURNING updated_at;
		`
		var updatedAt time.Time
		if err := s.db.QueryRowContext(ctx, updateQuery, req.GatewayID, req.RSSI, req.SNR, req.RawFrameHex, existingID).Scan(&updatedAt); err != nil {
			return nil, fmt.Errorf("failed to update pending join request: %w", err)
		}
		req.ID = existingID
		req.Status = "PENDING"
		req.CreatedAt = createdAt.UTC()
		req.UpdatedAt = updatedAt.UTC()
		return req, nil
	}

	const insertQuery = `
		INSERT INTO device_join_requests (device_mac, gateway_id, rssi, snr, raw_frame_hex, status, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, 'PENDING', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
		RETURNING id, created_at, updated_at;
	`
	var id int64
	var created, updated time.Time
	if err := s.db.QueryRowContext(ctx, insertQuery, cleanMAC, req.GatewayID, req.RSSI, req.SNR, req.RawFrameHex).Scan(&id, &created, &updated); err != nil {
		return nil, fmt.Errorf("failed to insert pending join request: %w", err)
	}

	req.ID = id
	req.DeviceMAC = cleanMAC
	req.Status = "PENDING"
	req.CreatedAt = created.UTC()
	req.UpdatedAt = updated.UTC()
	return req, nil
}

// ListPendingRequests returns all pending join requests.
func (s *PostgresJoinRequestStorage) ListPendingRequests(ctx context.Context) ([]*domain.DeviceJoinRequest, error) {
	const query = `
		SELECT id, device_mac, gateway_id, rssi, snr, raw_frame_hex, status, assigned_node_id, created_at, updated_at
		FROM device_join_requests
		WHERE status = 'PENDING'
		ORDER BY created_at DESC;
	`
	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("failed to query pending join requests: %w", err)
	}
	defer rows.Close()

	var list []*domain.DeviceJoinRequest
	for rows.Next() {
		var r domain.DeviceJoinRequest
		var rawHex sql.NullString
		var assignedID sql.NullInt64
		var snr sql.NullFloat64

		if err := rows.Scan(
			&r.ID,
			&r.DeviceMAC,
			&r.GatewayID,
			&r.RSSI,
			&snr,
			&rawHex,
			&r.Status,
			&assignedID,
			&r.CreatedAt,
			&r.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan join request row: %w", err)
		}

		if snr.Valid {
			r.SNR = snr.Float64
		}
		if rawHex.Valid {
			r.RawFrameHex = rawHex.String
		}
		if assignedID.Valid {
			val := int(assignedID.Int64)
			r.AssignedNodeID = &val
		}
		r.CreatedAt = r.CreatedAt.UTC()
		r.UpdatedAt = r.UpdatedAt.UTC()
		list = append(list, &r)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error reading join requests: %w", err)
	}
	if list == nil {
		list = make([]*domain.DeviceJoinRequest, 0)
	}
	return list, nil
}

// ApproveRequest approves a join request, assigns an available node_id, and registers the node in node_health and devices.
func (s *PostgresJoinRequestStorage) ApproveRequest(ctx context.Context, id int64, requestedNodeID *int) (*domain.DeviceJoinRequest, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("begin transaction: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	const selReq = `
		SELECT id, device_mac, gateway_id, status
		FROM device_join_requests
		WHERE id = $1
		FOR UPDATE;
	`
	var r domain.DeviceJoinRequest
	if err := tx.QueryRowContext(ctx, selReq, id).Scan(&r.ID, &r.DeviceMAC, &r.GatewayID, &r.Status); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrRequestNotFound
		}
		return nil, fmt.Errorf("query join request: %w", err)
	}

	// Determine node_id
	nodeID := 0
	if requestedNodeID != nil && *requestedNodeID > 0 && *requestedNodeID <= 254 {
		nodeID = *requestedNodeID
	} else {
		// Find smallest available node_id not yet assigned in node_health for this gateway
		const findSlot = `
			SELECT s.id
			FROM generate_series(1, 254) AS s(id)
			WHERE s.id NOT IN (
				SELECT node_id FROM node_health WHERE gateway_id = $1
			)
			ORDER BY s.id ASC
			LIMIT 1;
		`
		if err := tx.QueryRowContext(ctx, findSlot, r.GatewayID).Scan(&nodeID); err != nil {
			return nil, ErrNoAvailableNodeID
		}
	}

	// Update join request
	const updateReq = `
		UPDATE device_join_requests
		SET status = 'APPROVED', assigned_node_id = $1, updated_at = CURRENT_TIMESTAMP
		WHERE id = $2
		RETURNING updated_at;
	`
	var updatedAt time.Time
	if err := tx.QueryRowContext(ctx, updateReq, nodeID, id).Scan(&updatedAt); err != nil {
		return nil, fmt.Errorf("update request status: %w", err)
	}

	// Upsert into node_health
	const upsertHealth = `
		INSERT INTO node_health (
			gateway_id, node_id, session_sel, frame_counter, maint_seq, status_flags,
			pending_event_count, health_status, updated_at
		) VALUES ($1, $2, 0, 0, 0, 0, 0, 'ONLINE', CURRENT_TIMESTAMP)
		ON CONFLICT (gateway_id, node_id) DO UPDATE SET
			health_status = 'ONLINE',
			updated_at = CURRENT_TIMESTAMP;
	`
	if _, err := tx.ExecContext(ctx, upsertHealth, r.GatewayID, nodeID); err != nil {
		return nil, fmt.Errorf("upsert node_health: %w", err)
	}

	// Ensure device is active in devices table
	cleanMAC := strings.TrimSpace(r.DeviceMAC)
	macBytes, _ := hex.DecodeString(cleanMAC)
	if len(macBytes) == 6 {
		const upsertDev = `
			INSERT INTO devices (network_id, device_mac, status, updated_at)
			VALUES (1, $1, 'ACTIVE', CURRENT_TIMESTAMP)
			ON CONFLICT (network_id, device_mac) DO UPDATE SET
				status = 'ACTIVE',
				updated_at = CURRENT_TIMESTAMP;
		`
		_, _ = tx.ExecContext(ctx, upsertDev, macBytes)
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit approval: %w", err)
	}

	r.Status = "APPROVED"
	r.AssignedNodeID = &nodeID
	r.UpdatedAt = updatedAt.UTC()
	return &r, nil
}

// RejectRequest marks a request as REJECTED.
func (s *PostgresJoinRequestStorage) RejectRequest(ctx context.Context, id int64) error {
	const query = `
		UPDATE device_join_requests
		SET status = 'REJECTED', updated_at = CURRENT_TIMESTAMP
		WHERE id = $1;
	`
	res, err := s.db.ExecContext(ctx, query, id)
	if err != nil {
		return fmt.Errorf("reject request: %w", err)
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return ErrRequestNotFound
	}
	return nil
}
