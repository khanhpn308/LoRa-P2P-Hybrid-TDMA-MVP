package realtime

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"go.uber.org/goleak"
)

func TestConcurrency_FanOutAndGracefulShutdown(t *testing.T) {
	// Enforce zero goroutine leaks on test completion (TS-009, RT-004)
	defer goleak.VerifyNone(t)

	hub := NewHub(WithClientBufferSize(32))
	hubCtx, hubCancel := context.WithCancel(context.Background())
	go hub.Run(hubCtx)

	ticketStore := auth.NewTicketStore()
	jwtService, err := auth.NewJWTService([]byte("secret-jwt-key-for-concurrency-tests!!"))
	if err != nil {
		t.Fatalf("NewJWTService failed: %v", err)
	}

	handler := NewHandler(hub, ticketStore, jwtService,
		WithAllowEmptyOrigin(true),
		WithBufferSize(32),
	)

	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	server := httptest.NewServer(mux)

	const clientCount = 20
	const messageCount = 5

	var conns []*websocket.Conn
	var wg sync.WaitGroup

	// Connect clients concurrently
	claims := auth.Claims{
		Sub:      "concurrent-user",
		Username: "tester",
		Role:     auth.RoleOperator,
	}

	for i := 0; i < clientCount; i++ {
		ticket, err := ticketStore.CreateTicket(claims, 30*time.Second)
		if err != nil {
			t.Fatalf("CreateTicket failed: %v", err)
		}

		conn, resp, err := websocket.DefaultDialer.Dial(toWSURL(server.URL, "ticket="+ticket), nil)
		if err != nil {
			t.Fatalf("failed to connect client %d: %v", i, err)
		}
		if resp.StatusCode != http.StatusSwitchingProtocols {
			t.Fatalf("expected 101, got %d", resp.StatusCode)
		}
		conns = append(conns, conn)
	}

	// Wait for registration in hub
	time.Sleep(50 * time.Millisecond)
	if count := hub.ClientCount(); count != clientCount {
		t.Fatalf("expected %d registered clients, got %d", clientCount, count)
	}

	// Each client reads messages concurrently
	receivedCounts := make([]int, clientCount)
	for idx, conn := range conns {
		wg.Add(1)
		go func(cIndex int, c *websocket.Conn) {
			defer wg.Done()
			for {
				_ = c.SetReadDeadline(time.Now().Add(2 * time.Second))
				msgType, _, err := c.ReadMessage()
				if err != nil {
					// Disconnect or close frame received
					break
				}
				if msgType == websocket.TextMessage {
					receivedCounts[cIndex]++
					if receivedCounts[cIndex] == messageCount {
						break
					}
				}
			}
		}(idx, conn)
	}

	// Broadcast messages concurrently
	for m := 0; m < messageCount; m++ {
		payload := AlertTriggeredPayload{
			GatewayID:  "gw-perf",
			NodeID:     uint8((m % 15) + 1),
			AlertID:    "9000",
			EventRef:   uint32(m + 1),
			EventCode:  1,
			EventValue: int16(m * 10),
			Severity:   "P1_HIGH",
		}
		if err := hub.BroadcastAlert(context.Background(), payload); err != nil {
			t.Fatalf("BroadcastAlert failed: %v", err)
		}
	}

	// Wait for all clients to receive all messages
	wg.Wait()

	for i, count := range receivedCounts {
		if count != messageCount {
			t.Errorf("client %d received %d messages, expected %d", i, count, messageCount)
		}
	}

	// Graceful shutdown: Hub close frame delivery
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer shutdownCancel()

	if err := hub.Shutdown(shutdownCtx); err != nil {
		t.Fatalf("hub.Shutdown failed: %v", err)
	}
	hubCancel()

	for _, conn := range conns {
		_ = conn.Close()
	}

	server.Close()
	// Allow background goroutines to finish unwinding
	time.Sleep(50 * time.Millisecond)
}

func TestClient_AbruptDisconnectCleanup(t *testing.T) {
	defer goleak.VerifyNone(t)

	hub := NewHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go hub.Run(ctx)

	ticketStore := auth.NewTicketStore()
	jwtService, err := auth.NewJWTService([]byte("secret-jwt-key-disconnect-cleanup-test!"))
	if err != nil {
		t.Fatalf("NewJWTService failed: %v", err)
	}

	handler := NewHandler(hub, ticketStore, jwtService, WithAllowEmptyOrigin(true))
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	server := httptest.NewServer(mux)
	defer server.Close()

	claims := auth.Claims{Role: auth.RoleViewer}
	ticket, _ := ticketStore.CreateTicket(claims, 30*time.Second)

	conn, _, err := websocket.DefaultDialer.Dial(toWSURL(server.URL, "ticket="+ticket), nil)
	if err != nil {
		t.Fatalf("Dial failed: %v", err)
	}

	time.Sleep(30 * time.Millisecond)
	if hub.ClientCount() != 1 {
		t.Fatalf("expected 1 client, got %d", hub.ClientCount())
	}

	// Abruptly close connection from client side
	_ = conn.Close()

	// Wait for ReadPump detection and Hub unregister
	time.Sleep(50 * time.Millisecond)
	if hub.ClientCount() != 0 {
		t.Fatalf("expected 0 clients after abrupt disconnect, got %d", hub.ClientCount())
	}

	shutdownCtx, sCancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer sCancel()
	_ = hub.Shutdown(shutdownCtx)
}
