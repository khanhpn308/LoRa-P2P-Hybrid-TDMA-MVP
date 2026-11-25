package api_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
)

func TestHealthHandler_HealthEndpoints(t *testing.T) {
	handler := api.NewHealthHandler()
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	paths := []string{"/healthz", "/api/v1/health"}
	for _, path := range paths {
		t.Run("GET "+path, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, path, nil)
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != http.StatusOK {
				t.Fatalf("GET %s: expected 200 OK, got: %d", path, rec.Code)
			}

			if gotCT := rec.Header().Get("Content-Type"); gotCT != "application/json; charset=utf-8" {
				t.Fatalf("GET %s: expected Content-Type application/json; charset=utf-8, got: %q", path, gotCT)
			}

			var resp api.HealthResponseDTO
			if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
				t.Fatalf("GET %s: failed to parse response: %v", path, err)
			}

			if resp.Status != "ok" {
				t.Fatalf("GET %s: expected status=ok, got: %s", path, resp.Status)
			}
		})

		t.Run("POST "+path+" method not allowed", func(t *testing.T) {
			req := httptest.NewRequest(http.MethodPost, path, nil)
			rec := httptest.NewRecorder()
			mux.ServeHTTP(rec, req)

			if rec.Code != http.StatusMethodNotAllowed {
				t.Fatalf("POST %s: expected 405 Method Not Allowed, got: %d", path, rec.Code)
			}
		})
	}
}
