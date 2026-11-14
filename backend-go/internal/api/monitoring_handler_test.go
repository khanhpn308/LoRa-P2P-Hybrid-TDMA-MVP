package api_test

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/presence"
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
	if m.gwErr != nil {
		return nil, m.gwErr
	}
	var res []*domain.GatewayItem
	for _, gw := range m.gateways {
		res = append(res, &domain.GatewayItem{
			GatewayID: gw.GatewayID,
			Mode:      string(gw.Mode),
			NodeCount: gw.NodeCount,
		})
	}
	return res, nil
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

var deleteDriverOnce sync.Once

type mockDeleteExec struct {
	query string
	args  []driver.Value
}

type mockDeleteQuery struct {
	query string
	args  []driver.Value
}

type mockDeleteTracker struct {
	mu             sync.Mutex
	execs          []mockDeleteExec
	queries        []mockDeleteQuery
	assignedNodeID int
	assignedGwID   string
}

func (t *mockDeleteTracker) reset() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.execs = nil
	t.queries = nil
	t.assignedNodeID = 1
	t.assignedGwID = "gw-test-01"
}

func (t *mockDeleteTracker) addExec(q string, args []driver.Value) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.execs = append(t.execs, mockDeleteExec{query: q, args: args})
}

func (t *mockDeleteTracker) addQuery(q string, args []driver.Value) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.queries = append(t.queries, mockDeleteQuery{query: q, args: args})
}

func (t *mockDeleteTracker) getExecs() []mockDeleteExec {
	t.mu.Lock()
	defer t.mu.Unlock()
	res := make([]mockDeleteExec, len(t.execs))
	copy(res, t.execs)
	return res
}

var globalDeleteTracker = &mockDeleteTracker{
	assignedNodeID: 1,
	assignedGwID:   "gw-test-01",
}

type mockDeleteDriver struct{}

func (d *mockDeleteDriver) Open(name string) (driver.Conn, error) {
	return &mockDeleteConn{}, nil
}

type mockDeleteConn struct{}

func (c *mockDeleteConn) Prepare(query string) (driver.Stmt, error) {
	return &mockDeleteStmt{query: query}, nil
}

func (c *mockDeleteConn) Close() error { return nil }
func (c *mockDeleteConn) Begin() (driver.Tx, error) {
	return &mockDeleteTx{}, nil
}
func (c *mockDeleteConn) BeginTx(ctx context.Context, opts driver.TxOptions) (driver.Tx, error) {
	return &mockDeleteTx{}, nil
}

type mockDeleteTx struct{}

func (t *mockDeleteTx) Commit() error   { return nil }
func (t *mockDeleteTx) Rollback() error { return nil }

type mockDeleteStmt struct {
	query string
}

func (s *mockDeleteStmt) Close() error  { return nil }
func (s *mockDeleteStmt) NumInput() int { return -1 }

func (s *mockDeleteStmt) Exec(args []driver.Value) (driver.Result, error) {
	globalDeleteTracker.addExec(s.query, args)
	return driver.RowsAffected(1), nil
}

func (s *mockDeleteStmt) Query(args []driver.Value) (driver.Rows, error) {
	globalDeleteTracker.addQuery(s.query, args)
	q := strings.ToLower(s.query)

	if strings.Contains(q, "from device_join_requests where lower(device_mac) = $1") {
		globalDeleteTracker.mu.Lock()
		nid := int64(globalDeleteTracker.assignedNodeID)
		gid := globalDeleteTracker.assignedGwID
		globalDeleteTracker.mu.Unlock()
		return &mockDeleteRows{
			cols: []string{"gateway_id", "assigned_node_id"},
			data: [][]driver.Value{{gid, nid}},
		}, nil
	}

	if strings.Contains(q, "from node_health where node_id = $1") {
		globalDeleteTracker.mu.Lock()
		gid := globalDeleteTracker.assignedGwID
		globalDeleteTracker.mu.Unlock()
		return &mockDeleteRows{
			cols: []string{"gateway_id"},
			data: [][]driver.Value{{gid}},
		}, nil
	}

	if strings.Contains(q, "from device_join_requests where assigned_node_id = $1") {
		globalDeleteTracker.mu.Lock()
		gid := globalDeleteTracker.assignedGwID
		globalDeleteTracker.mu.Unlock()
		return &mockDeleteRows{
			cols: []string{"gateway_id"},
			data: [][]driver.Value{{gid}},
		}, nil
	}

	return &mockDeleteRows{cols: []string{"id"}, data: nil}, nil
}

