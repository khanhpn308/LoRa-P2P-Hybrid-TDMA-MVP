package storage_test

import (
	"context"
	"strings"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
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

func TestPostgresJoinRequestStorage_CreateOrUpdate_NewRequest(t *testing.T) {
	db := initMockDB("default")
	store := storage.NewPostgresJoinRequestStorage(db)

	req := &domain.DeviceJoinRequest{
		DeviceMAC: "001122334455",
		GatewayID: "gw01",
		RSSI:      -70,
		SNR:       8.5,
	}

	saved, isNew, err := store.CreateOrUpdateJoinRequest(context.Background(), req)
	if err != nil {
		t.Fatalf("unexpected error creating join request: %v", err)
	}
	if !isNew {
		t.Fatal("expected isNew=true for new join request")
	}
	if saved.ID != 101 {
		t.Fatalf("expected ID 101, got %d", saved.ID)
	}
	if saved.Status != "PENDING" {
		t.Fatalf("expected status PENDING, got %s", saved.Status)
	}
}

func TestPostgresJoinRequestStorage_CreateOrUpdate_PendingDuplicate(t *testing.T) {
	db := initMockDB("join_req_pending")
	store := storage.NewPostgresJoinRequestStorage(db)

	req := &domain.DeviceJoinRequest{
		DeviceMAC: "001122334455",
		GatewayID: "gw01",
		RSSI:      -65,
		SNR:       9.0,
	}

	saved, isNew, err := store.CreateOrUpdateJoinRequest(context.Background(), req)
	if err != nil {
		t.Fatalf("unexpected error updating join request: %v", err)
	}
	if isNew {
		t.Fatal("expected isNew=false for duplicate pending join request")
	}
	if saved.ID != 10 {
		t.Fatalf("expected ID 10, got %d", saved.ID)
	}
	if saved.Status != "PENDING" {
		t.Fatalf("expected status PENDING, got %s", saved.Status)
	}
}

func TestPostgresJoinRequestStorage_CreateOrUpdate_AlreadyApproved(t *testing.T) {
	db := initMockDB("join_req_approved")
	store := storage.NewPostgresJoinRequestStorage(db)

	req := &domain.DeviceJoinRequest{
		DeviceMAC: "001122334455",
		GatewayID: "gw01",
		RSSI:      -60,
		SNR:       11.0,
	}

	saved, isNew, err := store.CreateOrUpdateJoinRequest(context.Background(), req)
	if err != nil {
		t.Fatalf("unexpected error checking approved request: %v", err)
	}
	if isNew {
		t.Fatal("expected isNew=false for already approved device")
	}
	if saved.Status != "APPROVED" {
		t.Fatalf("expected status APPROVED, got %s", saved.Status)
	}
	if saved.AssignedNodeID == nil || *saved.AssignedNodeID != 5 {
		t.Fatalf("expected assigned node ID 5, got %v", saved.AssignedNodeID)
	}
}

func TestPostgresJoinRequestStorage_RejectRequestWithDetails_Success(t *testing.T) {
	db := initMockDB("default")
	store := storage.NewPostgresJoinRequestStorage(db)

	rejected, err := store.RejectRequestWithDetails(context.Background(), 10)
	if err != nil {
		t.Fatalf("unexpected error rejecting request: %v", err)
	}
	if rejected == nil || rejected.Status != "REJECTED" {
		t.Fatalf("expected status REJECTED, got %+v", rejected)
	}
	if rejected.DeviceMAC != "001122334455" {
		t.Fatalf("expected MAC 001122334455, got %s", rejected.DeviceMAC)
	}
	if rejected.GatewayID != "gw01" {
		t.Fatalf("expected GatewayID gw01, got %s", rejected.GatewayID)
	}
}

func TestPostgresJoinRequestStorage_RejectRequestWithDetails_NotFound(t *testing.T) {
	db := initMockDB("join_req_not_found")
	store := storage.NewPostgresJoinRequestStorage(db)

	_, err := store.RejectRequestWithDetails(context.Background(), 999)
	if err == nil || !strings.Contains(err.Error(), "join request not found") {
		t.Fatalf("expected ErrRequestNotFound, got %v", err)
	}
}
