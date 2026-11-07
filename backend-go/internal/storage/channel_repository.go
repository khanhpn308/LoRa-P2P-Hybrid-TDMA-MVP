package storage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

// ChannelRepository defines persistent storage operations for RF channels and Gateway allocations.
type ChannelRepository interface {
	GetChannel(ctx context.Context, channelID string) (*domain.RFChannel, error)
	ListChannels(ctx context.Context, planVersion string) ([]domain.ChannelView, error)
	GetActiveAllocationByGateway(ctx context.Context, gatewayID string) (*domain.ChannelAllocation, error)
	GetActiveAllocationByChannel(ctx context.Context, channelID string) (*domain.ChannelAllocation, error)
	AllocateChannel(ctx context.Context, req domain.AllocateRequest) (*domain.ChannelAllocation, error)
	ReleaseChannel(ctx context.Context, req domain.ReleaseRequest) (*domain.ChannelAllocation, error)
	ListActiveAllocations(ctx context.Context) ([]domain.ChannelAllocation, error)
}

// PostgresChannelRepository implements ChannelRepository backed by PostgreSQL.
type PostgresChannelRepository struct {
	db *sql.DB
}

// NewPostgresChannelRepository creates a new PostgresChannelRepository.
func NewPostgresChannelRepository(db *sql.DB) *PostgresChannelRepository {
	return &PostgresChannelRepository{db: db}
}

// GetChannel retrieves a single RF channel from the catalogue.
func (r *PostgresChannelRepository) GetChannel(ctx context.Context, channelID string) (*domain.RFChannel, error) {
	if err := domain.ValidateChannelID(channelID); err != nil {
		return nil, err
	}

	query := `
		SELECT channel_id, channel_plan_version, center_frequency_hz, bandwidth_hz,
		       is_enabled, created_at, updated_at
		FROM rf_channels
		WHERE channel_id = $1
	`
	var ch domain.RFChannel
	err := r.db.QueryRowContext(ctx, query, channelID).Scan(
		&ch.ChannelID,
		&ch.ChannelPlanVersion,
		&ch.CenterFrequencyHz,
		&ch.BandwidthHz,
		&ch.IsEnabled,
		&ch.CreatedAt,
		&ch.UpdatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, domain.ErrChannelNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("query channel %s: %w", channelID, err)
	}
	return &ch, nil
}

// ListChannels returns all channels for a given plan version with dynamically derived status.
func (r *PostgresChannelRepository) ListChannels(ctx context.Context, planVersion string) ([]domain.ChannelView, error) {
	if planVersion == "" {
		planVersion = domain.ChannelPlanVN920V1
	}
	if err := domain.ValidateChannelPlanVersion(planVersion); err != nil {
		return nil, err
	}

	query := `
		SELECT c.channel_id, c.channel_plan_version, c.center_frequency_hz, c.bandwidth_hz, c.is_enabled,
		       CASE
		           WHEN a.id IS NOT NULL THEN 'ALLOCATED'
		           WHEN NOT c.is_enabled THEN 'DISABLED'
		           ELSE 'AVAILABLE'
		       END AS state
		FROM rf_channels c
		LEFT JOIN gateway_channel_allocations a
		       ON c.channel_id = a.channel_id AND a.status = 'ALLOCATED'
		WHERE c.channel_plan_version = $1
		ORDER BY c.channel_id ASC
	`
	rows, err := r.db.QueryContext(ctx, query, planVersion)
	if err != nil {
		return nil, fmt.Errorf("list channels for plan %s: %w", planVersion, err)
	}
	defer rows.Close()

	var channels []domain.ChannelView
	for rows.Next() {
		var view domain.ChannelView
		if err := rows.Scan(
			&view.ChannelID,
			&view.ChannelPlanVersion,
			&view.CenterFrequencyHz,
			&view.BandwidthHz,
			&view.IsEnabled,
			&view.State,
		); err != nil {
			return nil, fmt.Errorf("scan channel row: %w", err)
		}
		channels = append(channels, view)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("channels iteration error: %w", err)
	}
	return channels, nil
}