type mockDeleteRows struct {
	cols []string
	data [][]driver.Value
	idx  int
}

func (r *mockDeleteRows) Columns() []string {
	return r.cols
}

func (r *mockDeleteRows) Close() error {
	return nil
}

func (r *mockDeleteRows) Next(dest []driver.Value) error {
	if r.idx >= len(r.data) {
		return io.EOF
	}
	row := r.data[r.idx]
	for i, val := range row {
		if i < len(dest) {
			dest[i] = val
		}
	}
	r.idx++
	return nil
}

func initMockDeleteDB() *sql.DB {
	deleteDriverOnce.Do(func() {
		sql.Register("mock_delete_postgres", &mockDeleteDriver{})
	})
	db, err := sql.Open("mock_delete_postgres", "default")
	if err != nil {
		panic(err)
	}
	return db
}

func TestMonitoringHandler_DeleteNode_PurgesEventsAndFormats(t *testing.T) {
	authMap := map[string]api.Role{
		"token-admin": api.RoleAdmin,
	}
	staticAuth := api.NewStaticAuthenticator(authMap)
	db := initMockDeleteDB()

	tests := []struct {
		name                 string
		nodeIDPath           string
		configuredNodeID     int
		configuredGwID       string
		expectedTargetNodeID int
		expectedEventsTarget int
		expectedGatewayScope string
	}{
		{
			name:                 "numeric ID '1'",
			nodeIDPath:           "1",
			configuredNodeID:     1,
			configuredGwID:       "gw-test-01",
			expectedTargetNodeID: 1,
			expectedEventsTarget: 1,
			expectedGatewayScope: "gw-test-01",
		},
		{
			name:                 "prefixed ID 'N-042'",
			nodeIDPath:           "N-042",
			configuredNodeID:     42,
			configuredGwID:       "gw-test-01",
			expectedTargetNodeID: 42,
			expectedEventsTarget: 42,
			expectedGatewayScope: "gw-test-01",
		},
		{
			name:                 "MAC hex '001122334455' resolves assigned node id",
			nodeIDPath:           "001122334455",
			configuredNodeID:     10,
			configuredGwID:       "gw-test-mac",
			expectedTargetNodeID: 10,
			expectedEventsTarget: 10,
			expectedGatewayScope: "gw-test-mac",
		},
		{
			name:                 "prefixed ID with gateway hint 'N-005?gateway_id=gw-custom-scope'",
			nodeIDPath:           "N-005?gateway_id=gw-custom-scope",
			configuredNodeID:     5,
			configuredGwID:       "gw-test-01",
			expectedTargetNodeID: 5,
			expectedEventsTarget: 5,
			expectedGatewayScope: "gw-custom-scope",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			globalDeleteTracker.reset()
			globalDeleteTracker.assignedNodeID = tc.configuredNodeID
			globalDeleteTracker.assignedGwID = tc.configuredGwID

			tracker := presence.NewTracker()
			tracker.SetNodeStatus(tc.expectedTargetNodeID, true)
			if !tracker.IsNodeOnline(tc.expectedTargetNodeID) {
				t.Fatalf("expected node %d to be online before delete", tc.expectedTargetNodeID)
			}

			store := newMockMonitoringStorage()
			handler := api.NewMonitoringHandler(store, 5*time.Minute, tracker, staticAuth)
			handler.SetDB(db)

			pub := &mockRevocationPublisher{}
			handler.SetRevocationPublisher(pub)

			mux := http.NewServeMux()
			handler.RegisterRoutes(mux)

			req := httptest.NewRequest(http.MethodDelete, "/api/v1/nodes/"+tc.nodeIDPath, nil)
			req.Header.Set("Authorization", "Bearer token-admin")
			rec := httptest.NewRecorder()

			mux.ServeHTTP(rec, req)

			if rec.Code != http.StatusOK {
				t.Fatalf("expected status 200 OK, got %d: %s", rec.Code, rec.Body.String())
			}

			// Verify presenceTracker was cleared for targetNodeID
			if tracker.IsNodeOnline(tc.expectedTargetNodeID) {
				t.Fatalf("expected presenceTracker to mark node %d offline after delete", tc.expectedTargetNodeID)
			}

			// Verify revocation downlink was published
			if len(pub.calls) != 1 {
				t.Fatalf("expected 1 revocation downlink call, got %d", len(pub.calls))
			}
			if pub.calls[0].nodeID != tc.expectedTargetNodeID {
				t.Fatalf("expected revocation call for nodeID %d, got %d", tc.expectedTargetNodeID, pub.calls[0].nodeID)
			}
			if pub.calls[0].gatewayID != tc.expectedGatewayScope {
				t.Fatalf("expected revocation call for gatewayID %s, got %s", tc.expectedGatewayScope, pub.calls[0].gatewayID)
			}

			// Verify database statements executed
			execs := globalDeleteTracker.getExecs()
			var foundEventsDelete, foundHealthDelete, foundRequestsDelete bool
			for _, e := range execs {
				lower := strings.ToLower(e.query)
				if strings.Contains(lower, "delete from events") {
					foundEventsDelete = true
					if len(e.args) < 1 || e.args[0] != int64(tc.expectedEventsTarget) && e.args[0] != tc.expectedEventsTarget {
						t.Errorf("events delete arg 0 expected %d, got %v", tc.expectedEventsTarget, e.args[0])
					}
					if len(e.args) >= 2 && e.args[1] != tc.expectedGatewayScope {
						t.Errorf("events delete arg 1 expected gateway %s, got %v", tc.expectedGatewayScope, e.args[1])
					}
				}
				if strings.Contains(lower, "delete from node_health") {
					foundHealthDelete = true
				}
				if strings.Contains(lower, "delete from device_join_requests") {
					foundRequestsDelete = true
				}
			}

			if !foundEventsDelete {
				t.Fatalf("expected DELETE FROM events to be executed, but not found in execs: %+v", execs)
			}
			if !foundHealthDelete {
				t.Fatalf("expected DELETE FROM node_health to be executed, but not found in execs: %+v", execs)
			}
			if !foundRequestsDelete {
				t.Fatalf("expected DELETE FROM device_join_requests to be executed, but not found in execs: %+v", execs)
			}
		})
	}
}

