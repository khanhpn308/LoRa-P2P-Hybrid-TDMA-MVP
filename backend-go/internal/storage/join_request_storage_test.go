package storage_test

import (
	"context"
	"strings"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

func TestPostgresJoinRequestStorage_IsDeviceRegistered_Success(t *testing.T) {
	db := initMockDB("default")
	store := storage.NewPostgresJoinRequestStorage(db)

	isRegistered, err := store.IsDeviceRegistered(context.Background(), "001122334455")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !isRegistered {
		t.Fatalf("expected device to be registered, got false")
	}
}

func TestPostgresJoinRequestStorage_IsDeviceRegistered_NotFound(t *testing.T) {
	db := initMockDB("device_unregistered")
	store := storage.NewPostgresJoinRequestStorage(db)

	isRegistered, err := store.IsDeviceRegistered(context.Background(), "001122334455")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if isRegistered {
		t.Fatalf("expected device to be unregistered, got true")
	}
}

func TestPostgresJoinRequestStorage_IsDeviceRegistered_InvalidMAC(t *testing.T) {
	db := initMockDB("default")
	store := storage.NewPostgresJoinRequestStorage(db)

	tests := []struct {
		name string
		mac  string
	}{
		{name: "too short", mac: "112233"},
		{name: "invalid hex", mac: "0011223344zz"},
		{name: "too long", mac: "00112233445566"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			isRegistered, err := store.IsDeviceRegistered(context.Background(), tt.mac)
			if err == nil {
				t.Fatalf("expected error for invalid MAC %q, got nil", tt.mac)
			}
			if isRegistered {
				t.Fatalf("expected isRegistered false for invalid MAC %q", tt.mac)
			}
		})
	}
}

func TestPostgresJoinRequestStorage_ApproveRequest_PurgesOrphanEvents(t *testing.T) {
	db := initMockDB("default")
	store := storage.NewPostgresJoinRequestStorage(db)

	mockExecMu.Lock()
	mockExecQueries = nil
	mockExecMu.Unlock()

	req, err := store.ApproveRequest(context.Background(), 10, nil)
	if err != nil {
		t.Fatalf("unexpected error approving request: %v", err)
	}

	if req == nil || req.Status != "APPROVED" {
		t.Fatalf("expected status APPROVED, got %+v", req)
	}
	if req.AssignedNodeID == nil || *req.AssignedNodeID != 1 {
		t.Fatalf("expected assigned_node_id 1, got %v", req.AssignedNodeID)
	}

	mockExecMu.Lock()
	queries := make([]string, len(mockExecQueries))
	copy(queries, mockExecQueries)
	mockExecMu.Unlock()

	var foundEventPurge bool
	for _, q := range queries {
		if strings.Contains(strings.ToLower(q), "delete from events where gateway_id = $1 and node_id = $2") {
			foundEventPurge = true
			break
		}
	}

	if !foundEventPurge {
		t.Fatalf("expected orphan event purge query 'DELETE FROM events WHERE gateway_id = $1 AND node_id = $2;' to be executed, but got: %+v", queries)
	}
}
