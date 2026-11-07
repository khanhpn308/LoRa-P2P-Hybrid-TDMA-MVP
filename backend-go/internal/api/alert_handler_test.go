package api_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockEventRepo struct {
	events       []*domain.Event
	acknowledged map[int64]bool
}

func newMockEventRepo() *mockEventRepo {
	now := time.Date(2026, 11, 7, 10, 0, 0, 0, time.UTC)
	return &mockEventRepo{
		acknowledged: make(map[int64]bool),
		events: []*domain.Event{
			{
				ID:         102,
				EventID:    "gw01:550e8400-e29b-41d4-a716-446655440000:43",
				GatewayID:  "gw01",
				NodeID:     2,
				Severity:   domain.SeverityP0Emergency,
				IngestedAt: now,
				AckStatus:  domain.AckStatusUnacknowledged,
				Data:       domain.EventData{EventRef: 2, EventCode: 1, EventValue: 1},
			},
			{
				ID:         101,
				EventID:    "gw01:550e8400-e29b-41d4-a716-446655440000:42",
				GatewayID:  "gw01",
				NodeID:     1,
				Severity:   domain.SeverityP1High,
				IngestedAt: now,
				AckStatus:  domain.AckStatusUnacknowledged,
				Data:       domain.EventData{EventRef: 1, EventCode: 1, EventValue: 1},
			},
		},
	}
}

func (m *mockEventRepo) RecordEvent(ctx context.Context, event *domain.Event) (*storage.EventRecordResult, error) {
	return &storage.EventRecordResult{EventID: 101, IsDuplicate: false, Status: "INSERTED"}, nil
}

func (m *mockEventRepo) GetEvent(ctx context.Context, gatewayID, eventID string) (*domain.Event, error) {
	for _, e := range m.events {
		if e.GatewayID == gatewayID && e.EventID == eventID {
			return e, nil
		}
	}
	return nil, storage.ErrEventNotFound
}

func (m *mockEventRepo) QuarantineEvent(ctx context.Context, q *storage.QuarantineRecord) error {
	return nil
}

func (m *mockEventRepo) RecordHealthUpdate(ctx context.Context, h *domain.NodeHealth) error {
	return nil
}

func (m *mockEventRepo) GetNodeHealth(ctx context.Context, gatewayID string, nodeID uint8) (*domain.NodeHealth, error) {
	return nil, storage.ErrHealthNotFound
}

func (m *mockEventRepo) ListEvents(ctx context.Context, cursor int64, limit int) ([]*domain.Event, int64, error) {
	return m.events, 0, nil
}

func (m *mockEventRepo) AcknowledgeEvent(ctx context.Context, alertID int64, acknowledgedBy string) (*domain.Event, error) {
	if alertID == 999 {
		return nil, storage.ErrEventNotFound
	}
	if m.acknowledged[alertID] {
		return nil, storage.ErrAlreadyAcknowledged
	}

	for _, e := range m.events {
		if e.ID == alertID {
			m.acknowledged[alertID] = true
			now := time.Now().UTC()
			e.AckStatus = domain.AckStatusAcknowledged
			e.AcknowledgedAt = &now
			e.AcknowledgedBy = &acknowledgedBy
			return e, nil
		}
	}
	return nil, storage.ErrEventNotFound
}

func (m *mockEventRepo) ListNodeHealth(ctx context.Context, gatewayID string, limit int) ([]*domain.NodeHealth, error) {
	return nil, nil
}

func TestAlertHandler_ListAlerts_Success(t *testing.T) {
	repo := newMockEventRepo()
	handler := api.NewAlertHandler(repo)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/api/v1/alerts?limit=10", nil)
	rec := httptest.NewRecorder()

	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got: %d", rec.Code)
	}

	var page api.AlertPageDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &page); err != nil {
		t.Fatalf("failed to parse AlertPageDTO: %v", err)
	}

	if len(page.Items) != 2 {
		t.Fatalf("expected 2 alerts, got: %d", len(page.Items))
	}
	if page.Items[0].AlertID != "102" || page.Items[0].Severity != "P0_EMERGENCY" {
		t.Fatalf("unexpected alert item: %+v", page.Items[0])
	}
}

func TestAlertHandler_ListAlerts_InvalidLimit(t *testing.T) {
	repo := newMockEventRepo()
	handler := api.NewAlertHandler(repo)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/api/v1/alerts?limit=500", nil)
	rec := httptest.NewRecorder()

	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422 Unprocessable Entity, got: %d", rec.Code)
	}
}

func TestAlertHandler_AcknowledgeAlert_Success(t *testing.T) {
	repo := newMockEventRepo()
	handler := api.NewAlertHandler(repo)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	body := `{"acknowledged_by":"ops_lead"}`
	req := httptest.NewRequest("POST", "/api/v1/alerts/101/acknowledge", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got: %d (%s)", rec.Code, rec.Body.String())
	}

	var alert api.AlertDTO
	if err := json.Unmarshal(rec.Body.Bytes(), &alert); err != nil {
		t.Fatalf("failed to decode alert DTO: %v", err)
	}

	if alert.AlertID != "101" {
		t.Fatalf("expected alert_id=101, got: %s", alert.AlertID)
	}
	if alert.AckStatus != "ACKNOWLEDGED" {
		t.Fatalf("expected ack_status=ACKNOWLEDGED, got: %s", alert.AckStatus)
	}
	if alert.AckedAt == nil {
		t.Fatalf("expected acked_at to be populated")
	}
}

func TestAlertHandler_AcknowledgeAlert_AlreadyAcknowledged(t *testing.T) {
	repo := newMockEventRepo()
	handler := api.NewAlertHandler(repo)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// First ack
	req1 := httptest.NewRequest("POST", "/api/v1/alerts/101/acknowledge", nil)
	rec1 := httptest.NewRecorder()
	mux.ServeHTTP(rec1, req1)
	if rec1.Code != http.StatusOK {
		t.Fatalf("expected first ack 200 OK, got: %d", rec1.Code)
	}

	// Second ack -> 409 Conflict
	req2 := httptest.NewRequest("POST", "/api/v1/alerts/101/acknowledge", nil)
	rec2 := httptest.NewRecorder()
	mux.ServeHTTP(rec2, req2)
	if rec2.Code != http.StatusConflict {
		t.Fatalf("expected second ack 409 Conflict, got: %d", rec2.Code)
	}
}

func TestAlertHandler_AcknowledgeAlert_NotFound(t *testing.T) {
	repo := newMockEventRepo()
	handler := api.NewAlertHandler(repo)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest("POST", "/api/v1/alerts/999/acknowledge", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("expected 404 Not Found, got: %d", rec.Code)
	}
}

func TestAlertHandler_AcknowledgeAlert_InvalidID(t *testing.T) {
	repo := newMockEventRepo()
	handler := api.NewAlertHandler(repo)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest("POST", "/api/v1/alerts/invalid_id/acknowledge", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422 Unprocessable Entity, got: %d", rec.Code)
	}
}
