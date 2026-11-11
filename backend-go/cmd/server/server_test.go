package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

type mockServerStatusStorage struct{}

func (m *mockServerStatusStorage) UpsertGatewayStatus(ctx context.Context, status *domain.GatewayStatusRecord) error {
	return nil
}
func (m *mockServerStatusStorage) GetGatewayStatus(ctx context.Context, gatewayID string) (*domain.GatewayStatusRecord, error) {
	if gatewayID == "gw-01" {
		return &domain.GatewayStatusRecord{GatewayID: "gw-01", Mode: domain.GatewayModeActive}, nil
	}
	return nil, storage.ErrGatewayStatusNotFound
}
func (m *mockServerStatusStorage) ListGateways(ctx context.Context) ([]*domain.GatewayItem, error) {
	return []*domain.GatewayItem{{GatewayID: "gw-01", Name: "Gateway 1"}}, nil
}
func (m *mockServerStatusStorage) CreateGateway(ctx context.Context, gatewayID, name, location, ipAddress string) error {
	return nil
}
func (m *mockServerStatusStorage) ListNodes(ctx context.Context, filter domain.NodeFilter) (*domain.NodePage, error) {
	return &domain.NodePage{Items: []domain.NodeSummary{{NodeID: 1, GatewayID: "gw-01", Status: "ONLINE"}}}, nil
}

type mockServerChannelRepo struct{}

func (m *mockServerChannelRepo) GetChannel(ctx context.Context, channelID string) (*domain.RFChannel, error) {
	return nil, nil
}
func (m *mockServerChannelRepo) ListChannels(ctx context.Context, planVersion string) ([]domain.ChannelView, error) {
	return []domain.ChannelView{{ChannelID: "CH00", State: domain.StatusAvailable}}, nil
}
func (m *mockServerChannelRepo) GetActiveAllocationByGateway(ctx context.Context, gatewayID string) (*domain.ChannelAllocation, error) {
	return nil, domain.ErrAllocationNotFound
}
func (m *mockServerChannelRepo) GetActiveAllocationByChannel(ctx context.Context, channelID string) (*domain.ChannelAllocation, error) {
	return nil, domain.ErrAllocationNotFound
}
func (m *mockServerChannelRepo) AllocateChannel(ctx context.Context, req domain.AllocateRequest) (*domain.ChannelAllocation, error) {
	return nil, nil
}
func (m *mockServerChannelRepo) ReleaseChannel(ctx context.Context, req domain.ReleaseRequest) (*domain.ChannelAllocation, error) {
	return nil, nil
}
func (m *mockServerChannelRepo) ListActiveAllocations(ctx context.Context) ([]domain.ChannelAllocation, error) {
	return nil, nil
}

type mockServerAlertRepo struct{}

func (m *mockServerAlertRepo) ListAlerts(ctx context.Context, filter domain.AlertFilter) (*domain.AlertPage, error) {
	return &domain.AlertPage{Items: []domain.AlertView{}}, nil
}
func (m *mockServerAlertRepo) AcknowledgeAlert(ctx context.Context, alertID int64, acknowledgedBy string) (*domain.AlertView, error) {
	return nil, nil
}

type mockServerJoinRequestStorage struct{}

func (m *mockServerJoinRequestStorage) CreateOrUpdatePendingRequest(ctx context.Context, req *domain.DeviceJoinRequest) (*domain.DeviceJoinRequest, error) {
	return nil, nil
}
func (m *mockServerJoinRequestStorage) ListPendingRequests(ctx context.Context) ([]*domain.DeviceJoinRequest, error) {
	return []*domain.DeviceJoinRequest{}, nil
}
func (m *mockServerJoinRequestStorage) ApproveRequest(ctx context.Context, id int64, requestedNodeID *int) (*domain.DeviceJoinRequest, error) {
	return nil, nil
}
func (m *mockServerJoinRequestStorage) RejectRequest(ctx context.Context, id int64) error {
	return nil
}
func (m *mockServerJoinRequestStorage) IsDeviceRegistered(ctx context.Context, mac string) (bool, error) {
	return true, nil
}