// GetActiveAllocationByGateway returns the currently active allocation held by a Gateway, if any.
func (r *PostgresChannelRepository) GetActiveAllocationByGateway(ctx context.Context, gatewayID string) (*domain.ChannelAllocation, error) {
	if err := domain.ValidateGatewayID(gatewayID); err != nil {
		return nil, err
	}

	query := `
		SELECT id, gateway_id, channel_id, status, request_id, allocation_generation,
		       granted_by, released_by, release_reason, created_at, updated_at, released_at
		FROM gateway_channel_allocations
		WHERE gateway_id = $1 AND status = 'ALLOCATED'
	`
	var alloc domain.ChannelAllocation
	var releasedBy, releaseReason sql.NullString
	var releasedAt sql.NullTime

	err := r.db.QueryRowContext(ctx, query, gatewayID).Scan(
		&alloc.ID,
		&alloc.GatewayID,
		&alloc.ChannelID,
		&alloc.Status,
		&alloc.RequestID,
		&alloc.AllocationGeneration,
		&alloc.GrantedBy,
		&releasedBy,
		&releaseReason,
		&alloc.CreatedAt,
		&alloc.UpdatedAt,
		&releasedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, domain.ErrAllocationNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("query active allocation for gateway %s: %w", gatewayID, err)
	}

	if releasedBy.Valid {
		alloc.ReleasedBy = releasedBy.String
	}
	if releaseReason.Valid {
		alloc.ReleaseReason = releaseReason.String
	}
	if releasedAt.Valid {
		alloc.ReleasedAt = &releasedAt.Time
	}
	return &alloc, nil
}

// GetActiveAllocationByChannel returns the active allocation for a given RF channel, if any.
func (r *PostgresChannelRepository) GetActiveAllocationByChannel(ctx context.Context, channelID string) (*domain.ChannelAllocation, error) {
	if err := domain.ValidateChannelID(channelID); err != nil {
		return nil, err
	}

	query := `
		SELECT id, gateway_id, channel_id, status, request_id, allocation_generation,
		       granted_by, released_by, release_reason, created_at, updated_at, released_at
		FROM gateway_channel_allocations
		WHERE channel_id = $1 AND status = 'ALLOCATED'
	`
	var alloc domain.ChannelAllocation
	var releasedBy, releaseReason sql.NullString
	var releasedAt sql.NullTime

	err := r.db.QueryRowContext(ctx, query, channelID).Scan(
		&alloc.ID,
		&alloc.GatewayID,
		&alloc.ChannelID,
		&alloc.Status,
		&alloc.RequestID,
		&alloc.AllocationGeneration,
		&alloc.GrantedBy,
		&releasedBy,
		&releaseReason,
		&alloc.CreatedAt,
		&alloc.UpdatedAt,
		&releasedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, domain.ErrAllocationNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("query active allocation for channel %s: %w", channelID, err)
	}

	if releasedBy.Valid {
		alloc.ReleasedBy = releasedBy.String
	}
	if releaseReason.Valid {
		alloc.ReleaseReason = releaseReason.String
	}
	if releasedAt.Valid {
		alloc.ReleasedAt = &releasedAt.Time
	}
	return &alloc, nil
}

