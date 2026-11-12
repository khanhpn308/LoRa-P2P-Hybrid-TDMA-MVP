package api_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockJoinRequestStorage struct {
	requests map[int64]*domain.DeviceJoinRequest
}

func newMockJoinRequestStorage() *mockJoinRequestStorage {
	nodeID := 10
	now := time.Now().UTC()
	return &mockJoinRequestStorage{
		requests: map[int64]*domain.DeviceJoinRequest{
			1: {
				ID:             1,
				DeviceMAC:      "001122334455",
				GatewayID:      "gw01",
				Status:         "PENDING",
				AssignedNodeID: &nodeID,
				CreatedAt:      now,
				UpdatedAt:      now,
			},
		},
	}
}

func (m *mockJoinRequestStorage) CreateOrUpdatePendingRequest(ctx context.Context, req *domain.DeviceJoinRequest) (*domain.DeviceJoinRequest, error) {
	return req, nil
}

func (m *mockJoinRequestStorage) ListPendingRequests(ctx context.Context) ([]*domain.DeviceJoinRequest, error) {
	var list []*domain.DeviceJoinRequest
	for _, req := range m.requests {
		if req.Status == "PENDING" {
			list = append(list, req)
		}
	}
	return list, nil
}

func (m *mockJoinRequestStorage) ApproveRequest(ctx context.Context, id int64, requestedNodeID *int) (*domain.DeviceJoinRequest, error) {
	req, ok := m.requests[id]
	if !ok {
		return nil, storage.ErrRequestNotFound
	}
	if id == 99 {
		return nil, storage.ErrNoAvailableNodeID
	}
	req.Status = "APPROVED"
	if requestedNodeID != nil {
		req.AssignedNodeID = requestedNodeID
	}
	return req, nil
}

func (m *mockJoinRequestStorage) RejectRequestWithDetails(ctx context.Context, id int64) (*domain.DeviceJoinRequest, error) {
	req, ok := m.requests[id]
	if !ok {
		return nil, storage.ErrRequestNotFound
	}
	req.Status = "REJECTED"
	return req, nil
}

func (m *mockJoinRequestStorage) RejectRequest(ctx context.Context, id int64) error {
	_, err := m.RejectRequestWithDetails(ctx, id)
	return err
}

func (m *mockJoinRequestStorage) IsDeviceRegistered(ctx context.Context, mac string) (bool, error) {
	return true, nil
}

type mockDownlinkPublisher struct {
	published []string
}

func (p *mockDownlinkPublisher) PublishJoinGrant(ctx context.Context, gatewayID string, deviceMAC string, nodeID int) error {
	p.published = append(p.published, gatewayID+":"+deviceMAC)
	return nil
}

func (p *mockDownlinkPublisher) PublishNodeRevoke(ctx context.Context, gatewayID string, nodeID int) error {
	p.published = append(p.published, "REVOKE:"+gatewayID+":"+strconv.Itoa(nodeID))
	return nil
}

func (p *mockDownlinkPublisher) PublishJoinWait(ctx context.Context, gatewayID string, deviceMAC string) error {
	p.published = append(p.published, "WAIT:"+gatewayID+":"+deviceMAC)
	return nil
}

func (p *mockDownlinkPublisher) PublishJoinReject(ctx context.Context, gatewayID string, deviceMAC string) error {
	p.published = append(p.published, "REJECT:"+gatewayID+":"+deviceMAC)
	return nil
}

