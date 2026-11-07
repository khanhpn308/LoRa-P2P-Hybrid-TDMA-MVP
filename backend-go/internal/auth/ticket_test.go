package auth_test

import (
	"sync"
	"testing"
	"time"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

func TestTicketStore_SingleUseLifecycle(t *testing.T) {
	store := auth.NewTicketStore()
	claims := auth.Claims{
		Sub:      "user-123",
		Username: "operator",
		Role:     auth.RoleOperator,
	}

	ticket, err := store.CreateTicket(claims, 30*time.Second)
	if err != nil {
		t.Fatalf("failed to create ticket: %v", err)
	}

	if len(ticket) != 64 { // 32 bytes hex encoded = 64 chars
		t.Fatalf("expected 64 character hex ticket, got %d chars", len(ticket))
	}

	// First consumption must succeed
	consumed, ok := store.ConsumeTicket(ticket)
	if !ok || consumed == nil {
		t.Fatal("first consumption of valid ticket must succeed")
	}
	if consumed.Sub != claims.Sub || consumed.Role != claims.Role {
		t.Fatalf("consumed claims mismatch: %+v", consumed)
	}

	// Second consumption MUST fail (single-use guarantee, ADR-0005)
	consumedSecond, okSecond := store.ConsumeTicket(ticket)
	if okSecond || consumedSecond != nil {
		t.Fatal("second consumption of same ticket must fail (replay violation)")
	}
}

func TestTicketStore_ExpiredTicket(t *testing.T) {
	store := auth.NewTicketStore()
	claims := auth.Claims{
		Sub:      "user-456",
		Username: "viewer",
		Role:     auth.RoleViewer,
	}

	// Create ticket with negative TTL (already expired)
	ticket, err := store.CreateTicket(claims, -1*time.Second)
	if err != nil {
		t.Fatalf("failed to create ticket: %v", err)
	}

	consumed, ok := store.ConsumeTicket(ticket)
	if ok || consumed != nil {
		t.Fatal("consumption of expired ticket must return false")
	}
}

func TestTicketStore_ConcurrentConsumption(t *testing.T) {
	store := auth.NewTicketStore()
	claims := auth.Claims{
		Sub:      "user-concurrent",
		Username: "admin",
		Role:     auth.RoleAdmin,
	}

	ticket, err := store.CreateTicket(claims, 10*time.Second)
	if err != nil {
		t.Fatalf("failed to create ticket: %v", err)
	}

	const concurrentGoroutines = 50
	var wg sync.WaitGroup
	wg.Add(concurrentGoroutines)

	successCount := 0
	var mu sync.Mutex

	for i := 0; i < concurrentGoroutines; i++ {
		go func() {
			defer wg.Done()
			_, ok := store.ConsumeTicket(ticket)
			if ok {
				mu.Lock()
				successCount++
				mu.Unlock()
			}
		}()
	}

	wg.Wait()

	if successCount != 1 {
		t.Fatalf("expected exactly 1 successful consumption among %d concurrent attempts, got %d", concurrentGoroutines, successCount)
	}
}

func TestTicketStore_PurgeExpired(t *testing.T) {
	store := auth.NewTicketStore()
	claims := auth.Claims{Sub: "u1", Role: auth.RoleViewer}

	_, _ = store.CreateTicket(claims, -10*time.Second) // expired
	_, _ = store.CreateTicket(claims, -5*time.Second)  // expired
	_, _ = store.CreateTicket(claims, 60*time.Second)  // active

	if store.Count() != 3 {
		t.Fatalf("expected count 3, got %d", store.Count())
	}

	purged := store.PurgeExpired(time.Now().UTC())
	if purged != 2 {
		t.Fatalf("expected 2 purged, got %d", purged)
	}
	if store.Count() != 1 {
		t.Fatalf("expected 1 remaining ticket, got %d", store.Count())
	}
}