func TestBuildServeMux_RouteRegistration(t *testing.T) {
	jwtSecret := "test-mvp-secret-key-minimum-32-bytes!!"
	jwtService, err := auth.NewJWTService([]byte(jwtSecret))
	if err != nil {
		t.Fatalf("failed to init jwtService: %v", err)
	}
	userRepo := auth.NewInMemoryUserRepository()
	ticketStore := auth.NewTicketStore()
	authService := auth.NewService(userRepo, jwtService, ticketStore)
	authHandler := auth.NewHandler(authService)

	jwtAuth := api.NewJWTAuthenticator(jwtService)
	provisionRepo := storage.NewMemoryProvisionStorage()
	masterKey := sha256.Sum256([]byte(jwtSecret + ":provision:master:key"))
	keyWrapper := api.NewAESGCMKeyWrapper(masterKey)
	provisionHandler := api.NewProvisionHandler(provisionRepo, keyWrapper, jwtAuth)
	nodeHandler := api.NewNodeHandler(nil)

	mux := BuildServeMux(nil, 5*time.Minute, nil, authHandler, nil, nil, provisionHandler, nil, nil, nodeHandler, jwtService)

	validToken, err := jwtService.GenerateToken(&auth.User{
		ID:       "u-test",
		Username: "operator",
		Role:     auth.RoleOperator,
		IsActive: true,
	}, time.Hour)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	// Health check - public route
	reqHealth := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	recHealth := httptest.NewRecorder()
	mux.ServeHTTP(recHealth, reqHealth)
	if recHealth.Code != http.StatusOK {
		t.Errorf("expected 200 for /healthz, got %d", recHealth.Code)
	}

	// Schedule endpoints must no longer be registered (return 404 with auth)
	reqSched := httptest.NewRequest(http.MethodGet, "/api/v1/gateways/gw01/schedules/1", nil)
	reqSched.Header.Set("Authorization", "Bearer "+validToken)
	recSched := httptest.NewRecorder()
	mux.ServeHTTP(recSched, reqSched)
	if recSched.Code != http.StatusNotFound {
		t.Errorf("expected 404 for removed schedule endpoint, got %d", recSched.Code)
	}

	// Schedule endpoints return 401 without auth
	reqSchedUnauth := httptest.NewRequest(http.MethodGet, "/api/v1/gateways/gw01/schedules/1", nil)
	recSchedUnauth := httptest.NewRecorder()
	mux.ServeHTTP(recSchedUnauth, reqSchedUnauth)
	if recSchedUnauth.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for unauthenticated removed schedule endpoint, got %d", recSchedUnauth.Code)
	}

	// Provision endpoint reachable (returns 401 when missing auth, NOT 404)
	reqProv := httptest.NewRequest(http.MethodPost, "/api/v1/devices/provision", nil)
	recProv := httptest.NewRecorder()
	mux.ServeHTTP(recProv, reqProv)
	if recProv.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for /api/v1/devices/provision without auth, got %d", recProv.Code)
	}

	// Telemetry endpoint returns 410 Gone with valid auth (Issue #303)
	reqTelem := httptest.NewRequest(http.MethodGet, "/api/v1/nodes/1/telemetry", nil)
	reqTelem.Header.Set("Authorization", "Bearer "+validToken)
	recTelem := httptest.NewRecorder()
	mux.ServeHTTP(recTelem, reqTelem)
	if recTelem.Code != http.StatusGone {
		t.Errorf("expected 410 for /api/v1/nodes/1/telemetry, got %d", recTelem.Code)
	}

	var telemResp api.DeprecatedTelemetryResponseDTO
	if err := json.Unmarshal(recTelem.Body.Bytes(), &telemResp); err != nil {
		t.Fatalf("failed to decode telemetry response: %v", err)
	}
	if telemResp.Code != "TELEMETRY_PERIODIC_MODE_DEPRECATED" {
		t.Errorf("expected TELEMETRY_PERIODIC_MODE_DEPRECATED, got %s", telemResp.Code)
	}
	expectedMsg := "Periodic application telemetry and SET_PERIODIC_MODE cease as current business flows. Event-Only V2 alerts arrive via ALERT_TRIGGERED."
	if telemResp.Message != expectedMsg {
		t.Errorf("expected message %q, got %q", expectedMsg, telemResp.Message)
	}
}

