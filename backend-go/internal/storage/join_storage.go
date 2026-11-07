package storage

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"fmt"
)

var (
	// ErrDeviceNotFound indicates no registered device matches the Network ID and MAC.
	ErrDeviceNotFound = errors.New("device not registered")
	// ErrDeviceNotActive indicates the device is suspended or revoked.
	ErrDeviceNotActive = errors.New("device is not active")
	// ErrGenerationNotFound indicates no active generation was found for the device.
	ErrGenerationNotFound = errors.New("device generation not found or inactive")
	// ErrStaleJoinCounter indicates the counter is lower than the high-water counter without matching transaction.
	ErrStaleJoinCounter = errors.New("join counter is stale or has rolled back")
	// ErrReplayDetected indicates a different payload was presented with an existing or past counter.
	ErrReplayDetected = errors.New("conflicting replay detected for join counter")
)

const (
	// StatusHelloAuthenticatedPendingGrant is the canonical initial status for verified Hello transactions.
	StatusHelloAuthenticatedPendingGrant = "HELLO_AUTHENTICATED_PENDING_GRANT"
)

// DeviceRecord contains active provisioning metadata for a device.
// Secrets (K_JOIN) are kept only in memory during authorization and never logged or serialized.
type DeviceRecord struct {
	NetworkID        uint32
	DeviceMAC        [6]byte
	Status           string
	ActiveGeneration uint16
	KJoinWrapped     []byte
}

// JoinHelloTxInput contains the parameters for an authenticated Hello transaction.
type JoinHelloTxInput struct {
	NetworkID      uint32
	DeviceMAC      [6]byte
	Generation     uint16
	TargetGWID     uint8
	JoinCounter    uint32
	RawHelloSHA256 [32]byte
	NodeNonce      [8]byte
	NodeX25519Pub  [32]byte
}

// JoinHelloTxResult is the result of persisting a Hello transaction.
type JoinHelloTxResult struct {
	TransactionID      int64
	Status             string
	IsIdempotentReplay bool
	JoinCounter        uint32
}

// JoinRepository defines the storage interface for device lookups and join transaction idempotency.
type JoinRepository interface {
	GetActiveDevice(ctx context.Context, networkID uint32, mac [6]byte) (*DeviceRecord, error)
	RecordJoinHello(ctx context.Context, input *JoinHelloTxInput) (*JoinHelloTxResult, error)
}

// PostgresJoinStorage implements JoinRepository on PostgreSQL with row-level locks and strict anti-replay idempotency.
type PostgresJoinStorage struct {
	db *sql.DB
}

// NewPostgresJoinStorage constructs a new PostgresJoinStorage repository.
func NewPostgresJoinStorage(db *sql.DB) *PostgresJoinStorage {
	return &PostgresJoinStorage{db: db}
}

// GetActiveDevice looks up the device and its currently active generation.
func (s *PostgresJoinStorage) GetActiveDevice(ctx context.Context, networkID uint32, mac [6]byte) (*DeviceRecord, error) {
	const query = `
		SELECT d.status, g.generation, g.k_join_wrapped
		FROM devices d
		JOIN device_generations g
		  ON d.network_id = g.network_id AND d.device_mac = g.device_mac
		WHERE d.network_id = $1 AND d.device_mac = $2 AND g.is_active = TRUE;
	`

	var status string
	var gen int
	var kJoinWrapped []byte

	err := s.db.QueryRowContext(ctx, query, int64(networkID), mac[:]).Scan(&status, &gen, &kJoinWrapped)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrDeviceNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query active device: %w", err)
	}

	if status != "ACTIVE" {
		return nil, fmt.Errorf("%w: status=%s", ErrDeviceNotActive, status)
	}

	return &DeviceRecord{
		NetworkID:        networkID,
		DeviceMAC:        mac,
		Status:           status,
		ActiveGeneration: uint16(gen),
		KJoinWrapped:     kJoinWrapped,
	}, nil
}

