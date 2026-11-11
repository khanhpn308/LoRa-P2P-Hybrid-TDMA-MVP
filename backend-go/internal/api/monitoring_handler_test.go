package api_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
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

func (m *mockMonitoringStorage) ListGateways(ctx context.Context) ([]*domain.GatewayItem, error) {
	return nil, nil
}

func (m *mockMonitoringStorage) CreateGateway(ctx context.Context, gatewayID, name, location, ipAddress string) error {
	return nil
}

func (m *mockMonitoringStorage) DeleteGateway(ctx context.Context, gatewayID string) error {
	if m.gwErr != nil {
		return m.gwErr
	}
	delete(m.gateways, gatewayID)
	return nil
}

func (m *mockMonitoringStorage) DeleteNode(ctx context.Context, nodeID string) error {
	if m.nodeErr != nil {
		return m.nodeErr
	}
	var remaining []domain.NodeSummary
	for _, n := range m.nodes {
		if fmt.Sprintf("%d", n.NodeID) != nodeID && fmt.Sprintf("N-%03d", n.NodeID) != nodeID {
			remaining = append(remaining, n)
		}
	}
	m.nodes = remaining
	return nil
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

			handler := api.NewMonitoringHandler(store, tc.offlineThreshold, nil)
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

			handler := api.NewMonitoringHandler(store, 5*time.Minute, nil)
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

func TestMonitoringHandler_DeleteGateway_Table(t *testing.T) {
	authMap := map[string]api.Role{
		"token-admin":    api.RoleAdmin,
		"token-operator": api.RoleOperator,
		"token-viewer":   api.RoleViewer,
	}
	staticAuth := api.NewStaticAuthenticator(authMap)

	tests := []struct {
		name           string
		gatewayID      string
		token          string
		storageErr     error
		expectedStatus int
	}{
		{
			name:           "missing bearer token returns 401",
			gatewayID:      "gw01",
			token:          "",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "invalid bearer token returns 401",
			gatewayID:      "gw01",
			token:          "invalid-token",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "role VIEWER returns 403 Forbidden",
			gatewayID:      "gw01",
			token:          "token-viewer",
			expectedStatus: http.StatusForbidden,
		},
		{
			name:           "role OPERATOR returns 403 Forbidden",
			gatewayID:      "gw01",
			token:          "token-operator",
			expectedStatus: http.StatusForbidden,
		},
		{
			name:           "invalid gateway ID format returns 422",
			gatewayID:      "invalid!gw!",
			token:          "token-admin",
			expectedStatus: http.StatusUnprocessableEntity,
		},
		{
			name:           "storage failure returns 500",
			gatewayID:      "gw01",
			token:          "token-admin",
			storageErr:     errors.New("db error"),
			expectedStatus: http.StatusInternalServerError,
		},
		{
			name:           "role ADMIN deletes gateway successfully returns 200",
			gatewayID:      "gw01",
			token:          "token-admin",
			expectedStatus: http.StatusOK,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			store := newMockMonitoringStorage()
			store.gwErr = tc.storageErr
			store.gateways["gw01"] = &domain.GatewayStatusRecord{GatewayID: "gw01"}

			handler := api.NewMonitoringHandler(store, 5*time.Minute, nil, staticAuth)
			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)

			req := httptest.NewRequest(http.MethodDelete, "/api/v1/gateways/"+tc.gatewayID, nil)
			if tc.token != "" {
				req.Header.Set("Authorization", "Bearer "+tc.token)
			}
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tc.expectedStatus {
				t.Fatalf("expected status %d, got %d: %s", tc.expectedStatus, rec.Code, rec.Body.String())
			}

			if tc.expectedStatus == http.StatusOK {
				var resp map[string]interface{}
				if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
					t.Fatalf("failed to decode response: %v", err)
				}
				if resp["status"] != "DELETED" || resp["gateway_id"] != tc.gatewayID {
					t.Fatalf("unexpected response body: %v", resp)
				}
				if _, exists := store.gateways[tc.gatewayID]; exists {
					t.Fatalf("expected gateway to be deleted from store")
				}
			}
		})
	}
}

