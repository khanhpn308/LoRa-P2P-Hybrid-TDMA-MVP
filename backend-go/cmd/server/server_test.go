package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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
	return nil, storage.ErrGatewayStatusNotFound
}
func (m *mockServerStatusStorage) ListGateways(ctx context.Context) ([]*domain.GatewayItem, error) {
	return []*domain.GatewayItem{}, nil
}
func (m *mockServerStatusStorage) CreateGateway(ctx context.Context, gatewayID, name, location, ipAddress string) error {
	return nil
}
func (m *mockServerStatusStorage) ListNodes(ctx context.Context, filter domain.NodeFilter) (*domain.NodePage, error) {
	return &domain.NodePage{Items: []domain.NodeSummary{}}, nil
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

	mux := BuildServeMux(nil, 5*time.Minute, nil, authHandler, nil, nil, provisionHandler, nil, nil, nodeHandler)

	// Health check
	reqHealth := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	recHealth := httptest.NewRecorder()
	mux.ServeHTTP(recHealth, reqHealth)
	if recHealth.Code != http.StatusOK {
		t.Errorf("expected 200 for /healthz, got %d", recHealth.Code)
	}

	// Schedule endpoints must no longer be registered (return 404)
	reqSched := httptest.NewRequest(http.MethodGet, "/api/v1/gateways/gw01/schedules/1", nil)
	recSched := httptest.NewRecorder()
	mux.ServeHTTP(recSched, reqSched)
	if recSched.Code != http.StatusNotFound {
		t.Errorf("expected 404 for removed schedule endpoint, got %d", recSched.Code)
	}

	// Provision endpoint reachable (returns 401 when missing auth, NOT 404)
	reqProv := httptest.NewRequest(http.MethodPost, "/api/v1/devices/provision", nil)
	recProv := httptest.NewRecorder()
	mux.ServeHTTP(recProv, reqProv)
	if recProv.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for /api/v1/devices/provision without auth, got %d", recProv.Code)
	}

	// Telemetry endpoint returns 410 Gone (Issue #303)
	reqTelem := httptest.NewRequest(http.MethodGet, "/api/v1/nodes/1/telemetry", nil)
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
	mux := BuildServeMux(statusStore, 5*time.Minute, nil, authHandler, nil, nil, provisionHandler, nil, nil, nodeHandler)

	// GET /api/v1/nodes handled by MonitoringHandler
	reqNodes := httptest.NewRequest(http.MethodGet, "/api/v1/nodes", nil)
	recNodes := httptest.NewRecorder()
	mux.ServeHTTP(recNodes, reqNodes)
	if recNodes.Code != http.StatusOK {
		t.Errorf("expected 200 for /api/v1/nodes via MonitoringHandler, got %d", recNodes.Code)
	}

	// GET /api/v1/nodes/1/telemetry handled by NodeHandler -> 410 Gone
	reqTelem := httptest.NewRequest(http.MethodGet, "/api/v1/nodes/1/telemetry", nil)
	recTelem := httptest.NewRecorder()
	mux.ServeHTTP(recTelem, reqTelem)
	if recTelem.Code != http.StatusGone {
		t.Errorf("expected 410 for /api/v1/nodes/1/telemetry via NodeHandler, got %d", recTelem.Code)
	}

	// GET /api/v1/nodes/999/telemetry handled by NodeHandler -> 422 Unprocessable Entity
	reqInvalid := httptest.NewRequest(http.MethodGet, "/api/v1/nodes/999/telemetry", nil)
	recInvalid := httptest.NewRecorder()
	mux.ServeHTTP(recInvalid, reqInvalid)
	if recInvalid.Code != http.StatusUnprocessableEntity {
		t.Errorf("expected 422 for /api/v1/nodes/999/telemetry, got %d", recInvalid.Code)
	}
}
