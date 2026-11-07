package api_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockMonitoringStorage struct {
	gateways map[string]*domain.GatewayStatusRecord
	nodes    []domain.NodeSummary
	gwErr    error
	nodeErr  error
}

func newMockMonitoringStorage() *mockMonitoringStorage {
	return &mockMonitoringStorage{
		gateways: make(map[string]*domain.GatewayStatusRecord),
	}
}

func (m *mockMonitoringStorage) UpsertGatewayStatus(ctx context.Context, status *domain.GatewayStatusRecord) error {
	m.gateways[status.GatewayID] = status
	return nil
}

func (m *mockMonitoringStorage) GetGatewayStatus(ctx context.Context, gatewayID string) (*domain.GatewayStatusRecord, error) {
	if m.gwErr != nil {
		return nil, m.gwErr
	}
	rec, ok := m.gateways[gatewayID]
	if !ok {
		return nil, storage.ErrGatewayStatusNotFound
	}
	return rec, nil
}

func (m *mockMonitoringStorage) ListNodes(ctx context.Context, filter domain.NodeFilter) (*domain.NodePage, error) {
	if m.nodeErr != nil {
		return nil, m.nodeErr
	}

	var filtered []domain.NodeSummary
	for _, n := range m.nodes {
		if filter.GatewayID != "" && n.GatewayID != filter.GatewayID {
			continue
		}
		if filter.Status != "" && n.Status != filter.Status {
			continue
		}
		filtered = append(filtered, n)
	}

	var nextCursor *string
	if len(filtered) > filter.Limit {
		c := "2"
		nextCursor = &c
		filtered = filtered[:filter.Limit]
	}

	return &domain.NodePage{
		Items:      filtered,
		NextCursor: nextCursor,
	}, nil
}

func TestMonitoringHandler_GetGatewayStatus_Table(t *testing.T) {
	now := time.Now().UTC()
	staleTime := now.Add(-10 * time.Minute)

	tests := []struct {
		name             string
		gatewayID        string
		storedRecord     *domain.GatewayStatusRecord
		storageErr       error
		offlineThreshold time.Duration
		expectedStatus   int
		expectedMode     string
	}{
		{
			name:      "active fresh gateway returns 200 with ACTIVE mode",
			gatewayID: "gw-active",
			storedRecord: &domain.GatewayStatusRecord{
				GatewayID:             "gw-active",
				GatewayEpoch:          "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				Mode:                  domain.GatewayModeActive,
				ActiveScheduleVersion: 42,
				RFDutyPermille:        150,
				NodeCount:             8,
				LastSeenAt:            now,
			},
			offlineThreshold: 5 * time.Minute,
			expectedStatus:   http.StatusOK,
			expectedMode:     "ACTIVE",
		},
		{
			name:      "stale gateway past threshold returns 200 with OFFLINE mode",
			gatewayID: "gw-stale",
			storedRecord: &domain.GatewayStatusRecord{
				GatewayID:             "gw-stale",
				GatewayEpoch:          "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				Mode:                  domain.GatewayModeActive,
				ActiveScheduleVersion: 10,
				RFDutyPermille:        0,
				NodeCount:             2,
				LastSeenAt:            staleTime,
			},
			offlineThreshold: 5 * time.Minute,
			expectedStatus:   http.StatusOK,
			expectedMode:     "OFFLINE",
		},
		{
			name:           "gateway not found returns 404",
			gatewayID:      "gw-unknown",
			expectedStatus: http.StatusNotFound,
		},
		{
			name:           "invalid gateway id format returns 422",
			gatewayID:      "gw_invalid@char",
			expectedStatus: http.StatusUnprocessableEntity,
		},
		{
			name:           "storage failure returns 500",
			gatewayID:      "gw-err",
			storageErr:     errors.New("db error"),
			expectedStatus: http.StatusInternalServerError,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			store := newMockMonitoringStorage()
			if tc.storedRecord != nil {
				store.gateways[tc.storedRecord.GatewayID] = tc.storedRecord
			}
			store.gwErr = tc.storageErr

			handler := api.NewMonitoringHandler(store, tc.offlineThreshold)
			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)

			req := httptest.NewRequest(http.MethodGet, "/api/v1/gateways/"+tc.gatewayID+"/status", nil)
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tc.expectedStatus {
				t.Fatalf("expected status %d, got %d: %s", tc.expectedStatus, rec.Code, rec.Body.String())
			}

			if tc.expectedStatus == http.StatusOK {
				var view domain.GatewayStatusView
				if err := json.NewDecoder(rec.Body).Decode(&view); err != nil {
					t.Fatalf("failed to decode response: %v", err)
				}
				if view.Mode != tc.expectedMode {
					t.Fatalf("expected mode %s, got %s", tc.expectedMode, view.Mode)
				}
				if view.GatewayID != tc.gatewayID {
					t.Fatalf("expected gateway_id %s, got %s", tc.gatewayID, view.GatewayID)
				}
			}
		})
	}
}

