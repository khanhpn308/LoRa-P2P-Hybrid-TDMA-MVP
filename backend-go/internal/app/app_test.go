package app_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/app"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/config"
)

func TestApp_New_InMemoryDefaults(t *testing.T) {
	cfg := config.LoadFromEnv(func(key string) string {
		if key == "PORT" {
			return "0" // pick random port
		}
		return ""
	})

	application, err := app.New(cfg)
	if err != nil {
		t.Fatalf("failed to initialize App: %v", err)
	}

	if application == nil {
		t.Fatal("expected non-nil application")
	}

	if application.Config() != cfg {
		t.Errorf("expected application config to match")
	}

	if application.Server() == nil {
		t.Errorf("expected non-nil http.Server")
	}

	if application.Hub() == nil {
		t.Errorf("expected non-nil Hub")
	}

	// Verify health check route is served via the configured server handler
	srv := application.Server()
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rec := httptest.NewRecorder()
	srv.Handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Errorf("expected 200 for /healthz, got %d", rec.Code)
	}
}

func TestApp_Run_GracefulShutdown(t *testing.T) {
	cfg := config.LoadFromEnv(func(key string) string {
		if key == "PORT" {
			return "0"
		}
		return ""
	})
	cfg.ShutdownTimeout = 500 * time.Millisecond

	application, err := app.New(cfg)
	if err != nil {
		t.Fatalf("failed to initialize app: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())

	errCh := make(chan error, 1)
	go func() {
		errCh <- application.Run(ctx)
	}()

	// Allow server goroutine to start
	time.Sleep(50 * time.Millisecond)

	// Trigger graceful shutdown
	cancel()

	select {
	case err := <-errCh:
		if err != nil {
			t.Errorf("expected clean shutdown, got error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("application.Run did not terminate within timeout")
	}
}
