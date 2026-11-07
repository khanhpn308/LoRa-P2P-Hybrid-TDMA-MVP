package api_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockNodeHealthRepo struct {
	nodes []*domain.NodeHealth
}

func (m *mockNodeHealthRepo) RecordEvent(ctx context.Context, event *domain.Event) (*storage.EventRecordResult, error) {
	return nil, nil
}
func (m *mockNodeHealthRepo) GetEvent(ctx context.Context, gatewayID, eventID string) (*domain.Event, error) {
	return nil, nil
}
func (m *mockNodeHealthRepo) QuarantineEvent(ctx context.Context, q *storage.QuarantineRecord) error {
	return nil
}
func (m *mockNodeHealthRepo) RecordHealthUpdate(ctx context.Context, h *domain.NodeHealth) error {
	return nil
}
func (m *mockNodeHealthRepo) GetNodeHealth(ctx context.Context, gatewayID string, nodeID uint8) (*domain.NodeHealth, error) {
	return nil, nil
}
func (m *mockNodeHealthRepo) ListEvents(ctx context.Context, cursor int64, limit int) ([]*domain.Event, int64, error) {
	return nil, 0, nil
}
func (m *mockNodeHealthRepo) AcknowledgeEvent(ctx context.Context, alertID int64, acknowledgedBy string) (*domain.Event, error) {
	return nil, nil
}
func (m *mockNodeHealthRepo) ListNodeHealth(ctx context.Context, gatewayID string, limit int) ([]*domain.NodeHealth, error) {
	return m.nodes, nil
}

func TestNodeHandler_ListNodes_Success(t *testing.T) {
	now := time.Now().UTC()
	repo := &mockNodeHealthRepo{
		nodes: []*domain.NodeHealth{
			{
				GatewayID:    "gw01",
				NodeID:       1,
				HealthStatus: domain.HealthStatusOnline,
				LastSeenAt:   now,
			},
			{
				GatewayID:    "gw01",
				NodeID:       2,
				HealthStatus: domain.HealthStatusOnline,
				LastSeenAt:   now,
			},
		},
	}

	handler := api.NewNodeHandler(repo)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/api/v1/nodes", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got: %d", rec.Code)
	}

	var page api.NodePageDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &page); err != nil {
		t.Fatalf("failed to decode NodePage: %v", err)
	}

	if len(page.Items) != 2 {
		t.Fatalf("expected 2 nodes, got %d", len(page.Items))
	}
	if page.Items[0].NodeID != 1 || *page.Items[0].AssignedSlotID != 1 {
		t.Fatalf("unexpected node summary: %+v", page.Items[0])
	}
}

func TestNodeHandler_GetNodeTelemetry_Gone410(t *testing.T) {
	repo := &mockNodeHealthRepo{}
	handler := api.NewNodeHandler(repo)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/api/v1/nodes/5/telemetry", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusGone {
		t.Fatalf("expected 410 Gone for deprecated telemetry, got: %d", rec.Code)
	}

	var resp api.DeprecatedTelemetryResponseDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse response: %v", err)
	}

	if resp.Code != "DEPRECATED_HISTORICAL" {
		t.Fatalf("expected DEPRECATED_HISTORICAL, got: %s", resp.Code)
	}
}

func TestNodeHandler_GetNodeTelemetry_InvalidNodeID(t *testing.T) {
	repo := &mockNodeHealthRepo{}
	handler := api.NewNodeHandler(repo)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/api/v1/nodes/999/telemetry", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422 Unprocessable Entity, got: %d", rec.Code)
	}
}