func TestMonitoringHandler_RFMetrics_NodeListOverlay(t *testing.T) {
	store := newMockMonitoringStorage()
	store.nodes = []domain.NodeSummary{
		{
			NodeID:    12,
			GatewayID: "gw01",
			Status:    "ONLINE",
		},
		{
			NodeID:    13,
			GatewayID: "gw01",
			Status:    "ONLINE",
		},
	}

	tracker := presence.NewTracker()
	rfTracker := tracker.RF()
	chIdx := 4
	rfTracker.UpdateNodeRF("gw01", 12, -88, -7.75, &chIdx, "UP_EVENT", "VERIFIED", "550e8400-e29b-41d4-a716-446655440000", 1001, 123456, 15)

	handler := api.NewMonitoringHandler(store, 5*time.Minute, tracker)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v1/nodes", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d: %s", rec.Code, rec.Body.String())
	}

	var page domain.NodePage
	if err := json.NewDecoder(rec.Body).Decode(&page); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if len(page.Items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(page.Items))
	}

	var node12, node13 *domain.NodeSummary
	for i := range page.Items {
		if page.Items[i].NodeID == 12 {
			node12 = &page.Items[i]
		}
		if page.Items[i].NodeID == 13 {
			node13 = &page.Items[i]
		}
	}

	if node12 == nil || node13 == nil {
		t.Fatalf("missing expected nodes in response")
	}

	// Verify node 12 overlay
	if node12.LastRssiDbm == nil || *node12.LastRssiDbm != -88 {
		t.Errorf("expected node 12 last_rssi_dbm -88, got %v", node12.LastRssiDbm)
	}
	if node12.LastSnrDb == nil || *node12.LastSnrDb != -7.75 {
		t.Errorf("expected node 12 last_snr_db -7.75, got %v", node12.LastSnrDb)
	}
	if node12.ChannelIdx == nil || *node12.ChannelIdx != 4 {
		t.Errorf("expected node 12 channel_idx 4, got %v", node12.ChannelIdx)
	}
	if node12.RfSource == nil || *node12.RfSource != "UP_EVENT" {
		t.Errorf("expected node 12 rf_source UP_EVENT, got %v", node12.RfSource)
	}
	if node12.RfStale == nil || *node12.RfStale != false {
		t.Errorf("expected node 12 rf_stale false, got %v", node12.RfStale)
	}
	if node12.LastRfAt == nil || *node12.LastRfAt == "" {
		t.Errorf("expected node 12 last_rf_at non-empty")
	}
	if node12.RfAgeSeconds == nil || *node12.RfAgeSeconds < 0 {
		t.Errorf("expected node 12 rf_age_seconds non-negative")
	}

	// Verify node 13 without RF remains nil (never substituted with zero!)
	if node13.LastRssiDbm != nil {
		t.Errorf("expected node 13 last_rssi_dbm nil, got %v", node13.LastRssiDbm)
	}
	if node13.LastSnrDb != nil {
		t.Errorf("expected node 13 last_snr_db nil, got %v", node13.LastSnrDb)
	}
	if node13.LastRfAt != nil {
		t.Errorf("expected node 13 last_rf_at nil, got %v", node13.LastRfAt)
	}
	if node13.RfAgeSeconds != nil {
		t.Errorf("expected node 13 rf_age_seconds nil, got %v", node13.RfAgeSeconds)
	}
	if node13.RfSource != nil {
		t.Errorf("expected node 13 rf_source nil, got %v", node13.RfSource)
	}
	if node13.RfStale != nil {
		t.Errorf("expected node 13 rf_stale nil, got %v", node13.RfStale)
	}
	if node13.ChannelIdx != nil {
		t.Errorf("expected node 13 channel_idx nil, got %v", node13.ChannelIdx)
	}
}

