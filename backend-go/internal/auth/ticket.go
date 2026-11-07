package auth

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
	"sync"
	"time"
)

type ticketRecord struct {
	claims    Claims
	expiresAt time.Time
}

// TicketStore provides thread-safe in-memory storage for single-use WebSocket tickets (RT-001, ADR-0005).
type TicketStore struct {
	mu      sync.Mutex
	tickets map[string]ticketRecord
}

// NewTicketStore initializes an empty TicketStore.
func NewTicketStore() *TicketStore {
	return &TicketStore{
		tickets: make(map[string]ticketRecord),
	}
}

// CreateTicket generates a cryptographically secure 32-byte pseudo-random ticket (CSPRNG hex string),
// associates it with the caller's claims, and stores it in memory for the duration of ttl.
func (s *TicketStore) CreateTicket(claims Claims, ttl time.Duration) (string, error) {
	var raw [32]byte
	if _, err := io.ReadFull(rand.Reader, raw[:]); err != nil {
		return "", fmt.Errorf("failed to generate secure random ticket: %w", err)
	}
	ticket := hex.EncodeToString(raw[:])

	s.mu.Lock()
	defer s.mu.Unlock()

	s.tickets[ticket] = ticketRecord{
		claims:    claims,
		expiresAt: time.Now().UTC().Add(ttl),
	}
	return ticket, nil
}

// ConsumeTicket atomically queries and removes the ticket from memory.
// It returns (*Claims, true) if and only if the ticket exists and has not expired.
// Subsequent attempts to consume the same ticket will fail (consume-once guarantee).
func (s *TicketStore) ConsumeTicket(ticket string) (*Claims, bool) {
	if ticket == "" {
		return nil, false
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	record, exists := s.tickets[ticket]
	if !exists {
		return nil, false
	}

	// Atomic deletion immediately upon access ensures zero replay window
	delete(s.tickets, ticket)

	if time.Now().UTC().After(record.expiresAt) {
		return nil, false
	}

	claimsCopy := record.claims
	return &claimsCopy, true
}

// PurgeExpired removes all expired tickets from the memory store to prevent memory bloat over time.
func (s *TicketStore) PurgeExpired(now time.Time) int {
	s.mu.Lock()
	defer s.mu.Unlock()

	purged := 0
	for ticket, record := range s.tickets {
		if now.After(record.expiresAt) {
			delete(s.tickets, ticket)
			purged++
		}
	}
	return purged
}

// Count returns the current active ticket count (primarily for testing and metrics).
func (s *TicketStore) Count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.tickets)
}