func TestBuildServeMux_CoexistenceWithMonitoringHandler(t *testing.T) {
	jwtSecret := "test-mvp-secret-key-minimum-32-bytes!!"
	jwtService, err := auth.NewJWTService([]byte(jwtSecret))
	if err != nil {
		t.Fatalf("failed to init jwtService: %v", err)
	}
	userRepo := auth.NewInMemoryUserRepository()
	ticketStore := auth.NewTicketStore()
	authService := auth.NewService(userRepo, jwtService, ticketStore)
	authHandler := auth.NewHandler(authService)

	jwtAuth := api.NewJWTAuthenticator(jwtService)
	provisionRepo := storage.NewMemoryProvisionStorage()
	masterKey := sha256.Sum256([]byte(jwtSecret + ":provision:master:key"))
	keyWrapper := api.NewAESGCMKeyWrapper(masterKey)
	provisionHandler := api.NewProvisionHandler(provisionRepo, keyWrapper, jwtAuth)
	nodeHandler := api.NewNodeHandler(nil)
	statusStore := &mockServerStatusStorage{}

	// Both MonitoringHandler and NodeHandler must register without panic or route collision
	mux := BuildServeMux(statusStore, 5*time.Minute, nil, authHandler, nil, nil, provisionHandler, nil, nil, nodeHandler, jwtService)

	validToken, err := jwtService.GenerateToken(&auth.User{
		ID:       "u-test",
		Username: "operator",
		Role:     auth.RoleOperator,
		IsActive: true,
	}, time.Hour)
	if err != nil {
		t.Fatalf("failed to generate token: %v", err)
	}

	// GET /api/v1/nodes without auth returns 401 Unauthorized (Issue #311)
	reqNodesUnauth := httptest.NewRequest(http.MethodGet, "/api/v1/nodes", nil)
	recNodesUnauth := httptest.NewRecorder()
	mux.ServeHTTP(recNodesUnauth, reqNodesUnauth)
	if recNodesUnauth.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for /api/v1/nodes without auth, got %d", recNodesUnauth.Code)
	}

	// GET /api/v1/nodes with valid auth handled by MonitoringHandler -> 200 OK
	reqNodes := httptest.NewRequest(http.MethodGet, "/api/v1/nodes", nil)
	reqNodes.Header.Set("Authorization", "Bearer "+validToken)
	recNodes := httptest.NewRecorder()
	mux.ServeHTTP(recNodes, reqNodes)
	if recNodes.Code != http.StatusOK {
		t.Errorf("expected 200 for /api/v1/nodes via MonitoringHandler, got %d", recNodes.Code)
	}

	// GET /api/v1/nodes/1/telemetry handled by NodeHandler -> 410 Gone (with auth)
	reqTelem := httptest.NewRequest(http.MethodGet, "/api/v1/nodes/1/telemetry", nil)
	reqTelem.Header.Set("Authorization", "Bearer "+validToken)
	recTelem := httptest.NewRecorder()
	mux.ServeHTTP(recTelem, reqTelem)
	if recTelem.Code != http.StatusGone {
		t.Errorf("expected 410 for /api/v1/nodes/1/telemetry via NodeHandler, got %d", recTelem.Code)
	}

	// GET /api/v1/nodes/999/telemetry handled by NodeHandler -> 422 Unprocessable Entity (with auth)
	reqInvalid := httptest.NewRequest(http.MethodGet, "/api/v1/nodes/999/telemetry", nil)
	reqInvalid.Header.Set("Authorization", "Bearer "+validToken)
	recInvalid := httptest.NewRecorder()
	mux.ServeHTTP(recInvalid, reqInvalid)
	if recInvalid.Code != http.StatusUnprocessableEntity {
		t.Errorf("expected 422 for /api/v1/nodes/999/telemetry, got %d", recInvalid.Code)
	}
}