func TestMonitoringHandler_ListNodes_Table(t *testing.T) {
	nowStr := time.Now().UTC().Format(time.RFC3339)
	slot1, slot2, slot3 := 1, 2, 3

	mockNodes := []domain.NodeSummary{
		{
			NodeID:         1,
			GatewayID:      "gw-01",
			AssignedSlotID: &slot1,
			LastSeenAt:     &nowStr,
			Status:         "ONLINE",
		},
		{
			NodeID:         2,
			GatewayID:      "gw-01",
			AssignedSlotID: &slot2,
			LastSeenAt:     &nowStr,
			Status:         "OFFLINE",
		},
		{
			NodeID:         3,
			GatewayID:      "gw-02",
			AssignedSlotID: &slot3,
			LastSeenAt:     &nowStr,
			Status:         "ONLINE",
		},
	}

	tests := []struct {
		name           string
		queryURL       string
		storageErr     error
		expectedStatus int
		expectedCount  int
	}{
		{
			name:           "default query returns all nodes",
			queryURL:       "/api/v1/nodes",
			expectedStatus: http.StatusOK,
			expectedCount:  3,
		},
		{
			name:           "filter by gateway_id",
			queryURL:       "/api/v1/nodes?gateway_id=gw-01",
			expectedStatus: http.StatusOK,
			expectedCount:  2,
		},
		{
			name:           "filter by status ONLINE",
			queryURL:       "/api/v1/nodes?status=ONLINE",
			expectedStatus: http.StatusOK,
			expectedCount:  2,
		},
		{
			name:           "filter with limit and pagination",
			queryURL:       "/api/v1/nodes?limit=2&cursor=0",
			expectedStatus: http.StatusOK,
			expectedCount:  2,
		},
		{
			name:           "invalid limit 0 returns 422",
			queryURL:       "/api/v1/nodes?limit=0",
			expectedStatus: http.StatusUnprocessableEntity,
		},
		{
			name:           "invalid limit > 100 returns 422",
			queryURL:       "/api/v1/nodes?limit=101",
			expectedStatus: http.StatusUnprocessableEntity,
		},
		{
			name:           "invalid gateway_id regex returns 422",
			queryURL:       "/api/v1/nodes?gateway_id=invalid!gw",
			expectedStatus: http.StatusUnprocessableEntity,
		},
		{
			name:           "invalid status enum returns 422",
			queryURL:       "/api/v1/nodes?status=INVALID_STATUS",
			expectedStatus: http.StatusUnprocessableEntity,
		},
		{
			name:           "invalid cursor returns 422",
			queryURL:       "/api/v1/nodes?cursor=-5",
			expectedStatus: http.StatusUnprocessableEntity,
		},
		{
			name:           "storage failure returns 500",
			queryURL:       "/api/v1/nodes",
			storageErr:     errors.New("db error"),
			expectedStatus: http.StatusInternalServerError,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			store := newMockMonitoringStorage()
			store.nodes = mockNodes
			store.nodeErr = tc.storageErr

			handler := api.NewMonitoringHandler(store, 5*time.Minute)
			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)

			req := httptest.NewRequest(http.MethodGet, tc.queryURL, nil)
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tc.expectedStatus {
				t.Fatalf("expected status %d, got %d: %s", tc.expectedStatus, rec.Code, rec.Body.String())
			}

			if tc.expectedStatus == http.StatusOK {
				var page domain.NodePage
				if err := json.NewDecoder(rec.Body).Decode(&page); err != nil {
					t.Fatalf("failed to decode response: %v", err)
				}
				if len(page.Items) != tc.expectedCount {
					t.Fatalf("expected %d items, got %d", tc.expectedCount, len(page.Items))
				}
			}
		})
	}
}