// AllocateChannel atomically assigns an exclusive channel to an authenticated Gateway.
func (r *PostgresChannelRepository) AllocateChannel(ctx context.Context, req domain.AllocateRequest) (*domain.ChannelAllocation, error) {
	if err := domain.ValidateGatewayID(req.GatewayID); err != nil {
		return nil, err
	}
	if err := domain.ValidateChannelID(req.ChannelID); err != nil {
		return nil, err
	}
	if err := domain.ValidateChannelPlanVersion(req.ChannelPlanVersion); err != nil {
		return nil, err
	}
	if err := domain.ValidateRequestID(req.RequestID); err != nil {
		return nil, err
	}

	tx, err := r.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return nil, fmt.Errorf("begin allocation tx: %w", err)
	}
	defer func() {
		if tx != nil {
			_ = tx.Rollback()
		}
	}()

	// 1. Idempotency check: same gateway_id and request_id
	var existingAlloc domain.ChannelAllocation
	var releasedBy, releaseReason sql.NullString
	var releasedAt sql.NullTime

	idempQuery := `
		SELECT id, gateway_id, channel_id, status, request_id, allocation_generation,
		       granted_by, released_by, release_reason, created_at, updated_at, released_at
		FROM gateway_channel_allocations
		WHERE gateway_id = $1 AND request_id = $2
		ORDER BY id DESC LIMIT 1
	`
	err = tx.QueryRowContext(ctx, idempQuery, req.GatewayID, req.RequestID).Scan(
		&existingAlloc.ID,
		&existingAlloc.GatewayID,
		&existingAlloc.ChannelID,
		&existingAlloc.Status,
		&existingAlloc.RequestID,
		&existingAlloc.AllocationGeneration,
		&existingAlloc.GrantedBy,
		&releasedBy,
		&releaseReason,
		&existingAlloc.CreatedAt,
		&existingAlloc.UpdatedAt,
		&releasedAt,
	)
	if err == nil {
		if releasedBy.Valid {
			existingAlloc.ReleasedBy = releasedBy.String
		}
		if releaseReason.Valid {
			existingAlloc.ReleaseReason = releaseReason.String
		}
		if releasedAt.Valid {
			existingAlloc.ReleasedAt = &releasedAt.Time
		}

		if existingAlloc.Status == domain.StatusAllocated {
			if existingAlloc.ChannelID == req.ChannelID {
				// Idempotent replay: return existing allocation
				_ = tx.Commit()
				tx = nil
				return &existingAlloc, nil
			}
			// Same request_id, but requesting a different channel
			return nil, domain.ErrGatewayAlreadyAllocated
		}
	} else if !errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("idempotency check: %w", err)
	}

	// 2. Check if Gateway already holds ANY active allocation
	var activeChan string
	checkGwQuery := `
		SELECT channel_id FROM gateway_channel_allocations
		WHERE gateway_id = $1 AND status = 'ALLOCATED'
		FOR UPDATE
	`
	err = tx.QueryRowContext(ctx, checkGwQuery, req.GatewayID).Scan(&activeChan)
	if err == nil {
		if activeChan == req.ChannelID {
			// Gateway already has this channel active
			return nil, fmt.Errorf("%w: gateway already holds channel %s", domain.ErrGatewayAlreadyAllocated, activeChan)
		}
		return nil, fmt.Errorf("%w: gateway already holds channel %s", domain.ErrGatewayAlreadyAllocated, activeChan)
	} else if !errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("check gateway allocation: %w", err)
	}

	// 3. Verify channel exists and is enabled in rf_channels catalogue
	var planVersion string
	var isEnabled bool
	checkChanQuery := `
		SELECT channel_plan_version, is_enabled
		FROM rf_channels
		WHERE channel_id = $1
		FOR UPDATE
	`
	err = tx.QueryRowContext(ctx, checkChanQuery, req.ChannelID).Scan(&planVersion, &isEnabled)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, domain.ErrChannelNotFound
	} else if err != nil {
		return nil, fmt.Errorf("check channel catalogue: %w", err)
	}
	if !isEnabled {
		return nil, domain.ErrChannelDisabled
	}
	if planVersion != req.ChannelPlanVersion {
		return nil, domain.ErrInvalidChannelPlan
	}

	// 4. Check if channel is already allocated to another gateway
	var currentHolder string
	checkAllocQuery := `
		SELECT gateway_id FROM gateway_channel_allocations
		WHERE channel_id = $1 AND status = 'ALLOCATED'
		FOR UPDATE
	`
	err = tx.QueryRowContext(ctx, checkAllocQuery, req.ChannelID).Scan(&currentHolder)
	if err == nil {
		return nil, domain.ErrChannelInUse
	} else if !errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("check channel availability: %w", err)
	}

	// 5. Calculate next monotonic generation for this channel
	var nextGen int64
	genQuery := `
		SELECT COALESCE(MAX(allocation_generation), 0) + 1
		FROM gateway_channel_allocations
		WHERE channel_id = $1
	`
	err = tx.QueryRowContext(ctx, genQuery, req.ChannelID).Scan(&nextGen)
	if err != nil {
		return nil, fmt.Errorf("calculate channel generation: %w", err)
	}

	// 6. Insert new allocation
	now := time.Now().UTC()
	grantedBy := req.GrantedBy
	if strings.TrimSpace(grantedBy) == "" {
		grantedBy = "system"
	}

	var newAlloc domain.ChannelAllocation
	insertQuery := `
		INSERT INTO gateway_channel_allocations (
			gateway_id, channel_id, status, request_id,
			allocation_generation, granted_by, created_at, updated_at
		) VALUES ($1, $2, 'ALLOCATED', $3, $4, $5, $6, $6)
		RETURNING id, gateway_id, channel_id, status, request_id, allocation_generation,
		          granted_by, created_at, updated_at
	`
	err = tx.QueryRowContext(ctx, insertQuery,
		req.GatewayID,
		req.ChannelID,
		req.RequestID,
		nextGen,
		grantedBy,
		now,
	).Scan(
		&newAlloc.ID,
		&newAlloc.GatewayID,
		&newAlloc.ChannelID,
		&newAlloc.Status,
		&newAlloc.RequestID,
		&newAlloc.AllocationGeneration,
		&newAlloc.GrantedBy,
		&newAlloc.CreatedAt,
		&newAlloc.UpdatedAt,
	)
	if err != nil {
		errStr := err.Error()
		if strings.Contains(errStr, "idx_exclusive_active_channel") {
			return nil, domain.ErrChannelInUse
		}
		if strings.Contains(errStr, "idx_exclusive_active_gateway") {
			return nil, domain.ErrGatewayAlreadyAllocated
		}
		return nil, fmt.Errorf("insert allocation: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit allocation tx: %w", err)
	}
	tx = nil
	return &newAlloc, nil
}

