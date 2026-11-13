package app_test

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
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

	if application.StatusSub() != nil {
		t.Errorf("expected nil StatusSub in default in-memory mode")
	}

	if application.DB() != nil {
		t.Errorf("expected nil DB in default in-memory mode")
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

func TestApp_New_NoPrematureDNSOrSubscriber(t *testing.T) {
	dnsCalled := false
	dnsLookup := func(host string) ([]string, error) {
		dnsCalled = true
		return []string{"192.168.1.50"}, nil
	}

	cfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "PORT":
			return "0"
		case "MQTT_HOST":
			return "mqtt-dev"
		default:
			return ""
		}
	}, dnsLookup)

	// In in-memory mode (empty DATABASE_URL), statusStore is nil.
	// app.New MUST NOT resolve MQTT host via DNS or instantiate/start statusSub.
	application, err := app.New(cfg)
	if err != nil {
		t.Fatalf("failed to initialize app: %v", err)
	}

	if dnsCalled {
		t.Errorf("app.New MUST NOT trigger DNS lookup when statusStore is nil")
	}
	if application.StatusSub() != nil {
		t.Errorf("expected nil statusSub when statusStore is nil, got %v", application.StatusSub())
	}
}

func TestApp_New_PersistentMode_SubscriberInitialized(t *testing.T) {
	dnsCalled := false
	dnsLookup := func(host string) ([]string, error) {
		dnsCalled = true
		return []string{"192.168.1.50"}, nil
	}

	cfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "PORT":
			return "0"
		case "DATABASE_URL":
			return "postgres://user:pass@127.0.0.1:5432/testdb?sslmode=disable"
		case "MQTT_HOST":
			return "mqtt-dev"
		default:
			return ""
		}
	}, dnsLookup)

	application, err := app.New(cfg)
	if err != nil {
		t.Fatalf("failed to initialize app in persistent mode: %v", err)
	}

	if application.DB() == nil {
		t.Fatal("expected non-nil DB in persistent mode")
	}
	if application.StatusSub() == nil {
		t.Fatal("expected non-nil StatusSub in persistent mode")
	}
	if application.Subscriber() == nil {
		t.Fatal("expected non-nil Subscriber lifecycle instance in persistent mode")
	}
	if !dnsCalled {
		t.Errorf("app.New in persistent mode MUST resolve MQTT broker URI via DNS fallback")
	}
}

func TestApp_Run_PersistentMode_RealSubscriberLifecycle(t *testing.T) {
	cfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "PORT":
			return "0"
		case "DATABASE_URL":
			return "postgres://user:pass@127.0.0.1:5432/testdb?sslmode=disable"
		case "MQTT_HOST":
			return "127.0.0.1"
		case "MQTT_PORT":
			return "1883"
		default:
			return ""
		}
	})
	cfg.ShutdownTimeout = 500 * time.Millisecond

	application, err := app.New(cfg)
	if err != nil {
		t.Fatalf("failed to initialize app: %v", err)
	}

	if application.StatusSub() == nil {
		t.Fatal("expected non-nil StatusSub in persistent mode")
	}

	ctx, cancel := context.WithCancel(context.Background())
	errCh := make(chan error, 1)
	go func() {
		errCh <- application.Run(ctx)
	}()

	time.Sleep(50 * time.Millisecond)
	cancel()

	select {
	case err := <-errCh:
		if err != nil {
			t.Errorf("expected clean shutdown, got error: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("application.Run did not terminate within timeout")
	}
}

type recordingSubscriber struct {
	mu           sync.Mutex
	events       []string
	startCalled  bool
	stopCalled   bool
	startErr     error
	onStartBlock chan struct{}
}

func (r *recordingSubscriber) Start(ctx context.Context) error {
	r.mu.Lock()
	r.startCalled = true
	r.events = append(r.events, "subscriber_start")
	blockCh := r.onStartBlock
	err := r.startErr
	r.mu.Unlock()

	if blockCh != nil {
		<-blockCh
	}
	return err
}

func (r *recordingSubscriber) Stop() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.stopCalled = true
	r.events = append(r.events, "subscriber_stop")
}

func (r *recordingSubscriber) getEvents() []string {
	r.mu.Lock()
	defer r.mu.Unlock()
	copied := make([]string, len(r.events))
	copy(copied, r.events)
	return copied
}

func TestApp_Run_DeterministicLifecycleOrdering(t *testing.T) {
	cfg := config.LoadFromEnv(func(key string) string {
		if key == "PORT" {
			return "0"
		}
		return ""
	})
	cfg.ShutdownTimeout = 500 * time.Millisecond

	recSub := &recordingSubscriber{}

	application, err := app.New(cfg, app.WithSubscriber(recSub))
	if err != nil {
		t.Fatalf("failed to initialize app: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	errCh := make(chan error, 1)
	go func() {
		errCh <- application.Run(ctx)
	}()

	// Wait for subscriber to start and server to respond
	time.Sleep(50 * time.Millisecond)

	recSub.mu.Lock()
	started := recSub.startCalled
	recSub.mu.Unlock()
	if !started {
		t.Fatal("expected subscriber.Start to be invoked during startup")
	}

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

	recSub.mu.Lock()
	stopped := recSub.stopCalled
	recSub.mu.Unlock()
	if !stopped {
		t.Fatal("expected subscriber.Stop to be invoked during shutdown")
	}

	events := recSub.getEvents()
	if len(events) != 2 || events[0] != "subscriber_start" || events[1] != "subscriber_stop" {
		t.Errorf("unexpected subscriber event order: %v", events)
	}
}

func TestApp_Run_FatalServerError(t *testing.T) {
	// Pre-bind a TCP port to trigger a listen conflict
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to bind port: %v", err)
	}
	defer l.Close()

	port := fmt.Sprintf("%d", l.Addr().(*net.TCPAddr).Port)

	cfg := config.LoadFromEnv(func(key string) string {
		if key == "PORT" {
			return port
		}
		return ""
	})

	application, err := app.New(cfg)
	if err != nil {
		t.Fatalf("failed to initialize app: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	err = application.Run(ctx)
	if err == nil {
		t.Fatal("expected server error due to address conflict, got nil")
	}
	if !strings.Contains(err.Error(), "server error:") {
		t.Errorf("expected wrapped 'server error:', got %v", err)
	}
}