func TestMonitoringHandler_RFMetrics_GatewayStatusOverlay(t *testing.T) {
	store := newMockMonitoringStorage()
	store.gateways["gw01"] = &domain.GatewayStatusRecord{
		GatewayID: "gw01",
		Mode:      domain.GatewayModeActive,
		NodeCount: 5,
	}

	tracker := presence.NewTracker()
	rfTracker := tracker.RF()
	rfTracker.UpdateChannelRF("gw01", 0, -108, "RX_IDLE", "550e8400-e29b-41d4-a716-446655440000", 1002, 123457, 20)

	handler := api.NewMonitoringHandler(store, 5*time.Minute, tracker)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// 1. Test GET /api/v1/gateways/gw01/status
	reqStatus := httptest.NewRequest(http.MethodGet, "/api/v1/gateways/gw01/status", nil)
	recStatus := httptest.NewRecorder()
	mux.ServeHTTP(recStatus, reqStatus)

	if recStatus.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d: %s", recStatus.Code, recStatus.Body.String())
	}

	var statusView domain.GatewayStatusView
	if err := json.NewDecoder(recStatus.Body).Decode(&statusView); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if statusView.ChannelRssiDbm == nil || *statusView.ChannelRssiDbm != -108 {
		t.Errorf("expected channel_rssi_dbm -108, got %v", statusView.ChannelRssiDbm)
	}
	if statusView.ChannelSampleContext == nil || *statusView.ChannelSampleContext != "RX_IDLE" {
		t.Errorf("expected channel_sample_context RX_IDLE, got %v", statusView.ChannelSampleContext)
	}
	if statusView.ChannelIdx == nil || *statusView.ChannelIdx != 0 {
		t.Errorf("expected channel_idx 0, got %v", statusView.ChannelIdx)
	}
	if statusView.ChannelRfStale == nil || *statusView.ChannelRfStale != false {
		t.Errorf("expected channel_rf_stale false, got %v", statusView.ChannelRfStale)
	}
	if statusView.ChannelRfAt == nil || *statusView.ChannelRfAt == "" {
		t.Errorf("expected channel_rf_at non-empty")
	}

	// 2. Test GET /api/v1/gateways list overlay
	reqList := httptest.NewRequest(http.MethodGet, "/api/v1/gateways", nil)
	recList := httptest.NewRecorder()
	mux.ServeHTTP(recList, reqList)

	if recList.Code != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d: %s", recList.Code, recList.Body.String())
	}

	var gwList []*domain.GatewayItem
	if err := json.NewDecoder(recList.Body).Decode(&gwList); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if len(gwList) != 1 {
		t.Fatalf("expected 1 gateway item, got %d", len(gwList))
	}
	if gwList[0].ChannelRssiDbm == nil || *gwList[0].ChannelRssiDbm != -108 {
		t.Errorf("expected list gateway channel_rssi_dbm -108, got %v", gwList[0].ChannelRssiDbm)
	}
	if gwList[0].ChannelSampleContext == nil || *gwList[0].ChannelSampleContext != "RX_IDLE" {
		t.Errorf("expected list gateway channel_sample_context RX_IDLE, got %v", gwList[0].ChannelSampleContext)
	}
}