// ReleaseChannel explicitly releases an active channel allocation.
func (r *PostgresChannelRepository) ReleaseChannel(ctx context.Context, req domain.ReleaseRequest) (*domain.ChannelAllocation, error) {
	if err := domain.ValidateGatewayID(req.GatewayID); err != nil {
		return nil, err
	}
	if err := domain.ValidateChannelID(req.ChannelID); err != nil {
		return nil, err
	}
	if err := domain.ValidateRequestID(req.RequestID); err != nil {
		return nil, err
	}

	tx, err := r.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return nil, fmt.Errorf("begin release tx: %w", err)
	}
	defer func() {
		if tx != nil {
			_ = tx.Rollback()
		}
	}()

	var allocID int64
	findQuery := `
		SELECT id FROM gateway_channel_allocations
		WHERE gateway_id = $1 AND channel_id = $2 AND status = 'ALLOCATED'
		FOR UPDATE
	`
	err = tx.QueryRowContext(ctx, findQuery, req.GatewayID, req.ChannelID).Scan(&allocID)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, domain.ErrAllocationNotFound
	} else if err != nil {
		return nil, fmt.Errorf("find allocation to release: %w", err)
	}

	now := time.Now().UTC()
	releasedBy := req.ReleasedBy
	if strings.TrimSpace(releasedBy) == "" {
		releasedBy = "system"
	}

	var updatedAlloc domain.ChannelAllocation
	var rb, rr sql.NullString
	var ra sql.NullTime

	updateQuery := `
		UPDATE gateway_channel_allocations
		SET status = 'RELEASED',
		    released_by = $1,
		    release_reason = $2,
		    released_at = $3,
		    updated_at = $3
		WHERE id = $4
		RETURNING id, gateway_id, channel_id, status, request_id, allocation_generation,
		          granted_by, released_by, release_reason, created_at, updated_at, released_at
	`
	err = tx.QueryRowContext(ctx, updateQuery, releasedBy, req.ReleaseReason, now, allocID).Scan(
		&updatedAlloc.ID,
		&updatedAlloc.GatewayID,
		&updatedAlloc.ChannelID,
		&updatedAlloc.Status,
		&updatedAlloc.RequestID,
		&updatedAlloc.AllocationGeneration,
		&updatedAlloc.GrantedBy,
		&rb,
		&rr,
		&updatedAlloc.CreatedAt,
		&updatedAlloc.UpdatedAt,
		&ra,
	)
	if err != nil {
		return nil, fmt.Errorf("update allocation: %w", err)
	}

	if rb.Valid {
		updatedAlloc.ReleasedBy = rb.String
	}
	if rr.Valid {
		updatedAlloc.ReleaseReason = rr.String
	}
	if ra.Valid {
		updatedAlloc.ReleasedAt = &ra.Time
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("commit release tx: %w", err)
	}
	tx = nil
	return &updatedAlloc, nil
}

// ListActiveAllocations returns all currently active channel allocations across the network.
func (r *PostgresChannelRepository) ListActiveAllocations(ctx context.Context) ([]domain.ChannelAllocation, error) {
	query := `
		SELECT id, gateway_id, channel_id, status, request_id, allocation_generation,
		       granted_by, released_by, release_reason, created_at, updated_at, released_at
		FROM gateway_channel_allocations
		WHERE status = 'ALLOCATED'
		ORDER BY channel_id ASC
	`
	rows, err := r.db.QueryContext(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query active allocations: %w", err)
	}
	defer rows.Close()

	var allocations []domain.ChannelAllocation
	for rows.Next() {
		var alloc domain.ChannelAllocation
		var releasedBy, releaseReason sql.NullString
		var releasedAt sql.NullTime

		if err := rows.Scan(
			&alloc.ID,
			&alloc.GatewayID,
			&alloc.ChannelID,
			&alloc.Status,
			&alloc.RequestID,
			&alloc.AllocationGeneration,
			&alloc.GrantedBy,
			&releasedBy,
			&releaseReason,
			&alloc.CreatedAt,
			&alloc.UpdatedAt,
			&releasedAt,
		); err != nil {
			return nil, fmt.Errorf("scan active allocation: %w", err)
		}

		if releasedBy.Valid {
			alloc.ReleasedBy = releasedBy.String
		}
		if releaseReason.Valid {
			alloc.ReleaseReason = releaseReason.String
		}
		if releasedAt.Valid {
			alloc.ReleasedAt = &releasedAt.Time
		}
		allocations = append(allocations, alloc)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate active allocations: %w", err)
	}
	return allocations, nil
}
