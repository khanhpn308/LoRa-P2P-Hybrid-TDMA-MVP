package realtime

import (
	"log"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

const (
	// writeWait is the maximum time allowed to write a message to the peer (RT-004).
	writeWait = 5 * time.Second

	// pongWait is the maximum time allowed to read the next pong message from the peer.
	pongWait = 60 * time.Second

	// pingPeriod sends pings to peer with this period. Must be less than pongWait.
	pingPeriod = (pongWait * 9) / 10

	// maxMessageSize is the maximum message size allowed from peer (SE-004).
	maxMessageSize = 4096

	// DefaultClientBufferSize is the bounded outbound queue capacity per client (RT-002).
	DefaultClientBufferSize = 64
)

// Client represents an individual active WebSocket connection to the Realtime Hub.
type Client struct {
	id        string
	hub       *Hub
	conn      *websocket.Conn
	send      chan []byte
	claims    *auth.Claims
	closeOnce sync.Once
	closed    chan struct{}
}

// NewClient initializes a new connected Client with a bounded outbound buffer.
func NewClient(id string, hub *Hub, conn *websocket.Conn, claims *auth.Claims, bufferSize int) *Client {
	if bufferSize <= 0 {
		bufferSize = DefaultClientBufferSize
	}
	return &Client{
		id:     id,
		hub:    hub,
		conn:   conn,
		send:   make(chan []byte, bufferSize),
		claims: claims,
		closed: make(chan struct{}),
	}
}

// ID returns the unique client identifier.
func (c *Client) ID() string {
	return c.id
}

// Claims returns the authenticated principal claims associated with this connection.
func (c *Client) Claims() *auth.Claims {
	return c.claims
}

// Close safely initiates client termination and notifies the write pump (RT-007).
func (c *Client) Close() {
	c.closeOnce.Do(func() {
		close(c.closed)
	})
}

// ReadPump handles inbound WebSocket messages, pong responses, and dead socket detection (RT-004).
func (c *Client) ReadPump() {
	defer func() {
		c.hub.Unregister(c)
		c.Close()
		_ = c.conn.Close()
	}()

	c.conn.SetReadLimit(maxMessageSize)
	_ = c.conn.SetReadDeadline(time.Now().Add(pongWait))
	c.conn.SetPongHandler(func(string) error {
		_ = c.conn.SetReadDeadline(time.Now().Add(pongWait))
		return nil
	})

	for {
		_, _, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				log.Printf("[WSS Hub] Client %s disconnected unexpectedly: %v", c.id, err)
			}
			break
		}
		// In WSS v1, the channel is server-push only (websocket.md §1).
		// Any client application payload is discarded without mutating state.
	}
}

// WritePump handles outbound fan-out events, periodic heartbeat pings, and graceful close frames (RT-003, RT-004).
func (c *Client) WritePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		_ = c.conn.Close()
	}()

	for {
		select {
		case <-c.closed:
			// Gracefully send CloseGoingAway frame
			_ = c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			_ = c.conn.WriteMessage(
				websocket.CloseMessage,
				websocket.FormatCloseMessage(websocket.CloseGoingAway, "connection closed"),
			)
			return

		case message, ok := <-c.send:
			_ = c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				// Send channel closed by hub
				_ = c.conn.WriteMessage(
					websocket.CloseMessage,
					websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
				)
				return
			}

			if err := c.conn.WriteMessage(websocket.TextMessage, message); err != nil {
				log.Printf("[WSS Hub] Write error for client %s: %v", c.id, err)
				return
			}

		case <-ticker.C:
			_ = c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				log.Printf("[WSS Hub] Ping timeout for client %s: %v", c.id, err)
				return
			}
		}
	}
}