func TestJoinRequestHandler_RBAC_Table(t *testing.T) {
	store := newMockJoinRequestStorage()
	pub := &mockDownlinkPublisher{}
	auth := api.NewStaticAuthenticator(map[string]api.Role{
		"viewer-tok":   api.RoleViewer,
		"operator-tok": api.RoleOperator,
		"admin-tok":    api.RoleAdmin,
	})

	handler := api.NewJoinRequestHandler(store, pub, auth)
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	tests := []struct {
		name       string
		method     string
		path       string
		body       string
		authHeader string
		wantCode   int
	}{
		// GET /api/v1/devices/requests
		{
			name:       "GET requests missing token -> 401",
			method:     http.MethodGet,
			path:       "/api/v1/devices/requests",
			authHeader: "",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "GET requests empty bearer token -> 401",
			method:     http.MethodGet,
			path:       "/api/v1/devices/requests",
			authHeader: "Bearer ",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "GET requests invalid token -> 401",
			method:     http.MethodGet,
			path:       "/api/v1/devices/requests",
			authHeader: "Bearer invalid-tok",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "GET requests VIEWER token -> 200 OK",
			method:     http.MethodGet,
			path:       "/api/v1/devices/requests",
			authHeader: "Bearer viewer-tok",
			wantCode:   http.StatusOK,
		},
		{
			name:       "GET requests OPERATOR token -> 200 OK",
			method:     http.MethodGet,
			path:       "/api/v1/devices/requests",
			authHeader: "Bearer operator-tok",
			wantCode:   http.StatusOK,
		},
		{
			name:       "GET requests ADMIN token -> 200 OK",
			method:     http.MethodGet,
			path:       "/api/v1/devices/requests",
			authHeader: "Bearer admin-tok",
			wantCode:   http.StatusOK,
		},

		// POST /api/v1/devices/requests/{id}/approve
		{
			name:       "POST approve missing token -> 401",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/approve",
			authHeader: "",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "POST approve empty bearer token -> 401",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/approve",
			authHeader: "Bearer ",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "POST approve invalid token -> 401",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/approve",
			authHeader: "Bearer invalid-tok",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "POST approve VIEWER token -> 403 Forbidden",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/approve",
			authHeader: "Bearer viewer-tok",
			wantCode:   http.StatusForbidden,
		},
		{
			name:       "POST approve OPERATOR token -> 200 OK",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/approve",
			authHeader: "Bearer operator-tok",
			wantCode:   http.StatusOK,
		},
		{
			name:       "POST approve ADMIN token -> 200 OK",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/approve",
			authHeader: "Bearer admin-tok",
			wantCode:   http.StatusOK,
		},

		// POST /api/v1/devices/requests/{id}/reject
		{
			name:       "POST reject missing token -> 401",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/reject",
			authHeader: "",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "POST reject empty bearer token -> 401",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/reject",
			authHeader: "Bearer ",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "POST reject invalid token -> 401",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/reject",
			authHeader: "Bearer invalid-tok",
			wantCode:   http.StatusUnauthorized,
		},
		{
			name:       "POST reject VIEWER token -> 403 Forbidden",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/reject",
			authHeader: "Bearer viewer-tok",
			wantCode:   http.StatusForbidden,
		},
		{
			name:       "POST reject OPERATOR token -> 200 OK",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/reject",
			authHeader: "Bearer operator-tok",
			wantCode:   http.StatusOK,
		},
		{
			name:       "POST reject ADMIN token -> 200 OK",
			method:     http.MethodPost,
			path:       "/api/v1/devices/requests/1/reject",
			authHeader: "Bearer admin-tok",
			wantCode:   http.StatusOK,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			var bodyReader = strings.NewReader(tc.body)
			req := httptest.NewRequest(tc.method, tc.path, bodyReader)
			if tc.authHeader != "" {
				req.Header.Set("Authorization", tc.authHeader)
			}
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != tc.wantCode {
				t.Fatalf("expected status %d, got %d (body: %s)", tc.wantCode, rec.Code, rec.Body.String())
			}
		})
	}

	t.Run("unconfigured authenticator returns 500 INTERNAL_ERROR", func(t *testing.T) {
		unconf := api.NewJoinRequestHandler(store, pub)
		unconfMux := http.NewServeMux()
		unconf.RegisterRoutes(unconfMux)

		reqGet := httptest.NewRequest(http.MethodGet, "/api/v1/devices/requests", nil)
		recGet := httptest.NewRecorder()
		unconfMux.ServeHTTP(recGet, reqGet)
		if recGet.Code != http.StatusInternalServerError {
			t.Errorf("expected 500 for unconfigured handler on GET, got %d", recGet.Code)
		}

		reqApprove := httptest.NewRequest(http.MethodPost, "/api/v1/devices/requests/1/approve", nil)
		recApprove := httptest.NewRecorder()
		unconfMux.ServeHTTP(recApprove, reqApprove)
		if recApprove.Code != http.StatusInternalServerError {
			t.Errorf("expected 500 for unconfigured handler on POST approve, got %d", recApprove.Code)
		}

		reqReject := httptest.NewRequest(http.MethodPost, "/api/v1/devices/requests/1/reject", nil)
		recReject := httptest.NewRecorder()
		unconfMux.ServeHTTP(recReject, reqReject)
		if recReject.Code != http.StatusInternalServerError {
			t.Errorf("expected 500 for unconfigured handler on POST reject, got %d", recReject.Code)
		}
	})

	t.Run("functional: approve not found returns 404", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/devices/requests/999/approve", nil)
		req.Header.Set("Authorization", "Bearer admin-tok")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)
		if rec.Code != http.StatusNotFound {
			t.Errorf("expected 404, got %d", rec.Code)
		}
	})

	t.Run("functional: approve capacity exceeded returns 409", func(t *testing.T) {
		store.requests[99] = &domain.DeviceJoinRequest{ID: 99, Status: "PENDING"}
		req := httptest.NewRequest(http.MethodPost, "/api/v1/devices/requests/99/approve", nil)
		req.Header.Set("Authorization", "Bearer admin-tok")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)
		if rec.Code != http.StatusConflict {
			t.Errorf("expected 409, got %d", rec.Code)
		}
	})

	t.Run("functional: reject not found returns 404", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodPost, "/api/v1/devices/requests/999/reject", nil)
		req.Header.Set("Authorization", "Bearer admin-tok")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)
		if rec.Code != http.StatusNotFound {
			t.Errorf("expected 404, got %d", rec.Code)
		}
	})

	t.Run("functional: invalid request ID returns 400", func(t *testing.T) {
		reqApprove := httptest.NewRequest(http.MethodPost, "/api/v1/devices/requests/abc/approve", nil)
		reqApprove.Header.Set("Authorization", "Bearer admin-tok")
		recApprove := httptest.NewRecorder()
		mux.ServeHTTP(recApprove, reqApprove)
		if recApprove.Code != http.StatusBadRequest {
			t.Errorf("expected 400 for non-numeric ID on approve, got %d", recApprove.Code)
		}

		reqReject := httptest.NewRequest(http.MethodPost, "/api/v1/devices/requests/-5/reject", nil)
		reqReject.Header.Set("Authorization", "Bearer admin-tok")
		recReject := httptest.NewRecorder()
		mux.ServeHTTP(recReject, reqReject)
		if recReject.Code != http.StatusBadRequest {
			t.Errorf("expected 400 for negative ID on reject, got %d", recReject.Code)
		}
	})

	t.Run("functional: reject publishes downlink join-reject", func(t *testing.T) {
		store.requests[2] = &domain.DeviceJoinRequest{
			ID:        2,
			DeviceMAC: "aabbccddeeff",
			GatewayID: "gw-test-02",
			Status:    "PENDING",
		}
		pub.published = nil

		req := httptest.NewRequest(http.MethodPost, "/api/v1/devices/requests/2/reject", nil)
		req.Header.Set("Authorization", "Bearer admin-tok")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 OK, got %d (body: %s)", rec.Code, rec.Body.String())
		}

		if len(pub.published) == 0 {
			t.Fatal("expected downlink publish on reject, got none")
		}
		expected := "REJECT:gw-test-02:aabbccddeeff"
		var found bool
		for _, p := range pub.published {
			if p == expected {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("expected downlink %q, got: %+v", expected, pub.published)
		}

		if store.requests[2].Status != "REJECTED" {
			t.Fatalf("expected status REJECTED, got %s", store.requests[2].Status)
		}
	})
}