func TestMonitoringHandler_DeleteNode_Table(t *testing.T) {
	authMap := map[string]api.Role{
		"token-admin":    api.RoleAdmin,
		"token-operator": api.RoleOperator,
		"token-viewer":   api.RoleViewer,
	}
	staticAuth := api.NewStaticAuthenticator(authMap)

	tests := []struct {
		name           string
		nodeID         string
		token          string
		storageErr     error
		expectedStatus int
	}{
		{
			name:           "missing bearer token returns 401",
			nodeID:         "12",
			token:          "",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "invalid bearer token returns 401",
			nodeID:         "12",
			token:          "bad-token",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "role VIEWER returns 403 Forbidden",
			nodeID:         "12",
			token:          "token-viewer",
			expectedStatus: http.StatusForbidden,
		},
		{
			name:           "role OPERATOR returns 403 Forbidden",
			nodeID:         "12",
			token:          "token-operator",
			expectedStatus: http.StatusForbidden,
		},
		{
			name:           "storage error returns 500",
			nodeID:         "12",
			token:          "token-admin",
			storageErr:     errors.New("db error"),
			expectedStatus: http.StatusInternalServerError,
		},
		{
			name:           "role ADMIN deletes numeric node returns 200",
			nodeID:         "1",
			token:          "token-admin",
			expectedStatus: http.StatusOK,
		},
		{
			name:           "role ADMIN deletes node by MAC returns 200",
			nodeID:         "aabbccddeeff",
			token:          "token-admin",
			expectedStatus: http.StatusOK,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			store := newMockMonitoringStorage()
			store.nodeErr = tc.storageErr
			store.nodes = []domain.NodeSummary{
				{NodeID: 1, GatewayID: "gw01", Status: "ONLINE"},
				{NodeID: 2, GatewayID: "gw01", Status: "OFFLINE"},
			}

			handler := api.NewMonitoringHandler(store, 5*time.Minute, nil, staticAuth)
			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)

			req := httptest.NewRequest(http.MethodDelete, "/api/v1/nodes/"+tc.nodeID, nil)
			if tc.token != "" {
				req.Header.Set("Authorization", "Bearer "+tc.token)
			}
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tc.expectedStatus {
				t.Fatalf("expected status %d, got %d: %s", tc.expectedStatus, rec.Code, rec.Body.String())
			}

			if tc.expectedStatus == http.StatusOK {
				var resp map[string]interface{}
				if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
					t.Fatalf("failed to decode response: %v", err)
				}
				if resp["status"] != "DELETED" || resp["node_id"] != tc.nodeID {
					t.Fatalf("unexpected response body: %v", resp)
				}
			}
		})
	}
}

func TestMonitoringHandler_CreateGateway_Table(t *testing.T) {
	authMap := map[string]api.Role{
		"token-admin":    api.RoleAdmin,
		"token-operator": api.RoleOperator,
		"token-viewer":   api.RoleViewer,
	}
	staticAuth := api.NewStaticAuthenticator(authMap)

	tests := []struct {
		name           string
		body           string
		token          string
		expectedStatus int
	}{
		{
			name:           "missing bearer token returns 401",
			body:           `{"gateway_id":"gw01","name":"Gateway 1"}`,
			token:          "",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "empty bearer token returns 401",
			body:           `{"gateway_id":"gw01","name":"Gateway 1"}`,
			token:          " ",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "invalid bearer token returns 401",
			body:           `{"gateway_id":"gw01","name":"Gateway 1"}`,
			token:          "invalid-token",
			expectedStatus: http.StatusUnauthorized,
		},
		{
			name:           "role VIEWER returns 403 Forbidden",
			body:           `{"gateway_id":"gw01","name":"Gateway 1"}`,
			token:          "token-viewer",
			expectedStatus: http.StatusForbidden,
		},
		{
			name:           "role OPERATOR returns 403 Forbidden",
			body:           `{"gateway_id":"gw01","name":"Gateway 1"}`,
			token:          "token-operator",
			expectedStatus: http.StatusForbidden,
		},
		{
			name:           "role ADMIN returns 201 Created",
			body:           `{"gateway_id":"gw01","name":"Gateway 1","location":"Building A","ip_address":"192.168.1.10"}`,
			token:          "token-admin",
			expectedStatus: http.StatusCreated,
		},
		{
			name:           "malformed JSON returns 400 Bad Request",
			body:           `{"gateway_id": invalid_json}`,
			token:          "token-admin",
			expectedStatus: http.StatusBadRequest,
		},
		{
			name:           "invalid gateway ID format returns 422",
			body:           `{"gateway_id":"invalid!gw!","name":"Bad Gateway"}`,
			token:          "token-admin",
			expectedStatus: http.StatusUnprocessableEntity,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			store := newMockMonitoringStorage()
			handler := api.NewMonitoringHandler(store, 5*time.Minute, nil, staticAuth)
			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)

			req := httptest.NewRequest(http.MethodPost, "/api/v1/gateways", strings.NewReader(tc.body))
			req.Header.Set("Content-Type", "application/json")
			if tc.token != "" {
				if tc.token == " " {
					req.Header.Set("Authorization", "Bearer ")
				} else {
					req.Header.Set("Authorization", "Bearer "+tc.token)
				}
			}
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != tc.expectedStatus {
				t.Fatalf("expected status %d, got %d: %s", tc.expectedStatus, rec.Code, rec.Body.String())
			}

			if tc.expectedStatus == http.StatusCreated {
				var resp map[string]interface{}
				if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
					t.Fatalf("failed to decode response: %v", err)
				}
				if resp["status"] != "CREATED" || resp["gateway_id"] != "gw01" {
					t.Fatalf("unexpected response body: %v", resp)
				}
			}
		})
	}
}

