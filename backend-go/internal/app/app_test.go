package app_test

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"fmt"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
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

func closedLocalPort(t *testing.T) string {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("failed to allocate ephemeral port: %v", err)
	}
	port := fmt.Sprintf("%d", l.Addr().(*net.TCPAddr).Port)
	_ = l.Close()
	return port
}

func TestApp_New_PersistentMode_SubscriberInitialized(t *testing.T) {
	dnsCalled := false
	dnsLookup := func(host string) ([]string, error) {
		dnsCalled = true
		return []string{"192.168.1.50"}, nil
	}
	dbPort := closedLocalPort(t)

	cfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "PORT":
			return "0"
		case "DATABASE_URL":
			return fmt.Sprintf("postgres://user:pass@127.0.0.1:%s/testdb?sslmode=disable&connect_timeout=1", dbPort)
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
	dbPort := closedLocalPort(t)
	mqttPort := closedLocalPort(t)
	cfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "PORT":
			return "0"
		case "DATABASE_URL":
			return fmt.Sprintf("postgres://user:pass@127.0.0.1:%s/testdb?sslmode=disable&connect_timeout=1", dbPort)
		case "MQTT_HOST":
			return "127.0.0.1"
		case "MQTT_PORT":
			return mqttPort
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

func TestApp_New_PersistentMode_FailsClosedOnUnresolvedMQTTHost(t *testing.T) {
	dnsLookup := func(host string) ([]string, error) {
		return nil, errors.New("dns unavailable")
	}
	dbPort := closedLocalPort(t)

	cfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "PORT":
			return "0"
		case "DATABASE_URL":
			return fmt.Sprintf("postgres://user:pass@127.0.0.1:%s/testdb?sslmode=disable&connect_timeout=1", dbPort)
		case "MQTT_HOST":
			return "mqtt-dev"
		default:
			return ""
		}
	}, dnsLookup)

	application, err := app.New(cfg)
	if !errors.Is(err, config.ErrUnresolvedMQTTHost) {
		t.Fatalf("expected ErrUnresolvedMQTTHost, got (%v, %v)", application, err)
	}
}

func TestApp_New_PersistentMode_FailsClosedOnMissingTLSCerts(t *testing.T) {
	dbPort := closedLocalPort(t)
	cfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "PORT":
			return "0"
		case "DATABASE_URL":
			return fmt.Sprintf("postgres://user:pass@127.0.0.1:%s/testdb?sslmode=disable&connect_timeout=1", dbPort)
		case "MQTT_HOST":
			return "mqtt-tls"
		case "MQTT_TLS_ENABLED":
			return "true"
		case "MQTT_TLS_CA_FILE":
			return filepath.Join(t.TempDir(), "nonexistent-ca.crt")
		default:
			return ""
		}
	})

	application, err := app.New(cfg)
	if !errors.Is(err, config.ErrInvalidMQTTConfig) {
		t.Fatalf("expected ErrInvalidMQTTConfig, got (%v, %v)", application, err)
	}
}

func TestApp_New_PersistentMode_TLSValidCerts_Succeeds(t *testing.T) {
	dir := t.TempDir()
	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("generate ca key: %v", err)
	}
	caSerial, _ := rand.Int(rand.Reader, big.NewInt(1<<62))
	caTmpl := &x509.Certificate{
		SerialNumber:          caSerial,
		Subject:               pkix.Name{CommonName: "test-ca"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
		BasicConstraintsValid: true,
		IsCA:                  true,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, caTmpl, caTmpl, &caKey.PublicKey, caKey)
	if err != nil {
		t.Fatalf("create ca cert: %v", err)
	}
	caPath := filepath.Join(dir, "ca.crt")
	if err := os.WriteFile(caPath, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER}), 0o600); err != nil {
		t.Fatalf("write ca cert: %v", err)
	}

	dbPort := closedLocalPort(t)
	cfg := config.LoadFromEnv(func(key string) string {
		switch key {
		case "PORT":
			return "0"
		case "DATABASE_URL":
			return fmt.Sprintf("postgres://user:pass@127.0.0.1:%s/testdb?sslmode=disable&connect_timeout=1", dbPort)
		case "MQTT_HOST":
			return "mqtt-tls"
		case "MQTT_TLS_ENABLED":
			return "true"
		case "MQTT_TLS_CA_FILE":
			return caPath
		default:
			return ""
		}
	})

	application, err := app.New(cfg)
	if err != nil {
		t.Fatalf("expected app.New to succeed with valid TLS CA cert, got %v", err)
	}
	if application.DB() != nil {
		_ = application.DB().Close()
	}
	uri, err := cfg.ResolveMQTTBrokerURI()
	if err != nil || uri != "tls://mqtt-tls:8883" {
		t.Errorf("expected tls://mqtt-tls:8883, got (%q, %v)", uri, err)
	}
}
