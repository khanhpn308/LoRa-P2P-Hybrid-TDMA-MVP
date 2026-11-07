package storage_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

func TestPostgresProvisionStorage_ProvisionDevice_Table(t *testing.T) {
	mac := [6]byte{0x00, 0x11, 0x22, 0x33, 0x44, 0x55}
	validWrappedKey := make([]byte, 60)
	for i := range validWrappedKey {
		validWrappedKey[i] = 0xAA
	}

	tests := []struct {
		name        string
		state       string
		input       *storage.ProvisionDeviceInput
		ctxTimeout  time.Duration
		cancelCtx   bool
		wantErr     bool
		expectedErr error
	}{
		{
			name:  "success initial provision",
			state: "default",
			input: &storage.ProvisionDeviceInput{
				NetworkID:          1,
				DeviceMAC:          mac,
				Generation:         1,
				KJoinWrapped:       validWrappedKey,
				InitialJoinCounter: 0,
			},
			wantErr: false,
		},
		{
			name:  "success default generation when zero",
			state: "default",
			input: &storage.ProvisionDeviceInput{
				NetworkID:          1,
				DeviceMAC:          mac,
				Generation:         0,
				KJoinWrapped:       validWrappedKey,
				InitialJoinCounter: 10,
			},
			wantErr: false,
		},
		{
			name:        "nil input returns ErrInvalidProvisionInput",
			state:       "default",
			input:       nil,
			wantErr:     true,
			expectedErr: storage.ErrInvalidProvisionInput,
		},
		{
			name:  "zero network_id returns ErrInvalidProvisionInput",
			state: "default",
			input: &storage.ProvisionDeviceInput{
				NetworkID:          0,
				DeviceMAC:          mac,
				Generation:         1,
				KJoinWrapped:       validWrappedKey,
				InitialJoinCounter: 0,
			},
			wantErr:     true,
			expectedErr: storage.ErrInvalidProvisionInput,
		},
		{
			name:  "short wrapped key returns ErrInvalidProvisionInput",
			state: "default",
			input: &storage.ProvisionDeviceInput{
				NetworkID:          1,
				DeviceMAC:          mac,
				Generation:         1,
				KJoinWrapped:       make([]byte, 16),
				InitialJoinCounter: 0,
			},
			wantErr:     true,
			expectedErr: storage.ErrInvalidProvisionInput,
		},
		{
			name:  "conflict active generation already exists",
			state: "provision_active_conflict",
			input: &storage.ProvisionDeviceInput{
				NetworkID:          1,
				DeviceMAC:          mac,
				Generation:         2,
				KJoinWrapped:       validWrappedKey,
				InitialJoinCounter: 0,
			},
			wantErr:     true,
			expectedErr: storage.ErrDeviceAlreadyProvisioned,
		},
		{
			name:  "conflict generation number already exists",
			state: "provision_gen_exists",
			input: &storage.ProvisionDeviceInput{
				NetworkID:          1,
				DeviceMAC:          mac,
				Generation:         1,
				KJoinWrapped:       validWrappedKey,
				InitialJoinCounter: 0,
			},
			wantErr:     true,
			expectedErr: storage.ErrGenerationAlreadyExists,
		},
		{
			name:  "device revoked returns ErrDeviceNotActive",
			state: "provision_device_revoked",
			input: &storage.ProvisionDeviceInput{
				NetworkID:          1,
				DeviceMAC:          mac,
				Generation:         1,
				KJoinWrapped:       validWrappedKey,
				InitialJoinCounter: 0,
			},
			wantErr:     true,
			expectedErr: storage.ErrDeviceNotActive,
		},
		{
			name:      "context cancellation propagates error",
			state:     "default",
			cancelCtx: true,
			input: &storage.ProvisionDeviceInput{
				NetworkID:          1,
				DeviceMAC:          mac,
				Generation:         1,
				KJoinWrapped:       validWrappedKey,
				InitialJoinCounter: 0,
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			db := initMockDB(tt.state)
			repo := storage.NewPostgresProvisionStorage(db)

			ctx := context.Background()
			if tt.cancelCtx {
				var cancel context.CancelFunc
				ctx, cancel = context.WithCancel(ctx)
				cancel()
			} else if tt.ctxTimeout > 0 {
				var cancel context.CancelFunc
				ctx, cancel = context.WithTimeout(ctx, tt.ctxTimeout)
				defer cancel()
			}

			result, err := repo.ProvisionDevice(ctx, tt.input)
			if (err != nil) != tt.wantErr {
				t.Fatalf("ProvisionDevice() error = %v, wantErr %v", err, tt.wantErr)
			}
			if tt.expectedErr != nil && !errors.Is(err, tt.expectedErr) {
				t.Fatalf("ProvisionDevice() error = %v, want expectedErr %v", err, tt.expectedErr)
			}
			if !tt.wantErr {
				if result == nil {
					t.Fatal("expected non-nil result on success")
				}
				if result.NetworkID != tt.input.NetworkID {
					t.Errorf("got NetworkID %d, want %d", result.NetworkID, tt.input.NetworkID)
				}
				if result.DeviceMAC != tt.input.DeviceMAC {
					t.Errorf("got DeviceMAC %v, want %v", result.DeviceMAC, tt.input.DeviceMAC)
				}
				if tt.input.Generation > 0 && result.Generation != tt.input.Generation {
					t.Errorf("got Generation %d, want %d", result.Generation, tt.input.Generation)
				}
				if result.Status != "ACTIVE" {
					t.Errorf("got Status %s, want ACTIVE", result.Status)
				}
			}
		})
	}
}
