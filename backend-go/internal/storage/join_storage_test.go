package storage_test

import (
	"context"
	"errors"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

func TestGetActiveDevice_Success(t *testing.T) {
	db := initMockDB("join_active")
	repo := storage.NewPostgresJoinStorage(db)

	mac := [6]byte{0x01, 0x02, 0x03, 0x04, 0x05, 0x06}
	record, err := repo.GetActiveDevice(context.Background(), 100, mac)
	if err != nil {
		t.Fatalf("expected successful query, got: %v", err)
	}

	if record.Status != "ACTIVE" || record.ActiveGeneration != 1 {
		t.Fatalf("unexpected record values: %+v", record)
	}
	if record.NetworkID != 100 || record.DeviceMAC != mac {
		t.Fatalf("device identity mismatch: %+v", record)
	}
}

func TestGetActiveDevice_NotFound(t *testing.T) {
	db := initMockDB("join_device_not_found")
	repo := storage.NewPostgresJoinStorage(db)

	_, err := repo.GetActiveDevice(context.Background(), 100, [6]byte{1, 2, 3, 4, 5, 6})
	if !errors.Is(err, storage.ErrDeviceNotFound) {
		t.Fatalf("expected ErrDeviceNotFound, got: %v", err)
	}
}

func TestGetActiveDevice_NotActive(t *testing.T) {
	db := initMockDB("join_device_revoked")
	repo := storage.NewPostgresJoinStorage(db)

	_, err := repo.GetActiveDevice(context.Background(), 100, [6]byte{1, 2, 3, 4, 5, 6})
	if !errors.Is(err, storage.ErrDeviceNotActive) {
		t.Fatalf("expected ErrDeviceNotActive, got: %v", err)
	}
}

func TestRecordJoinHello_FirstCounter(t *testing.T) {
	db := initMockDB("join_first_counter")
	repo := storage.NewPostgresJoinStorage(db)

	input := &storage.JoinHelloTxInput{
		NetworkID:      1,
		DeviceMAC:      [6]byte{0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF},
		Generation:     1,
		TargetGWID:     2,
		JoinCounter:    10,
		RawHelloSHA256: [32]byte{1, 2, 3},
		NodeNonce:      [8]byte{4, 5, 6},
		NodeX25519Pub:  [32]byte{7, 8, 9},
	}

	result, err := repo.RecordJoinHello(context.Background(), input)
	if err != nil {
		t.Fatalf("expected successful insert, got: %v", err)
	}

	if result.IsIdempotentReplay {
		t.Fatal("expected IsIdempotentReplay to be false for new counter")
	}
	if result.TransactionID != 99 || result.JoinCounter != 10 {
		t.Fatalf("unexpected result: %+v", result)
	}
	if result.Status != storage.StatusHelloAuthenticatedPendingGrant {
		t.Fatalf("expected status %s, got %s", storage.StatusHelloAuthenticatedPendingGrant, result.Status)
	}
}

func TestRecordJoinHello_AdvancingCounter(t *testing.T) {
	db := initMockDB("join_advancing_counter")
	repo := storage.NewPostgresJoinStorage(db)

	input := &storage.JoinHelloTxInput{
		NetworkID:      1,
		DeviceMAC:      [6]byte{0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF},
		Generation:     1,
		TargetGWID:     2,
		JoinCounter:    15, // 15 > 10
		RawHelloSHA256: [32]byte{1, 2, 3},
		NodeNonce:      [8]byte{4, 5, 6},
		NodeX25519Pub:  [32]byte{7, 8, 9},
	}

	result, err := repo.RecordJoinHello(context.Background(), input)
	if err != nil {
		t.Fatalf("expected successful advancement, got: %v", err)
	}
	if result.IsIdempotentReplay {
		t.Fatal("expected IsIdempotentReplay to be false for advancing counter")
	}
	if result.TransactionID != 99 || result.JoinCounter != 15 {
		t.Fatalf("unexpected result: %+v", result)
	}
}

func TestRecordJoinHello_IdempotentRetry(t *testing.T) {
	db := initMockDB("join_idempotent_retry")
	repo := storage.NewPostgresJoinStorage(db)

	identicalHash := [32]byte{}
	copy(identicalHash[:], []byte("hello-hash-32-bytes-identical!!!"))

	input := &storage.JoinHelloTxInput{
		NetworkID:      1,
		DeviceMAC:      [6]byte{0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF},
		Generation:     1,
		TargetGWID:     2,
		JoinCounter:    20, // 20 <= 20
		RawHelloSHA256: identicalHash,
	}

	result, err := repo.RecordJoinHello(context.Background(), input)
	if err != nil {
		t.Fatalf("expected successful idempotent result, got: %v", err)
	}
	if !result.IsIdempotentReplay {
		t.Fatal("expected IsIdempotentReplay to be true for identical retry")
	}
	if result.TransactionID != 88 || result.JoinCounter != 20 {
		t.Fatalf("unexpected result: %+v", result)
	}
}

func TestRecordJoinHello_ReplayDetected_DifferentPayload(t *testing.T) {
	db := initMockDB("join_replay_conflict")
	repo := storage.NewPostgresJoinStorage(db)

	attackerHash := [32]byte{0x99, 0x88, 0x77, 0x66}

	input := &storage.JoinHelloTxInput{
		NetworkID:      1,
		DeviceMAC:      [6]byte{0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF},
		Generation:     1,
		TargetGWID:     2,
		JoinCounter:    20, // 20 <= 20, different payload!
		RawHelloSHA256: attackerHash,
	}

	_, err := repo.RecordJoinHello(context.Background(), input)
	if !errors.Is(err, storage.ErrReplayDetected) {
		t.Fatalf("expected ErrReplayDetected, got: %v", err)
	}
}

func TestRecordJoinHello_StaleCounter(t *testing.T) {
	db := initMockDB("join_stale_counter")
	repo := storage.NewPostgresJoinStorage(db)

	input := &storage.JoinHelloTxInput{
		NetworkID:      1,
		DeviceMAC:      [6]byte{0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF},
		Generation:     1,
		TargetGWID:     2,
		JoinCounter:    20, // 20 < 50 without transaction
		RawHelloSHA256: [32]byte{1},
	}

	_, err := repo.RecordJoinHello(context.Background(), input)
	if !errors.Is(err, storage.ErrStaleJoinCounter) {
		t.Fatalf("expected ErrStaleJoinCounter, got: %v", err)
	}
}

func TestRecordJoinHello_DeviceRevokedDuringLock(t *testing.T) {
	db := initMockDB("join_device_revoked")
	repo := storage.NewPostgresJoinStorage(db)

	input := &storage.JoinHelloTxInput{
		NetworkID:   1,
		DeviceMAC:   [6]byte{0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF},
		Generation:  1,
		JoinCounter: 10,
	}

	_, err := repo.RecordJoinHello(context.Background(), input)
	if !errors.Is(err, storage.ErrDeviceNotActive) {
		t.Fatalf("expected ErrDeviceNotActive, got: %v", err)
	}
}

func TestRecordJoinHello_NilInput(t *testing.T) {
	db := initMockDB("default")
	repo := storage.NewPostgresJoinStorage(db)

	_, err := repo.RecordJoinHello(context.Background(), nil)
	if err == nil {
		t.Fatal("expected error for nil input, got nil")
	}
}
