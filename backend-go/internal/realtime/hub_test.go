package realtime

import (
	"context"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

func TestHub_RegisterAndUnregister(t *testing.T) {
	hub := NewHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go hub.Run(ctx)

	client := NewClient("client-1", hub, nil, &auth.Claims{Role: auth.RoleViewer}, 10)

	hub.Register(client)

	// Wait for registration in loop
	time.Sleep(20 * time.Millisecond)
	if count := hub.ClientCount(); count != 1 {
		t.Fatalf("expected 1 client, got %d", count)
	}

	hub.Unregister(client)
	time.Sleep(20 * time.Millisecond)
	if count := hub.ClientCount(); count != 0 {
		t.Fatalf("expected 0 clients after unregister, got %d", count)
	}
}

func TestHub_BroadcastToMultipleClients(t *testing.T) {
	hub := NewHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go hub.Run(ctx)

	clientA := NewClient("client-a", hub, nil, &auth.Claims{Role: auth.RoleOperator}, 10)
	clientB := NewClient("client-b", hub, nil, &auth.Claims{Role: auth.RoleAdmin}, 10)

	hub.Register(clientA)
	hub.Register(clientB)
	time.Sleep(20 * time.Millisecond)

	payload := AlertTriggeredPayload{
		GatewayID:  "gw-test",
		NodeID:     1,
		AlertID:    "123",
		EventRef:   10,
		EventCode:  1,
		EventValue: 1,
		Severity:   "P1_HIGH",
	}

	if err := hub.BroadcastAlert(ctx, payload); err != nil {
		t.Fatalf("BroadcastAlert failed: %v", err)
	}

	// Verify both clients received the message in their send channel
	select {
	case msgA := <-clientA.send:
		if len(msgA) == 0 {
			t.Error("clientA received empty message")
		}
	case <-time.After(200 * time.Millisecond):
		t.Fatal("clientA timed out waiting for broadcast")
	}

	select {
	case msgB := <-clientB.send:
		if len(msgB) == 0 {
			t.Error("clientB received empty message")
		}
	case <-time.After(200 * time.Millisecond):
		t.Fatal("clientB timed out waiting for broadcast")
	}
}

func TestHub_SlowConsumerBackpressurePolicy(t *testing.T) {
	// Buffer size 2: client will fill up quickly
	hub := NewHub(WithClientBufferSize(2))
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go hub.Run(ctx)

	fastClient := NewClient("fast-client", hub, nil, &auth.Claims{Role: auth.RoleViewer}, 2)
	slowClient := NewClient("slow-client", hub, nil, &auth.Claims{Role: auth.RoleViewer}, 2)

	hub.Register(fastClient)
	hub.Register(slowClient)
	time.Sleep(20 * time.Millisecond)

	if count := hub.ClientCount(); count != 2 {
		t.Fatalf("expected 2 clients, got %d", count)
	}

	// Fill slowClient's buffer (capacity 2)
	slowClient.send <- []byte("msg1")
	slowClient.send <- []byte("msg2")

	// Fast client drain loop
	fastReceived := 0
	fastDone := make(chan struct{})
	go func() {
		for {
			select {
			case <-fastClient.send:
				fastReceived++
				if fastReceived == 3 {
					close(fastDone)
					return
				}
			case <-time.After(500 * time.Millisecond):
				return
			}
		}
	}()

	// Send 3 broadcasts:
	// First broadcast will find slowClient buffer full -> slowClient will be dropped!
	// Fast client should receive all broadcasts without delay.
	for i := 0; i < 3; i++ {
		err := hub.Broadcast(ctx, []byte(`{"test":true}`))
		if err != nil {
			t.Fatalf("Broadcast failed on iteration %d: %v", i, err)
		}
	}

	select {
	case <-fastDone:
		// Fast client received all 3 messages
	case <-time.After(500 * time.Millisecond):
		t.Fatalf("fast client timed out, received %d of 3", fastReceived)
	}

	// Verify slow client was closed and removed from hub
	time.Sleep(50 * time.Millisecond)
	if count := hub.ClientCount(); count != 1 {
		t.Fatalf("expected 1 client remaining after slow consumer drop, got %d", count)
	}

	select {
	case <-slowClient.closed:
		// Slow consumer closed channel triggered
	default:
		t.Error("expected slow client closed channel to be signaled")
	}
}

func TestHub_BroadcastAfterShutdown(t *testing.T) {
	hub := NewHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go hub.Run(ctx)

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer shutdownCancel()

	if err := hub.Shutdown(shutdownCtx); err != nil {
		t.Fatalf("hub.Shutdown failed: %v", err)
	}

	// Broadcasting to closed hub should return ErrHubClosed
	err := hub.Broadcast(ctx, []byte("data"))
	if err != ErrHubClosed {
		t.Fatalf("expected ErrHubClosed, got: %v", err)
	}
}

func TestHub_BroadcastDomainAlert(t *testing.T) {
	hub := NewHub()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go hub.Run(ctx)

	client := NewClient("c1", hub, nil, &auth.Claims{Role: auth.RoleViewer}, 5)
	hub.Register(client)
	time.Sleep(20 * time.Millisecond)

	trig := "2026-11-08T01:00:00Z"
	alert := domain.AlertView{
		AlertID:     "888",
		NodeID:      2,
		GatewayID:   "gw-01",
		EventRef:    123,
		EventCode:   1,
		EventValue:  100,
		Severity:    domain.SeverityP0Emergency,
		TriggeredAt: &trig,
	}

	if err := hub.BroadcastDomainAlert(ctx, alert); err != nil {
		t.Fatalf("BroadcastDomainAlert failed: %v", err)
	}

	select {
	case msg := <-client.send:
		if len(msg) == 0 {
			t.Error("received empty message from BroadcastDomainAlert")
		}
	case <-time.After(200 * time.Millisecond):
		t.Fatal("timed out waiting for domain alert broadcast")
	}
}