type mockRevocationPublisher struct {
	calls []struct {
		gatewayID string
		nodeID    int
	}
	err error
}

func (m *mockRevocationPublisher) PublishNodeRevoke(ctx context.Context, gatewayID string, nodeID int) error {
	if m.err != nil {
		return m.err
	}
	m.calls = append(m.calls, struct {
		gatewayID string
		nodeID    int
	}{gatewayID: gatewayID, nodeID: nodeID})
	return nil
}

func TestMonitoringHandler_DeleteNode_PublishesDownlinkRevoke(t *testing.T) {
	authMap := map[string]api.Role{
		"token-admin": api.RoleAdmin,
	}
	staticAuth := api.NewStaticAuthenticator(authMap)

	store := newMockMonitoringStorage()
	store.nodes = []domain.NodeSummary{
		{NodeID: 42, GatewayID: "gw-test-01", Status: "ONLINE"},
	}

	handler := api.NewMonitoringHandler(store, 5*time.Minute, nil, staticAuth)
	pub := &mockRevocationPublisher{}
	handler.SetRevocationPublisher(pub)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/nodes/42", nil)
	req.Header.Set("Authorization", "Bearer token-admin")
	rec := httptest.NewRecorder()

	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d: %s", rec.Code, rec.Body.String())
	}

	if len(pub.calls) != 1 {
		t.Fatalf("expected 1 call to PublishNodeRevoke, got %d", len(pub.calls))
	}

	if pub.calls[0].gatewayID != "gw-test-01" {
		t.Fatalf("expected gatewayID gw-test-01, got %s", pub.calls[0].gatewayID)
	}

	if pub.calls[0].nodeID != 42 {
		t.Fatalf("expected nodeID 42, got %d", pub.calls[0].nodeID)
	}
}

func TestMonitoringHandler_DeleteNode_WithGatewayQueryHint(t *testing.T) {
	authMap := map[string]api.Role{
		"token-admin": api.RoleAdmin,
	}
	staticAuth := api.NewStaticAuthenticator(authMap)

	store := newMockMonitoringStorage()
	handler := api.NewMonitoringHandler(store, 5*time.Minute, nil, staticAuth)
	pub := &mockRevocationPublisher{}
	handler.SetRevocationPublisher(pub)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodDelete, "/api/v1/nodes/N-15?gateway_id=gw-custom", nil)
	req.Header.Set("Authorization", "Bearer token-admin")
	rec := httptest.NewRecorder()

	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d: %s", rec.Code, rec.Body.String())
	}

	if len(pub.calls) != 1 {
		t.Fatalf("expected 1 call to PublishNodeRevoke, got %d", len(pub.calls))
	}

	if pub.calls[0].gatewayID != "gw-custom" {
		t.Fatalf("expected gatewayID gw-custom, got %s", pub.calls[0].gatewayID)
	}

	if pub.calls[0].nodeID != 15 {
		t.Fatalf("expected nodeID 15, got %d", pub.calls[0].nodeID)
	}
}
