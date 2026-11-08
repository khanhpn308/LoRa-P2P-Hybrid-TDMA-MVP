package realtime

import (
	"log"
	"net/http"
	"net/url"
	"strings"

	"github.com/gorilla/websocket"
	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth"
)

var defaultAllowedOrigins = []string{
	"http://localhost:3000",
	"http://127.0.0.1:3000",
	"http://localhost:8080",
	"http://127.0.0.1:8080",
}

// Handler handles HTTP WebSocket upgrades for realtime fan-out (SE-006).
type Handler struct {
	hub              *Hub
	ticketStore      *auth.TicketStore
	jwtService       *auth.JWTService
	allowedOrigins   map[string]bool
	allowAllOrigins  bool
	allowEmptyOrigin bool
	upgrader         websocket.Upgrader
	bufferSize       int
}

// HandlerOption configures the WebSocket upgrade handler.
type HandlerOption func(*Handler)

// WithAllowedOrigins specifies the whitelist of allowed Origin URLs.
func WithAllowedOrigins(origins []string) HandlerOption {
	return func(h *Handler) {
		h.allowedOrigins = make(map[string]bool)
		for _, o := range origins {
			trimmed := strings.TrimSpace(o)
			if trimmed == "*" {
				h.allowAllOrigins = true
			} else if trimmed != "" {
				h.allowedOrigins[trimmed] = true
			}
		}
	}
}

// WithAllowEmptyOrigin sets whether handshake requests without an Origin header are permitted (e.g., CLI / test clients).
func WithAllowEmptyOrigin(allow bool) HandlerOption {
	return func(h *Handler) {
		h.allowEmptyOrigin = allow
	}
}

// WithBufferSize sets the outbound channel buffer size for upgraded clients.
func WithBufferSize(size int) HandlerOption {
	return func(h *Handler) {
		if size > 0 {
			h.bufferSize = size
		}
	}
}

// NewHandler initializes a new realtime WebSocket Handler.
func NewHandler(
	hub *Hub,
	ticketStore *auth.TicketStore,
	jwtService *auth.JWTService,
	options ...HandlerOption,
) *Handler {
	h := &Handler{
		hub:              hub,
		ticketStore:      ticketStore,
		jwtService:       jwtService,
		allowedOrigins:   make(map[string]bool),
		allowEmptyOrigin: false,
		bufferSize:       DefaultClientBufferSize,
	}

	for _, o := range defaultAllowedOrigins {
		h.allowedOrigins[o] = true
	}

	for _, opt := range options {
		opt(h)
	}

	h.upgrader = websocket.Upgrader{
		ReadBufferSize:  maxMessageSize,
		WriteBufferSize: maxMessageSize,
		CheckOrigin:     h.checkOrigin,
	}

	return h
}

// RegisterRoutes registers the WebSocket endpoint on the provided HTTP ServeMux.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v1/ws/realtime", h.ServeHTTP)
}

func (h *Handler) checkOrigin(r *http.Request) bool {
	origin := r.Header.Get("Origin")
	if origin == "" {
		// Non-browser or direct CLI client
		return h.allowEmptyOrigin
	}

	if h.allowAllOrigins {
		return true
	}

	// Direct match in whitelist
	if h.allowedOrigins[origin] {
		return true
	}

	// Match scheme + host
	parsed, err := url.Parse(origin)
	if err == nil && parsed.Host != "" {
		if h.allowedOrigins[parsed.Scheme+"://"+parsed.Host] {
			return true
		}
		// Allow origin if it matches request Host (same-origin policy)
		if parsed.Host == r.Host {
			return true
		}
	}

	return false
}

// ServeHTTP authenticates caller and upgrades HTTP to WebSocket (RFC 6455, SE-006).
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// 1. Strict Origin check before upgrade
	if !h.checkOrigin(r) {
		http.Error(w, "Forbidden: origin not allowed", http.StatusForbidden)
		return
	}

	// 2. Authentication check: query ticket (ADR-0005) or Bearer header
	var claims *auth.Claims
	ticket := r.URL.Query().Get("ticket")

	if ticket != "" && h.ticketStore != nil {
		c, ok := h.ticketStore.ConsumeTicket(ticket)
		if !ok {
			w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
			http.Error(w, "Unauthorized: invalid or expired websocket ticket", http.StatusUnauthorized)
			return
		}
		claims = c
	} else {
		// Check Authorization: Bearer <token>
		authHeader := r.Header.Get("Authorization")
		if authHeader != "" && strings.HasPrefix(authHeader, "Bearer ") && h.jwtService != nil {
			token := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
			c, err := h.jwtService.VerifyToken(token)
			if err != nil {
				w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
				http.Error(w, "Unauthorized: invalid bearer token", http.StatusUnauthorized)
				return
			}
			claims = c
		}
	}

	if claims == nil {
		w.Header().Set("WWW-Authenticate", `Bearer error="invalid_token"`)
		http.Error(w, "Unauthorized: authentication required via ticket or bearer token", http.StatusUnauthorized)
		return
	}

	// 3. RBAC role enforcement (SE-004)
	if !auth.IsValidRole(claims.Role) {
		http.Error(w, "Forbidden: insufficient role permissions", http.StatusForbidden)
		return
	}

	// 4. Upgrade HTTP connection to RFC 6455 WebSocket
	conn, err := h.upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[WSS Hub] Handshake upgrade failed: %v", err)
		return
	}

	clientID, err := GenerateUUIDv4()
	if err != nil {
		_ = conn.Close()
		return
	}

	client := NewClient(clientID, h.hub, conn, claims, h.bufferSize)
	h.hub.Register(client)

	go client.WritePump()
	go client.ReadPump()
}
