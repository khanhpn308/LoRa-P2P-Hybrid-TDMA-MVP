package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime"
)

func TestWebSocketHandler_RouteRegistrationAndUpgrade(t *testing.T) {
	hub := realtime.NewHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go hub.Run(ctx)

	ticketStore := auth.NewTicketStore()
	jwtService, err := auth.NewJWTService([]byte("secret-key-at-least-32-chars-long-api-test!"))
	if err != nil {
		t.Fatalf("NewJWTService failed: %v", err)
	}

	realtimeHandler := realtime.NewHandler(hub, ticketStore, jwtService,
		realtime.WithAllowEmptyOrigin(true),
	)
	wsHandler := NewWebSocketHandler(realtimeHandler)

	mux := http.NewServeMux()
	wsHandler.RegisterRoutes(mux)

	server := httptest.NewServer(mux)
	defer server.Close()

	claims := auth.Claims{
		Sub:      "user-api-test",
		Username: "operator",
		Role:     auth.RoleOperator,
	}
	ticket, err := ticketStore.CreateTicket(claims, 30*time.Second)
	if err != nil {
		t.Fatalf("CreateTicket failed: %v", err)
	}

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/api/v1/ws/realtime?ticket=" + ticket
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("WebSocket upgrade via WebSocketHandler failed: %v", err)
	}
	defer conn.Close()

	if resp.StatusCode != http.StatusSwitchingProtocols {
		t.Fatalf("expected 101 Switching Protocols, got %d", resp.StatusCode)
	}

	shutdownCtx, sCancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer sCancel()
	_ = hub.Shutdown(shutdownCtx)
}

func TestWebSocketHandler_NilHandler(t *testing.T) {
	wsHandler := NewWebSocketHandler(nil)
	mux := http.NewServeMux()
	wsHandler.RegisterRoutes(mux)

	req := httptest.NewRequest("GET", "/api/v1/ws/realtime", nil)
	rec := httptest.NewRecorder()

	wsHandler.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 Service Unavailable for nil handler, got %d", rec.Code)
	}
}