func TestMonitoringHandler_RFMetrics_CleanupOnDelete(t *testing.T) {
	authMap := map[string]api.Role{
		"token-admin": api.RoleAdmin,
	}
	staticAuth := api.NewStaticAuthenticator(authMap)

	store := newMockMonitoringStorage()
	store.gateways["gw01"] = &domain.GatewayStatusRecord{GatewayID: "gw01"}
	store.nodes = []domain.NodeSummary{
		{NodeID: 12, GatewayID: "gw01"},
	}

	tracker := presence.NewTracker()
	rfTracker := tracker.RF()
	chIdx := 2
	rfTracker.UpdateNodeRF("gw01", 12, -75, 4.5, &chIdx, "UP_EVENT", "VERIFIED", "550e8400-e29b-41d4-a716-446655440000", 10, 100, 0)
	rfTracker.UpdateChannelRF("gw01", 0, -105, "RX_IDLE", "550e8400-e29b-41d4-a716-446655440000", 11, 101, 0)

	handler := api.NewMonitoringHandler(store, 5*time.Minute, tracker, staticAuth)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// 1. Delete Node 12
	reqNodeDel := httptest.NewRequest(http.MethodDelete, "/api/v1/nodes/12", nil)
	reqNodeDel.Header.Set("Authorization", "Bearer token-admin")
	recNodeDel := httptest.NewRecorder()
	mux.ServeHTTP(recNodeDel, reqNodeDel)

	if recNodeDel.Code != http.StatusOK {
		t.Fatalf("expected node delete 200 OK, got %d: %s", recNodeDel.Code, recNodeDel.Body.String())
	}
	if view := rfTracker.GetNodeRFView("gw01", 12); view != nil {
		t.Fatalf("expected node 12 RF view to be purged after delete, got %+v", view)
	}

	// 2. Delete Gateway gw01
	reqGwDel := httptest.NewRequest(http.MethodDelete, "/api/v1/gateways/gw01", nil)
	reqGwDel.Header.Set("Authorization", "Bearer token-admin")
	recGwDel := httptest.NewRecorder()
	mux.ServeHTTP(recGwDel, reqGwDel)

	if recGwDel.Code != http.StatusOK {
		t.Fatalf("expected gateway delete 200 OK, got %d: %s", recGwDel.Code, recGwDel.Body.String())
	}
	if chView := rfTracker.GetChannelRFView("gw01", 0); chView != nil {
		t.Fatalf("expected gateway gw01 channel RF view to be purged after delete, got %+v", chView)
	}
}
