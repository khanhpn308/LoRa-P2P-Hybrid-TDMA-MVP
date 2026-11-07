package realtime

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func setupTestWSServer(t *testing.T, opts ...HandlerOption) (*httptest.Server, *Hub, *auth.TicketStore, *auth.JWTService, func()) {
	t.Helper()

	hub := NewHub()
	ctx, cancel := context.WithCancel(context.Background())
	go hub.Run(ctx)

	ticketStore := auth.NewTicketStore()
	jwtService, err := auth.NewJWTService([]byte("test-secret-key-at-least-32-characters-long!!"))
	if err != nil {
		t.Fatalf("NewJWTService failed: %v", err)
	}

	handler := NewHandler(hub, ticketStore, jwtService, opts...)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	server := httptest.NewServer(mux)

	cleanup := func() {
		server.Close()
		shutdownCtx, sCancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer sCancel()
		_ = hub.Shutdown(shutdownCtx)
		cancel()
	}

	return server, hub, ticketStore, jwtService, cleanup
}

func toWSURL(httpURL string, query string) string {
	wsURL := "ws" + strings.TrimPrefix(httpURL, "http") + "/api/v1/ws/realtime"
	if query != "" {
		wsURL += "?" + query
	}
	return wsURL
}

func TestHandler_Handshake_ValidTicket(t *testing.T) {
	server, _, ticketStore, _, cleanup := setupTestWSServer(t, WithAllowEmptyOrigin(true))
	defer cleanup()

	claims := auth.Claims{
		Sub:      "user-1",
		Username: "operator_test",
		Role:     auth.RoleOperator,
	}

	ticket, err := ticketStore.CreateTicket(claims, 30*time.Second)
	if err != nil {
		t.Fatalf("CreateTicket failed: %v", err)
	}

	wsURL := toWSURL(server.URL, "ticket="+ticket)
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("WebSocket dial failed: %v", err)
	}
	defer conn.Close()

	if resp.StatusCode != http.StatusSwitchingProtocols {
		t.Fatalf("expected 101 Switching Protocols, got %d", resp.StatusCode)
	}

	// Consume-once guarantee: Attempting to connect again with same ticket must fail (zero replay)
	_, replayResp, replayErr := websocket.DefaultDialer.Dial(wsURL, nil)
	if replayErr == nil {
		t.Fatal("expected dial with consumed ticket to fail, but succeeded")
	}
	if replayResp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 Unauthorized on ticket replay, got %d", replayResp.StatusCode)
	}
}

func TestHandler_Handshake_ExpiredTicket(t *testing.T) {
	server, _, ticketStore, _, cleanup := setupTestWSServer(t, WithAllowEmptyOrigin(true))
	defer cleanup()

	claims := auth.Claims{
		Sub:      "user-1",
		Username: "viewer_test",
		Role:     auth.RoleViewer,
	}

	// Create ticket with negative duration to simulate expiration
	ticket, err := ticketStore.CreateTicket(claims, -1*time.Second)
	if err != nil {
		t.Fatalf("CreateTicket failed: %v", err)
	}

	wsURL := toWSURL(server.URL, "ticket="+ticket)
	_, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err == nil {
		t.Fatal("expected expired ticket dial to fail, but succeeded")
	}
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 Unauthorized for expired ticket, got %d", resp.StatusCode)
	}
}

func TestHandler_Handshake_BearerToken(t *testing.T) {
	server, _, _, jwtService, cleanup := setupTestWSServer(t, WithAllowEmptyOrigin(true))
	defer cleanup()

	user := &auth.User{
		ID:       "user-admin",
		Username: "admin_user",
		Role:     auth.RoleAdmin,
	}
	token, err := jwtService.GenerateToken(user, 60*time.Minute)
	if err != nil {
		t.Fatalf("GenerateToken failed: %v", err)
	}

	header := make(http.Header)
	header.Set("Authorization", "Bearer "+token)

	wsURL := toWSURL(server.URL, "")
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, header)
	if err != nil {
		t.Fatalf("WebSocket dial with Bearer token failed: %v", err)
	}
	defer conn.Close()

	if resp.StatusCode != http.StatusSwitchingProtocols {
		t.Fatalf("expected 101 Switching Protocols, got %d", resp.StatusCode)
	}
}

func TestHandler_Handshake_InvalidBearerToken(t *testing.T) {
	server, _, _, _, cleanup := setupTestWSServer(t, WithAllowEmptyOrigin(true))
	defer cleanup()

	header := make(http.Header)
	header.Set("Authorization", "Bearer invalid-garbage-token")

	wsURL := toWSURL(server.URL, "")
	_, resp, err := websocket.DefaultDialer.Dial(wsURL, header)
	if err == nil {
		t.Fatal("expected invalid token dial to fail, but succeeded")
	}
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 Unauthorized for invalid token, got %d", resp.StatusCode)
	}
}

func TestHandler_Handshake_MissingAuth(t *testing.T) {
	server, _, _, _, cleanup := setupTestWSServer(t, WithAllowEmptyOrigin(true))
	defer cleanup()

	wsURL := toWSURL(server.URL, "")
	_, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err == nil {
		t.Fatal("expected unauthenticated dial to fail, but succeeded")
	}
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 Unauthorized for missing auth, got %d", resp.StatusCode)
	}
}

func TestHandler_OriginValidation(t *testing.T) {
	server, _, ticketStore, _, cleanup := setupTestWSServer(t,
		WithAllowedOrigins([]string{"http://trusted.example.com", "http://localhost:3000"}),
		WithAllowEmptyOrigin(false),
	)
	defer cleanup()

	claims := auth.Claims{
		Sub:      "user-1",
		Username: "operator",
		Role:     auth.RoleOperator,
	}

	// 1. Valid Origin: http://trusted.example.com
	ticket1, _ := ticketStore.CreateTicket(claims, 30*time.Second)
	headerValid := make(http.Header)
	headerValid.Set("Origin", "http://trusted.example.com")
	conn, resp, err := websocket.DefaultDialer.Dial(toWSURL(server.URL, "ticket="+ticket1), headerValid)
	if err != nil {
		t.Fatalf("dial with trusted origin failed: %v", err)
	}
	_ = conn.Close()
	if resp.StatusCode != http.StatusSwitchingProtocols {
		t.Fatalf("expected 101 for trusted origin, got %d", resp.StatusCode)
	}

	// 2. Disallowed Origin: http://malicious.evil.com -> 403 Forbidden
	ticket2, _ := ticketStore.CreateTicket(claims, 30*time.Second)
	headerInvalid := make(http.Header)
	headerInvalid.Set("Origin", "http://malicious.evil.com")
	_, respBad, errBad := websocket.DefaultDialer.Dial(toWSURL(server.URL, "ticket="+ticket2), headerInvalid)
	if errBad == nil {
		t.Fatal("expected dial with untrusted origin to fail, but succeeded")
	}
	if respBad.StatusCode != http.StatusForbidden {
		t.Fatalf("expected 403 Forbidden for untrusted origin, got %d", respBad.StatusCode)
	}
}
