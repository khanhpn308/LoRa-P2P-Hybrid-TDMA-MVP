package main

import (
	"crypto/sha256"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage"
)

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

	mux := BuildServeMux(nil, 5*time.Minute, nil, nil, authHandler, nil, nil, provisionHandler, nil, nil)

	// Health check
	reqHealth := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	recHealth := httptest.NewRecorder()
	mux.ServeHTTP(recHealth, reqHealth)
	if recHealth.Code != http.StatusOK {
		t.Errorf("expected 200 for /healthz, got %d", recHealth.Code)
	}

	// Provision endpoint reachable (returns 401 when missing auth, NOT 404)
	reqProv := httptest.NewRequest(http.MethodPost, "/api/v1/devices/provision", nil)
	recProv := httptest.NewRecorder()
	mux.ServeHTTP(recProv, reqProv)
	if recProv.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for /api/v1/devices/provision without auth, got %d", recProv.Code)
	}
}