func TestBuildServeMux_EnforceBearerAuth_AllReadEndpoints(t *testing.T) {
	jwtSecret := "test-mvp-secret-key-minimum-32-bytes!!"
	jwtService, err := auth.NewJWTService([]byte(jwtSecret))
	if err != nil {
		t.Fatalf("failed to init jwtService: %v", err)
	}
	userRepo := auth.NewInMemoryUserRepository()
	if err := auth.SeedDefaultUsers(context.Background(), userRepo); err != nil {
		t.Fatalf("failed to seed default users: %v", err)
	}
	ticketStore := auth.NewTicketStore()
	authService := auth.NewService(userRepo, jwtService, ticketStore)
	authHandler := auth.NewHandler(authService)

	jwtAuth := api.NewJWTAuthenticator(jwtService)
	provisionRepo := storage.NewMemoryProvisionStorage()
	masterKey := sha256.Sum256([]byte(jwtSecret + ":provision:master:key"))
	keyWrapper := api.NewAESGCMKeyWrapper(masterKey)
	provisionHandler := api.NewProvisionHandler(provisionRepo, keyWrapper, jwtAuth)
	nodeHandler := api.NewNodeHandler(nil)
	statusStore := &mockServerStatusStorage{}
	channelRepo := &mockServerChannelRepo{}
	channelHandler := api.NewChannelHandler(channelRepo, jwtAuth)
	alertRepo := &mockServerAlertRepo{}
	alertHandler := api.NewAlertHandler(alertRepo, jwtAuth)
	joinReqStore := &mockServerJoinRequestStorage{}
	joinReqHandler := api.NewJoinRequestHandler(joinReqStore, nil, jwtAuth)

	mux := BuildServeMux(
		statusStore,
		5*time.Minute,
		nil,
		authHandler,
		channelHandler,
		alertHandler,
		provisionHandler,
		joinReqHandler,
		nil,
		nodeHandler,
		jwtService,
		jwtAuth,
	)

	validToken, err := jwtService.GenerateToken(&auth.User{
		ID:       "u-viewer-01",
		Username: "viewer01",
		Role:     auth.RoleViewer,
		IsActive: true,
	}, time.Hour)
	if err != nil {
		t.Fatalf("failed to generate valid token: %v", err)
	}

	expiredToken, err := jwtService.GenerateToken(&auth.User{
		ID:       "u-expired",
		Username: "expired",
		Role:     auth.RoleViewer,
		IsActive: true,
	}, -time.Hour)
	if err != nil {
		t.Fatalf("failed to generate expired token: %v", err)
	}

	readEndpoints := []struct {
		name string
		path string
	}{
		{name: "Gateways list", path: "/api/v1/gateways"},
		{name: "Gateway status", path: "/api/v1/gateways/gw-01/status"},
		{name: "Nodes list", path: "/api/v1/nodes"},
		{name: "Alerts list", path: "/api/v1/alerts"},
		{name: "Channels list", path: "/api/v1/channels"},
		{name: "Join requests list", path: "/api/v1/devices/requests"},
	}

	for _, ep := range readEndpoints {
		t.Run(ep.name+"_MissingToken", func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, ep.path, nil)
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != http.StatusUnauthorized {
				t.Fatalf("expected 401 Unauthorized, got %d", rec.Code)
			}
			wwwAuth := rec.Header().Get("WWW-Authenticate")
			if wwwAuth != `Bearer error="invalid_token"` {
				t.Errorf("expected WWW-Authenticate header 'Bearer error=\"invalid_token\"', got %q", wwwAuth)
			}

			var body map[string]string
			if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
				t.Fatalf("failed to parse json response: %v", err)
			}
			if body["error"] != "UNAUTHORIZED" {
				t.Errorf("expected error UNAUTHORIZED, got %q", body["error"])
			}
			if body["message"] != "missing or malformed bearer token" {
				t.Errorf("expected message 'missing or malformed bearer token', got %q", body["message"])
			}
		})

		t.Run(ep.name+"_MalformedTokenPrefix", func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, ep.path, nil)
			req.Header.Set("Authorization", "Basic "+validToken)
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != http.StatusUnauthorized {
				t.Fatalf("expected 401 Unauthorized, got %d", rec.Code)
			}
			wwwAuth := rec.Header().Get("WWW-Authenticate")
			if wwwAuth != `Bearer error="invalid_token"` {
				t.Errorf("expected WWW-Authenticate header 'Bearer error=\"invalid_token\"', got %q", wwwAuth)
			}

			var body map[string]string
			if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
				t.Fatalf("failed to parse json response: %v", err)
			}
			if body["error"] != "UNAUTHORIZED" {
				t.Errorf("expected error UNAUTHORIZED, got %q", body["error"])
			}
			if body["message"] != "missing or malformed bearer token" {
				t.Errorf("expected message 'missing or malformed bearer token', got %q", body["message"])
			}
		})

		t.Run(ep.name+"_EmptyToken", func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, ep.path, nil)
			req.Header.Set("Authorization", "Bearer ")
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != http.StatusUnauthorized {
				t.Fatalf("expected 401 Unauthorized, got %d", rec.Code)
			}
			wwwAuth := rec.Header().Get("WWW-Authenticate")
			if wwwAuth != `Bearer error="invalid_token"` {
				t.Errorf("expected WWW-Authenticate header 'Bearer error=\"invalid_token\"', got %q", wwwAuth)
			}
		})

		t.Run(ep.name+"_ExpiredToken", func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, ep.path, nil)
			req.Header.Set("Authorization", "Bearer "+expiredToken)
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != http.StatusUnauthorized {
				t.Fatalf("expected 401 Unauthorized, got %d", rec.Code)
			}
			wwwAuth := rec.Header().Get("WWW-Authenticate")
			if wwwAuth != `Bearer error="invalid_token"` {
				t.Errorf("expected WWW-Authenticate header 'Bearer error=\"invalid_token\"', got %q", wwwAuth)
			}

			var body map[string]string
			if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
				t.Fatalf("failed to parse json response: %v", err)
			}
			if body["error"] != "UNAUTHORIZED" {
				t.Errorf("expected error UNAUTHORIZED, got %q", body["error"])
			}
			if body["message"] != "invalid or expired token" {
				t.Errorf("expected message 'invalid or expired token', got %q", body["message"])
			}
		})

		t.Run(ep.name+"_ValidToken", func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, ep.path, nil)
			req.Header.Set("Authorization", "Bearer "+validToken)
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != http.StatusOK {
				t.Fatalf("expected 200 OK for %s with valid token, got %d (body: %s)", ep.path, rec.Code, rec.Body.String())
			}
		})
	}

	// Verify Public Routes continue to work without auth
	t.Run("Public_Healthz", func(t *testing.T) {
		req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Errorf("expected 200 for /healthz without auth, got %d", rec.Code)
		}
	})

	t.Run("Public_AuthLogin", func(t *testing.T) {
		loginPayload := `{"username":"operator01","password":"operator"}`
		req := httptest.NewRequest(http.MethodPost, "/api/v1/auth/login", strings.NewReader(loginPayload))
		req.Header.Set("Content-Type", "application/json")
		rec := httptest.NewRecorder()
		mux.ServeHTTP(rec, req)

		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200 for /api/v1/auth/login without auth, got %d (body: %s)", rec.Code, rec.Body.String())
		}
		var loginResp map[string]interface{}
		if err := json.Unmarshal(rec.Body.Bytes(), &loginResp); err != nil {
			t.Fatalf("failed to parse login response: %v", err)
		}
		if loginResp["access_token"] == nil || loginResp["access_token"] == "" {
			t.Errorf("expected access_token in login response, got %+v", loginResp)
		}
	})
}
