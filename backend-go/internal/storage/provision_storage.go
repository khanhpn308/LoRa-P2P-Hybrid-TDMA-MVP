package storage

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"
)

var (
	// ErrDeviceAlreadyProvisioned indicates an active generation already exists for the device.
	ErrDeviceAlreadyProvisioned = errors.New("device already provisioned with active generation")
	// ErrGenerationAlreadyExists indicates the specified generation counter already exists for the device.
	ErrGenerationAlreadyExists = errors.New("device generation already exists")
	// ErrInvalidProvisionInput indicates bad parameters for provisioning.
	ErrInvalidProvisionInput = errors.New("invalid provision input parameter")
)

// ProvisionDeviceInput contains verified parameters for device provisioning.
type ProvisionDeviceInput struct {
	NetworkID          uint32
	DeviceMAC          [6]byte
	Generation         uint16
	KJoinWrapped       []byte
	InitialJoinCounter uint32
}

// ProvisionDeviceResult contains persisted metadata for a provisioned device.
type ProvisionDeviceResult struct {
	NetworkID  uint32
	DeviceMAC  [6]byte
	Generation uint16
	Status     string
	CreatedAt  time.Time
}

// ProvisionRepository defines the database interface for device registration and K_JOIN provisioning.
type ProvisionRepository interface {
	ProvisionDevice(ctx context.Context, input *ProvisionDeviceInput) (*ProvisionDeviceResult, error)
}

// PostgresProvisionStorage implements ProvisionRepository against PostgreSQL with transactional guarantees.
type PostgresProvisionStorage struct {
	db *sql.DB
}

// NewPostgresProvisionStorage constructs a new PostgresProvisionStorage.
func NewPostgresProvisionStorage(db *sql.DB) *PostgresProvisionStorage {
	return &PostgresProvisionStorage{db: db}
}

// ProvisionDevice commits device registration, active generation with wrapped key, and initial join counter atomically.
func (s *PostgresProvisionStorage) ProvisionDevice(ctx context.Context, input *ProvisionDeviceInput) (*ProvisionDeviceResult, error) {
	if input == nil {
		return nil, fmt.Errorf("%w: input cannot be nil", ErrInvalidProvisionInput)
	}
	if input.NetworkID == 0 {
		return nil, fmt.Errorf("%w: network_id must be positive", ErrInvalidProvisionInput)
	}
	if input.Generation == 0 {
		input.Generation = 1
	}
	if len(input.KJoinWrapped) < 32 {
		return nil, fmt.Errorf("%w: k_join_wrapped must be at least 32 bytes, got %d", ErrInvalidProvisionInput, len(input.KJoinWrapped))
	}

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return nil, fmt.Errorf("failed to begin provision transaction: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	// 1. Insert device record if not existing
	const insertDeviceQuery = `
		INSERT INTO devices (network_id, device_mac, status)
		VALUES ($1, $2, 'ACTIVE')
		ON CONFLICT (network_id, device_mac) DO NOTHING;
	`
	if _, err := tx.ExecContext(ctx, insertDeviceQuery, int64(input.NetworkID), input.DeviceMAC[:]); err != nil {
		return nil, fmt.Errorf("failed to insert device record: %w", err)
	}

	// 2. Lock device row and verify active status
	const lockDeviceQuery = `
		SELECT status FROM devices
		WHERE network_id = $1 AND device_mac = $2
		FOR UPDATE;
	`
	var devStatus string
	if err := tx.QueryRowContext(ctx, lockDeviceQuery, int64(input.NetworkID), input.DeviceMAC[:]).Scan(&devStatus); err != nil {
		return nil, fmt.Errorf("failed to lock device row: %w", err)
	}
	if devStatus != "ACTIVE" {
		return nil, fmt.Errorf("%w: status=%s", ErrDeviceNotActive, devStatus)
	}

	// 3. Verify no active generation already exists (prevent duplicate active generation conflict)
	const checkActiveGenQuery = `
		SELECT generation FROM device_generations
		WHERE network_id = $1 AND device_mac = $2 AND is_active = TRUE
		FOR UPDATE;
	`
	var activeGen int
	err = tx.QueryRowContext(ctx, checkActiveGenQuery, int64(input.NetworkID), input.DeviceMAC[:]).Scan(&activeGen)
	if err == nil {
		return nil, fmt.Errorf("%w: device already has active generation %d", ErrDeviceAlreadyProvisioned, activeGen)
	} else if !errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("failed to check existing active generation: %w", err)
	}

	// 4. Verify the specific generation number does not already exist
	const checkGenQuery = `
		SELECT 1 FROM device_generations
		WHERE network_id = $1 AND device_mac = $2 AND generation = $3;
	`
	var dummy int
	err = tx.QueryRowContext(ctx, checkGenQuery, int64(input.NetworkID), input.DeviceMAC[:], int(input.Generation)).Scan(&dummy)
	if err == nil {
		return nil, fmt.Errorf("%w: generation %d already exists", ErrGenerationAlreadyExists, input.Generation)
	} else if !errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("failed to check specific generation: %w", err)
	}

	// 5. Insert into device_generations
	const insertGenQuery = `
		INSERT INTO device_generations (network_id, device_mac, generation, k_join_wrapped, is_active)
		VALUES ($1, $2, $3, $4, TRUE)
		RETURNING created_at;
	`
	var createdAt time.Time
	if err := tx.QueryRowContext(ctx, insertGenQuery, int64(input.NetworkID), input.DeviceMAC[:], int(input.Generation), input.KJoinWrapped).Scan(&createdAt); err != nil {
		return nil, fmt.Errorf("failed to insert device generation: %w", err)
	}

	// 6. Insert into device_join_counters initialized to initial join counter
	const insertCounterQuery = `
		INSERT INTO device_join_counters (network_id, device_mac, generation, last_join_counter)
		VALUES ($1, $2, $3, $4);
	`
	if _, err := tx.ExecContext(ctx, insertCounterQuery, int64(input.NetworkID), input.DeviceMAC[:], int(input.Generation), int64(input.InitialJoinCounter)); err != nil {
		return nil, fmt.Errorf("failed to insert initial join counter: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return nil, fmt.Errorf("failed to commit provision transaction: %w", err)
	}

	return &ProvisionDeviceResult{
		NetworkID:  input.NetworkID,
		DeviceMAC:  input.DeviceMAC,
		Generation: input.Generation,
		Status:     "ACTIVE",
		CreatedAt:  createdAt.UTC(),
	}, nil
}