// RecordJoinHello executes a PostgreSQL transaction with row-level locks to advance
// the monotonic JoinCounter or return an idempotent result for byte-identical retransmissions.
func (s *PostgresJoinStorage) RecordJoinHello(ctx context.Context, input *JoinHelloTxInput) (*JoinHelloTxResult, error) {
	if input == nil {
		return nil, errors.New("join input cannot be nil")
	}

	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return nil, fmt.Errorf("failed to begin join transaction: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	// 1. Lock device row and verify it is still ACTIVE
	const lockDeviceQuery = `
		SELECT status FROM devices
		WHERE network_id = $1 AND device_mac = $2
		FOR UPDATE;
	`
	var devStatus string
	err = tx.QueryRowContext(ctx, lockDeviceQuery, int64(input.NetworkID), input.DeviceMAC[:]).Scan(&devStatus)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrDeviceNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to lock device row: %w", err)
	}
	if devStatus != "ACTIVE" {
		return nil, fmt.Errorf("%w: status=%s", ErrDeviceNotActive, devStatus)
	}

	// 2. Lock generation row and verify is_active
	const lockGenQuery = `
		SELECT is_active FROM device_generations
		WHERE network_id = $1 AND device_mac = $2 AND generation = $3
		FOR UPDATE;
	`
	var isGenActive bool
	err = tx.QueryRowContext(ctx, lockGenQuery, int64(input.NetworkID), input.DeviceMAC[:], int(input.Generation)).Scan(&isGenActive)
	if errors.Is(err, sql.ErrNoRows) || !isGenActive {
		return nil, ErrGenerationNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("failed to lock generation row: %w", err)
	}

	// 3. Lock device_join_counters row for this (network_id, device_mac, generation)
	const lockCounterQuery = `
		SELECT last_join_counter FROM device_join_counters
		WHERE network_id = $1 AND device_mac = $2 AND generation = $3
		FOR UPDATE;
	`
	var lastCounter int64
	err = tx.QueryRowContext(ctx, lockCounterQuery, int64(input.NetworkID), input.DeviceMAC[:], int(input.Generation)).Scan(&lastCounter)

	incoming := int64(input.JoinCounter)

	if errors.Is(err, sql.ErrNoRows) {
		// First ever counter entry for this generation
		const insertCounterQuery = `
			INSERT INTO device_join_counters (network_id, device_mac, generation, last_join_counter)
			VALUES ($1, $2, $3, $4);
		`
		if _, err := tx.ExecContext(ctx, insertCounterQuery, int64(input.NetworkID), input.DeviceMAC[:], int(input.Generation), incoming); err != nil {
			return nil, fmt.Errorf("failed to insert initial join counter: %w", err)
		}

		txID, err := insertJoinTx(ctx, tx, input)
		if err != nil {
			return nil, err
		}

		if err := tx.Commit(); err != nil {
			return nil, fmt.Errorf("failed to commit join transaction: %w", err)
		}

		return &JoinHelloTxResult{
			TransactionID:      txID,
			Status:             StatusHelloAuthenticatedPendingGrant,
			IsIdempotentReplay: false,
			JoinCounter:        input.JoinCounter,
		}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to lock join counter: %w", err)
	}

	// 4. Counter evaluation: advancement vs idempotency vs replay
	if incoming > lastCounter {
		// Advance high-water counter
		const updateCounterQuery = `
			UPDATE device_join_counters
			SET last_join_counter = $1, updated_at = CURRENT_TIMESTAMP
			WHERE network_id = $2 AND device_mac = $3 AND generation = $4;
		`
		if _, err := tx.ExecContext(ctx, updateCounterQuery, incoming, int64(input.NetworkID), input.DeviceMAC[:], int(input.Generation)); err != nil {
			return nil, fmt.Errorf("failed to advance join counter: %w", err)
		}

		txID, err := insertJoinTx(ctx, tx, input)
		if err != nil {
			return nil, err
		}

		if err := tx.Commit(); err != nil {
			return nil, fmt.Errorf("failed to commit advanced join transaction: %w", err)
		}

		return &JoinHelloTxResult{
			TransactionID:      txID,
			Status:             StatusHelloAuthenticatedPendingGrant,
			IsIdempotentReplay: false,
			JoinCounter:        input.JoinCounter,
		}, nil
	}

	// incoming <= lastCounter: could be an idempotent retry of existing transaction or a replay attack
	const queryExistingTx = `
		SELECT id, status, raw_hello_sha256 FROM join_transactions
		WHERE network_id = $1 AND device_mac = $2 AND generation = $3 AND join_counter = $4;
	`
	var existingID int64
	var existingStatus string
	var existingSHA []byte

	err = tx.QueryRowContext(ctx, queryExistingTx, int64(input.NetworkID), input.DeviceMAC[:], int(input.Generation), incoming).Scan(&existingID, &existingStatus, &existingSHA)
	if errors.Is(err, sql.ErrNoRows) {
		// Counter is smaller than high-water mark, but no transaction recorded for it -> stale rollback
		return nil, ErrStaleJoinCounter
	}
	if err != nil {
		return nil, fmt.Errorf("failed to query existing transaction: %w", err)
	}

	// Compare raw_hello_sha256
	if !bytes.Equal(existingSHA, input.RawHelloSHA256[:]) {
		// Same counter presented with different payload -> replay attack detected
		return nil, ErrReplayDetected
	}

	// Byte-identical retry: return existing transaction idempotently
	return &JoinHelloTxResult{
		TransactionID:      existingID,
		Status:             existingStatus,
		IsIdempotentReplay: true,
		JoinCounter:        input.JoinCounter,
	}, nil
}

func insertJoinTx(ctx context.Context, tx *sql.Tx, input *JoinHelloTxInput) (int64, error) {
	const insertTxQuery = `
		INSERT INTO join_transactions (
			network_id, device_mac, generation, target_gw_id, join_counter,
			status, raw_hello_sha256, node_nonce, node_x25519_pub
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		RETURNING id;
	`
	var txID int64
	err := tx.QueryRowContext(ctx, insertTxQuery,
		int64(input.NetworkID),
		input.DeviceMAC[:],
		int(input.Generation),
		int(input.TargetGWID),
		int64(input.JoinCounter),
		StatusHelloAuthenticatedPendingGrant,
		input.RawHelloSHA256[:],
		input.NodeNonce[:],
		input.NodeX25519Pub[:],
	).Scan(&txID)

	if err != nil {
		return 0, fmt.Errorf("failed to insert join transaction: %w", err)
	}
	return txID, nil
}
