package api_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func TestCORSMiddleware_HeadersAndPreflight(t *testing.T) {
	downstreamCalled := false
	handler := api.CORSMiddleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		downstreamCalled = true
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))

	// Test normal GET request
	req := httptest.NewRequest(http.MethodGet, "/test", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if !downstreamCalled {
		t.Errorf("expected downstream handler to be called for GET")
	}
	if rec.Header().Get("Access-Control-Allow-Origin") != "*" {
		t.Errorf("expected Access-Control-Allow-Origin: *, got %q", rec.Header().Get("Access-Control-Allow-Origin"))
	}
	if rec.Header().Get("Access-Control-Allow-Methods") != "GET, POST, PUT, PATCH, DELETE, OPTIONS" {
		t.Errorf("expected Access-Control-Allow-Methods header, got %q", rec.Header().Get("Access-Control-Allow-Methods"))
	}
	if rec.Header().Get("Access-Control-Allow-Headers") != "Content-Type, Authorization, X-Requested-With, X-Idempotency-Key" {
		t.Errorf("expected Access-Control-Allow-Headers header, got %q", rec.Header().Get("Access-Control-Allow-Headers"))
	}

	// Test OPTIONS preflight
	downstreamCalled = false
	reqOpt := httptest.NewRequest(http.MethodOptions, "/test", nil)
	recOpt := httptest.NewRecorder()
	handler.ServeHTTP(recOpt, reqOpt)

	if downstreamCalled {
		t.Errorf("downstream handler MUST NOT be called for OPTIONS preflight")
	}
	if recOpt.Code != http.StatusNoContent {
		t.Errorf("expected 204 No Content for OPTIONS preflight, got %d", recOpt.Code)
	}
}

func TestBuildServeMux_NilDependencies_HealthCheck(t *testing.T) {
	mux := api.BuildServeMux(nil, 5*time.Minute, nil, nil, nil, nil, nil, nil, nil, nil, nil)
	if mux == nil {
		t.Fatal("expected non-nil ServeMux")
	}

	// /healthz should work even with all optional dependencies nil
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("expected 200 OK for /healthz, got %d", rec.Code)
	}

	// Unauthenticated request under /api/v1/ with nil jwtService returns 401 Unauthorized
	reqAPI := httptest.NewRequest(http.MethodGet, "/api/v1/gateways", nil)
	recAPI := httptest.NewRecorder()
	mux.ServeHTTP(recAPI, reqAPI)

	if recAPI.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for /api/v1/gateways, got %d", recAPI.Code)
	}
	if recAPI.Header().Get("WWW-Authenticate") != `Bearer error="invalid_token"` {
		t.Errorf("expected WWW-Authenticate header, got %q", recAPI.Header().Get("WWW-Authenticate"))
	}

	var errResp map[string]string
	if err := json.Unmarshal(recAPI.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}
	if errResp["error"] != "UNAUTHORIZED" {
		t.Errorf("expected error UNAUTHORIZED, got %q", errResp["error"])
	}

	// Preflight OPTIONS on /api/v1/ returns 204
	reqPreflight := httptest.NewRequest(http.MethodOptions, "/api/v1/gateways", nil)
	recPreflight := httptest.NewRecorder()
	mux.ServeHTTP(recPreflight, reqPreflight)

	if recPreflight.Code != http.StatusNoContent {
		t.Errorf("expected 204 for OPTIONS /api/v1/gateways, got %d", recPreflight.Code)
	}
}

func TestBuildServeMux_JWTAuthenticatorExtraction(t *testing.T) {
	jwtSecret := "test-secret-key-minimum-32-bytes!!"
	jwtService, err := auth.NewJWTService([]byte(jwtSecret))
	if err != nil {
		t.Fatalf("failed to create JWT service: %v", err)
	}

	jwtAuth := api.NewJWTAuthenticator(jwtService)
	// Pass nil jwtService but pass jwtAuth in authenticators slice -> should extract jwtService
	mux := api.BuildServeMux(nil, 5*time.Minute, nil, nil, nil, nil, nil, nil, nil, nil, nil, jwtAuth)
	if mux == nil {
		t.Fatal("expected non-nil ServeMux")
	}

	// OPTIONS preflight on /api/v1/ should succeed
	reqPreflight := httptest.NewRequest(http.MethodOptions, "/api/v1/test", nil)
	recPreflight := httptest.NewRecorder()
	mux.ServeHTTP(recPreflight, reqPreflight)
	if recPreflight.Code != http.StatusNoContent {
		t.Errorf("expected 204 for OPTIONS, got %d", recPreflight.Code)
	}
}
