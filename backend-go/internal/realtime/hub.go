package realtime

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"sync"
	"sync/atomic"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain"
)

var (
	// ErrHubClosed is returned when attempting to broadcast to a closed hub.
	ErrHubClosed = errors.New("realtime hub is closed")
)

// HubOption allows configuring Hub behavior.
type HubOption func(*Hub)

// WithClientBufferSize sets the bounded outbound queue size for clients.
func WithClientBufferSize(size int) HubOption {
	return func(h *Hub) {
		if size > 0 {
			h.clientBufferSize = size
		}
	}
}

// Hub maintains the set of active connected clients and broadcasts events
// according to the Hybrid TDMA MVP realtime specification (RT-001, RT-002, RT-003, RT-004).
type Hub struct {
	clients          map[*Client]bool
	register         chan *Client
	unregister       chan *Client
	broadcast        chan []byte
	stop             chan struct{}
	done             chan struct{}
	stopOnce         sync.Once
	clientBufferSize int
	activeClients    atomic.Int64
}

// NewHub constructs a new Realtime Hub.
func NewHub(options ...HubOption) *Hub {
	h := &Hub{
		clients:          make(map[*Client]bool),
		register:         make(chan *Client),
		unregister:       make(chan *Client),
		broadcast:        make(chan []byte, 128),
		stop:             make(chan struct{}),
		done:             make(chan struct{}),
		clientBufferSize: DefaultClientBufferSize,
	}
	for _, opt := range options {
		opt(h)
	}
	return h
}

// Run executes the central hub event loop, handling client lifecycle and fan-out (RT-001, RT-004).
func (h *Hub) Run(ctx context.Context) {
	defer close(h.done)

	for {
		select {
		case <-ctx.Done():
			h.closeAllClients()
			return

		case <-h.stop:
			h.closeAllClients()
			return

		case client := <-h.register:
			if _, exists := h.clients[client]; !exists {
				h.clients[client] = true
				h.activeClients.Add(1)
			}

		case client := <-h.unregister:
			if _, exists := h.clients[client]; exists {
				delete(h.clients, client)
				h.activeClients.Add(-1)
				client.Close()
			}

		case message := <-h.broadcast:
			// Fan-out with non-blocking slow consumer protection (RT-002, RT-004)
			var slowConsumers []*Client
			for client := range h.clients {
				select {
				case client.send <- message:
					// Fast consumer: successfully queued in bounded buffer
				default:
					// Slow consumer: outbound buffer full! Drop immediately to prevent blocking others.
					log.Printf("[WSS Hub] Slow consumer detected on client %s (buffer size %d full); terminating connection.",
						client.ID(), h.clientBufferSize)
					slowConsumers = append(slowConsumers, client)
				}
			}

			// Clean up slow consumers
			for _, client := range slowConsumers {
				delete(h.clients, client)
				h.activeClients.Add(-1)
				client.Close()
			}
		}
	}
}

// Register registers a new client with the Hub.
func (h *Hub) Register(client *Client) {
	select {
	case <-h.stop:
		client.Close()
		return
	default:
	}

	select {
	case <-h.stop:
		client.Close()
	case h.register <- client:
	}
}

// Unregister unregisters an existing client from the Hub.
func (h *Hub) Unregister(client *Client) {
	select {
	case <-h.stop:
		return
	default:
	}

	select {
	case <-h.stop:
	case h.unregister <- client:
	}
}

// ClientCount returns the number of currently connected clients.
func (h *Hub) ClientCount() int {
	return int(h.activeClients.Load())
}

// Broadcast sends a pre-formatted JSON event to all registered clients.
func (h *Hub) Broadcast(ctx context.Context, message []byte) error {
	select {
	case <-h.stop:
		return ErrHubClosed
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-h.stop:
		return ErrHubClosed
	case h.broadcast <- message:
		return nil
	}
}

// BroadcastEnvelope serializes and broadcasts a RealtimeEnvelope.
func (h *Hub) BroadcastEnvelope(ctx context.Context, env *RealtimeEnvelope) error {
	if env == nil {
		return errors.New("cannot broadcast nil envelope")
	}
	bytes, err := json.Marshal(env)
	if err != nil {
		return fmt.Errorf("failed to serialize realtime envelope: %w", err)
	}
	return h.Broadcast(ctx, bytes)
}

// BroadcastAlert broadcasts an ALERT_TRIGGERED event.
func (h *Hub) BroadcastAlert(ctx context.Context, payload AlertTriggeredPayload) error {
	env, err := NewAlertTriggeredEvent(payload, nil)
	if err != nil {
		return fmt.Errorf("invalid alert event payload: %w", err)
	}
	return h.BroadcastEnvelope(ctx, env)
}

// BroadcastScheduleState broadcasts a SCHEDULE_STATE_CHANGED event.
func (h *Hub) BroadcastScheduleState(ctx context.Context, payload ScheduleStateChangedPayload) error {
	env, err := NewScheduleStateChangedEvent(payload, nil)
	if err != nil {
		return fmt.Errorf("invalid schedule state payload: %w", err)
	}
	return h.BroadcastEnvelope(ctx, env)
}

// BroadcastGatewayStatus broadcasts a GATEWAY_STATUS_CHANGED event.
func (h *Hub) BroadcastGatewayStatus(ctx context.Context, payload GatewayStatusChangedPayload) error {
	env, err := NewGatewayStatusChangedEvent(payload, nil)
	if err != nil {
		return fmt.Errorf("invalid gateway status payload: %w", err)
	}
	return h.BroadcastEnvelope(ctx, env)
}

// BroadcastDomainAlert converts a domain.AlertView into an ALERT_TRIGGERED payload and broadcasts it.
func (h *Hub) BroadcastDomainAlert(ctx context.Context, alert domain.AlertView) error {
	payload := AlertTriggeredPayload{
		GatewayID:   alert.GatewayID,
		NodeID:      alert.NodeID,
		AlertID:     alert.AlertID,
		EventRef:    alert.EventRef,
		EventCode:   alert.EventCode,
		EventValue:  alert.EventValue,
		Severity:    string(alert.Severity),
		TriggeredAt: alert.TriggeredAt,
	}
	return h.BroadcastAlert(ctx, payload)
}

// Shutdown initiates graceful termination of the Hub and closes all active client connections (RT-003).
func (h *Hub) Shutdown(ctx context.Context) error {
	h.stopOnce.Do(func() {
		close(h.stop)
	})

	select {
	case <-h.done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (h *Hub) closeAllClients() {
	for client := range h.clients {
		client.Close()
		delete(h.clients, client)
	}
	h.activeClients.Store(0)
}
